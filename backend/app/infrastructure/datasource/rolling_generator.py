"""滚动观测数据生成器（评审 V2.0 §2 修复项 R1 + R3，及 P1-7 事件注入）。

根因回顾：观测数据此前由 scripts/generate_demo_data.py 一次性生成到固定
时刻，服务运行期无人追加样本 → 六站最新样本时间戳冻结、data_age_min 线性
增长、健康检查误报「运行正常」。

本生成器改为**滚动窗口**（R1）：

  - tick(now) 以传入时刻为基准、按采样步长（默认 5min）对齐后追加样本，
    样本时间戳永远来自相对时间（floor(now/step)），永不耗尽；
  - tick/catch_up/inject_event 均接受显式 now 参数（可注入时钟，可测性）；
  - 水位递推与 LinearResponseModel / generate_demo_data 共用同一套
    gain/kernel/response_k 参数（ADR-3），模拟数据与模型口径一致；
  - catch_up() 供健康检查在 STALE 时调用（R3 自愈）：清空内存态后从
    Parquet 最后样本一路补齐到当前时刻，并写 self_heal 日志；
  - inject_event() 注入极端降雨事件（P1-7 演示钥匙）：观测雨强按
    storm_shape 时程落入后续 tick，同时把同样的雨真值追加进
    station_{id}_future.parquet——降雨预报（get_rain_forecast）取数自
    该文件，预测链路因此能「提前看到」上涨，从而产生带提前量的预警。

# EXT-POINT(DATASOURCE): 接入真实数据源时，用真实采集适配器替换本生成器
# 的 tick 数据来源（健康检查新鲜度判定、自愈框架与注入接口形态不变）。
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from app.core.logging import get_logger
from app.infrastructure.forecast.params import build_kernel

logger = get_logger("datasource.rolling")

# 强度档位 → (每步峰值 mm, 持续分钟)（P1-7 演示钥匙档位表）
INTENSITY_PRESETS: dict = {
    "light": {"peak_mm": 2.2, "duration_minutes": 90, "label": "小雨"},
    "moderate": {"peak_mm": 5.0, "duration_minutes": 120, "label": "中雨"},
    "heavy": {"peak_mm": 8.0, "duration_minutes": 150, "label": "大雨"},
    "extreme": {"peak_mm": 12.0, "duration_minutes": 120, "label": "极端暴雨"},
}


def storm_shape(steps: int, peak: float, rng) -> np.ndarray:
    """雨强时程曲线：快速起涨 → 峰值 → 指数退去（与 generate_demo_data 同形）。"""
    t = np.linspace(0, 1, max(int(steps), 1))
    rise = 1 - np.exp(-t * 8)
    fall = np.exp(-np.maximum(t - 0.45, 0) * 6)
    shape = rise * fall
    jitter = rng.uniform(0.85, 1.15, len(t))
    return np.round(np.clip(shape * peak * jitter, 0, None), 2)


def floor_to_step(ts: datetime, step_minutes: int) -> datetime:
    """对齐到采样步长（相对时间基准，R1 的核心：不用固定起点）。"""
    base = ts.replace(second=0, microsecond=0)
    return base - timedelta(minutes=base.minute % step_minutes)


class _StationState:
    __slots__ = ("last_ts", "level", "rain_window")

    def __init__(self, last_ts: Optional[datetime], level: float, rain_window: np.ndarray):
        self.last_ts = last_ts
        self.level = level
        self.rain_window = rain_window  # 最近 kernel_len 步雨强（含当前步）


class RollingSimGenerator:
    """滚动追加观测样本；线程安全（调度线程与健康检查线程并发调用）。"""

    def __init__(
        self,
        ts_repo,
        stations_provider: Callable[[], list],
        linear_params,
        step_minutes: int = 5,
        base_drizzle_prob: float = 0.06,
        max_tick_steps: int = 12,
        max_catch_up_steps: int = 600,
    ):
        self._ts_repo = ts_repo
        self._stations_provider = stations_provider  # 返回 [{station_id, base_level, response_k}]
        self._params = linear_params
        self._step = step_minutes
        self._drizzle_prob = base_drizzle_prob
        self._max_tick_steps = max_tick_steps          # 单次 tick 最多补步数（防雪崩）
        self._max_catch_up_steps = max_catch_up_steps  # 自愈补齐上限
        self._kernel = build_kernel(linear_params.kernel_len, linear_params.kernel_tau)
        self._gain = linear_params.gain
        self._lock = threading.Lock()
        self._state: dict = {}
        self._events: dict = {}   # station_id -> [event dict]
        self._event_seq = 0

    # ------------------------------------------------------------------
    # 站点状态
    # ------------------------------------------------------------------
    def _stations(self) -> list:
        try:
            rows = self._stations_provider() or []
        except Exception:
            logger.exception("stations_provider failed; rolling tick skipped this round")
            return []
        out = []
        for r in rows:
            out.append({
                "station_id": int(r["station_id"]),
                "base_level": float(r.get("base_level") or 1.0),
                "response_k": float(r.get("response_k") if r.get("response_k") is not None else 0.01),
            })
        return out

    def _seed_state(self, station_id: int, base_level: float) -> _StationState:
        """从 Parquet 最后样本播种递推状态；无数据则从「一步之前」冷启动。

        种子时间戳对齐到采样网格：离网种子（如生成脚本在任意分钟运行过）
        会让后续样本永远偏离网格、滞后峰值逼近 8 分钟；对齐后样本严格
        落网格，data_age_min 峰值 ≈ 一个采样周期。
        """
        latest = self._ts_repo.latest(station_id)
        window = np.zeros(len(self._kernel))
        if latest and latest.get("ts"):
            ts = pd.Timestamp(latest["ts"]).to_pydatetime()
            grid = floor_to_step(ts, self._step)
            st = _StationState(grid if grid != ts else ts, float(latest["level"]), window)
        else:
            st = _StationState(None, base_level, window)
        return st

    # ------------------------------------------------------------------
    # 降雨：基础毛毛雨 + 注入事件
    # ------------------------------------------------------------------
    def _base_drizzle(self, station_id: int, ts: datetime) -> float:
        rng = np.random.default_rng((int(ts.timestamp()) * 1000 + station_id) % (2**32))
        if rng.random() < self._drizzle_prob:
            return float(np.round(rng.uniform(0.1, 0.6), 2))
        return 0.0

    def _event_rain(self, station_id: int, ts: datetime) -> float:
        total = 0.0
        for ev in self._events.get(station_id, []):
            if ev["start_ts"] <= ts <= ev["end_ts"]:
                idx = int((ts - ev["start_ts"]).total_seconds() // (self._step * 60))
                if 0 <= idx < len(ev["shape"]):
                    total += float(ev["shape"][idx])
        return total

    # ------------------------------------------------------------------
    # 递推一步
    # ------------------------------------------------------------------
    def _advance(self, st: _StationState, station: dict, ts: datetime) -> tuple:
        rain = round(self._base_drizzle(station["station_id"], ts)
                     + self._event_rain(station["station_id"], ts), 2)
        win = st.rain_window
        win[:-1] = win[1:]
        win[-1] = rain
        inflow = self._gain * float(np.dot(self._kernel, win))
        lvl = st.level + inflow - station["response_k"] * (st.level - station["base_level"])
        rng = np.random.default_rng((int(ts.timestamp()) * 7919 + station["station_id"]) % (2**32))
        lvl += rng.normal(0, 0.0015)
        lvl = max(lvl, 0.0)
        st.level = lvl
        st.last_ts = ts
        return ts, round(lvl, 4), rain

    def _generate_rows(self, station: dict, st: _StationState, from_ts: datetime,
                       to_ts: datetime) -> pd.DataFrame:
        rows = []
        ts = from_ts
        while ts <= to_ts:
            rows.append(self._advance(st, station, ts))
            ts = ts + timedelta(minutes=self._step)
        return pd.DataFrame(rows, columns=["ts", "level", "rain_observed"])

    # ------------------------------------------------------------------
    # R1：滚动 tick（样本时间戳 = floor(now/step)，相对时间）
    # ------------------------------------------------------------------
    def tick(self, now: Optional[datetime] = None) -> int:
        """推进一轮采样：为每个启用点位补齐 [last_ts+step, floor(now/step)] 的样本。"""
        now = now or datetime.now()
        target = floor_to_step(now, self._step)
        written = 0
        with self._lock:
            for station in self._stations():
                try:
                    written += self._tick_station(station, target, cap=self._max_tick_steps)
                except Exception:
                    logger.exception(
                        "rolling tick failed for station %s; state will be re-seeded next tick",
                        station.get("station_id"),
                    )
                    self._state.pop(station.get("station_id"), None)  # 自愈：下轮重新播种
        return written

    def _tick_station(self, station: dict, target: datetime, cap: int) -> int:
        sid = station["station_id"]
        st = self._state.get(sid)
        if st is None:
            st = self._seed_state(sid, station["base_level"])
            self._state[sid] = st
        if st.last_ts is None:
            st.last_ts = target - timedelta(minutes=self._step)
        from_ts = st.last_ts + timedelta(minutes=self._step)
        if from_ts > target:
            return 0
        # 追赶上限：差距过大时只补最近 cap 步（时间戳仍取相对时间，保证新鲜）
        earliest = target - timedelta(minutes=(cap - 1) * self._step)
        if from_ts < earliest:
            from_ts = earliest
            st.last_ts = from_ts - timedelta(minutes=self._step)
            st.level = station["base_level"]  # 长缺口后从基流水位重新起推
        df = self._generate_rows(station, st, from_ts, target)
        if df.empty:
            return 0
        self._append_rows(sid, df)
        return len(df)

    def _append_rows(self, station_id: int, new_df: pd.DataFrame) -> None:
        old = self._ts_repo.read_series(station_id)
        parts = [df for df in (old, new_df) if not df.empty]
        if not parts:
            return
        merged = pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0].copy()
        merged = merged.drop_duplicates(subset="ts", keep="last").sort_values("ts")
        self._ts_repo.write_series(station_id, merged)

    # ------------------------------------------------------------------
    # R3：自愈（健康检查发现 STALE 时调用）
    # ------------------------------------------------------------------
    def catch_up(self, now: Optional[datetime] = None) -> int:
        """清空内存态后从 Parquet 最后样本补齐到当前时刻（自愈入口）。"""
        now = now or datetime.now()
        target = floor_to_step(now, self._step)
        written = 0
        with self._lock:
            for station in self._stations():
                try:
                    self._state.pop(station["station_id"], None)  # 强制重新播种
                    written += self._tick_station(station, target, cap=self._max_catch_up_steps)
                except Exception:
                    logger.exception("self-heal catch-up failed for station %s", station["station_id"])
        logger.info(
            "generator self-heal catch-up done: %s samples (event=self_heal)", written,
            extra={"event": "self_heal", "samples": written},
        )
        return written

    def freshness_age_minutes(self, now: Optional[datetime] = None) -> Optional[float]:
        """全部启用点位中最旧样本的滞后分钟数（健康检查新鲜度口径）。"""
        now = now or datetime.now()
        worst = None
        for station in self._stations():
            latest = self._ts_repo.latest(station["station_id"])
            if not latest or not latest.get("ts"):
                return 9999.0
            age = (now - pd.Timestamp(latest["ts"]).to_pydatetime()).total_seconds() / 60.0
            age = max(0.0, age)  # 时钟轻微偏移时不出负数
            worst = age if worst is None else max(worst, age)
        return worst

    def last_sample_info(self) -> Optional[dict]:
        """最新一条样本（演示口径：六站一致滚动，取 id 最大站点即可）。"""
        stations = self._stations()
        if not stations:
            return None
        return self._ts_repo.latest(stations[-1]["station_id"])

    # ------------------------------------------------------------------
    # P1-7：极端降雨事件注入（演示钥匙）
    # ------------------------------------------------------------------
    def inject_event(self, station_id: int, intensity: str,
                     now: Optional[datetime] = None) -> dict:
        """注入一场暴雨：观测雨强进入后续 tick，同步写入未来真值供预报取数。"""
        if intensity not in INTENSITY_PRESETS:
            raise ValueError(f"不支持的强度档位 {intensity}，可选 {list(INTENSITY_PRESETS)}")
        preset = INTENSITY_PRESETS[intensity]
        now = now or datetime.now()
        start = floor_to_step(now, self._step) + timedelta(minutes=self._step)
        steps = max(1, int(preset["duration_minutes"] / self._step))
        end = start + timedelta(minutes=(steps - 1) * self._step)
        seed = (int(now.timestamp()) * 131 + station_id) % (2**32)
        shape = storm_shape(steps, preset["peak_mm"], np.random.default_rng(seed))

        with self._lock:
            self._event_seq += 1
            event = {
                "event_id": f"RAIN-{self._event_seq:04d}",
                "station_id": station_id,
                "intensity": intensity,
                "intensity_label": preset["label"],
                "peak_mm_per_step": preset["peak_mm"],
                "duration_minutes": preset["duration_minutes"],
                "start_ts": start,
                "end_ts": end,
                "shape": shape,
                "injected_at": now,
            }
            self._events.setdefault(station_id, []).append(event)
            self._write_future_truth(station_id, start, shape)
        logger.info(
            "extreme rain event injected: station=%s intensity=%s event=%s",
            station_id, intensity, event["event_id"],
            extra={"event": "rain_inject", "station_id": station_id},
        )
        return event

    def _write_future_truth(self, station_id: int, start: datetime, shape: np.ndarray) -> None:
        """把注入事件的雨真值写入 station_{id}_future.parquet（预报取数来源）。"""
        path = Path(self._ts_repo.dir) / f"station_{station_id}_future.parquet"
        ts = pd.date_range(start=start, periods=len(shape),
                           freq=f"{self._step}min")
        add = pd.DataFrame({"ts": ts, "rain_true": shape})
        if path.exists():
            try:
                cur = pd.read_parquet(path)
                cur["ts"] = pd.to_datetime(cur["ts"])
                merged = pd.concat([cur, add], ignore_index=True)
                merged = merged.groupby("ts", as_index=False)["rain_true"].sum()
                merged = merged.sort_values("ts")
                merged.to_parquet(path, index=False)
                return
            except Exception:
                logger.exception("extend future truth failed; rewriting with event only")
        add.to_parquet(path, index=False)

    def active_events(self, limit: int = 20) -> list:
        """当前生效/近期注入的事件（注入接口 GET 用）。"""
        rows = []
        for sid, evs in self._events.items():
            rows.extend(evs)
        rows.sort(key=lambda e: e["injected_at"], reverse=True)
        return [
            {
                "event_id": e["event_id"],
                "station_id": e["station_id"],
                "intensity": e["intensity"],
                "intensity_label": e["intensity_label"],
                "peak_mm_per_step": e["peak_mm_per_step"],
                "duration_minutes": e["duration_minutes"],
                "start_ts": e["start_ts"],
                "end_ts": e["end_ts"],
                "injected_at": e["injected_at"],
            }
            for e in rows[:limit]
        ]
