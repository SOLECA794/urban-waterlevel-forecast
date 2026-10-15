"""模拟数据源（✅ 真实现）。

双路输出（V1.3 §8.1）：
  rain_observed(t)          实况降雨（来自 Parquet 历史序列）
  rain_forecast(t_issue,h)  在 t_issue 时刻对未来 h 小时的预报

预报误差建模，体现「预见期越长越不准」：
  rain_forecast(t,h) = rain_true(t+h) · (1 + ε(h))
  ε(h) ~ N(bias(h), σ(h))，σ(h) 与 |bias(h)| 随 h 单调增大；
  并加入对峰值的系统性低估（真实数值预报对强对流的典型缺陷）。

将来接真实 NWP：只需替换 get_rain_forecast 的取数实现（EXT-POINT 已标注）。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from app.core.logging import get_logger
from app.domain.ports.data_source import DataBlock, SourceInfo, SourceStatus

logger = get_logger("datasource.simulated")

# R2（评审 §2）：数据源链路状态与「数据新鲜度」分离判定。
# 链路状态可以是 STREAMING，但样本滞后超过阈值必须改判 STALE——
# 这是「监控系统自己没发现系统坏了」误报的修复点。
STALE_STATUS = "STALE"


def evaluate_source_status(link_status: str, data_age_min: Optional[float],
                           stale_after_minutes: float = 30.0) -> tuple:
    """纯函数：按链路状态 + 数据新鲜度给出对外状态与说明（可单测）。

    返回 (status, detail)。链路异常优先；链路正常但样本滞后 > 阈值 → STALE。
    """
    if link_status in ("ERROR", "DISCONNECTED"):
        return link_status, "数据源链路异常（FR-1.3）"
    if data_age_min is None:
        return link_status, "暂无样本（等待首次采集）"
    if data_age_min > stale_after_minutes:
        return STALE_STATUS, f"观测数据滞后 {data_age_min:.0f} 分钟（超过 {stale_after_minutes:.0f} 分钟阈值，生成器可能停滞）"
    return link_status or "READY", "模拟数据源运行正常"


class SimulatedSource:
    """模拟数据源：读取 Parquet 历史序列 + 按需生成降雨预报序列。"""

    name = "simulated"

    def __init__(self, ts_repo, interval_minutes: int = 5, missing_cycles: int = 3,
                 stale_after_minutes: float = 30.0):
        self._ts_repo = ts_repo
        self._interval = interval_minutes
        self._missing_cycles = missing_cycles
        self._stale_after_minutes = stale_after_minutes
        self._status = SourceStatus.DISCONNECTED
        self._last_error: Optional[str] = None
        self._info: Optional[SourceInfo] = None

    # --- 生命周期（FR-1.5 统一适配接口） ---
    async def connect(self, config: dict) -> SourceInfo:
        self._status = SourceStatus.CONNECTING
        try:
            ids = self._ts_repo.station_ids()
            self._info = SourceInfo(
                source_code="SIM-001",
                source_name="模拟数据源（实况+预报双路）",
                type="simulated",
                stations=ids,
                interval_minutes=self._interval,
            )
            self._status = SourceStatus.READY
            return self._info
        except Exception as exc:  # 断流/异常置 ERROR（FR-1.3）
            self._status = SourceStatus.ERROR
            self._last_error = str(exc)
            raise

    async def disconnect(self) -> bool:
        self._status = SourceStatus.DISCONNECTED
        return True

    async def start_stream(self, sink) -> bool:
        if self._status not in (SourceStatus.READY, SourceStatus.STREAMING):
            return False
        self._status = SourceStatus.STREAMING
        return True

    async def stop_stream(self) -> bool:
        if self._status == SourceStatus.STREAMING:
            self._status = SourceStatus.READY
        return True

    async def get_status(self) -> SourceStatus:
        return self._status

    @property
    def status_value(self) -> str:
        """同步读取状态（应用层用，避免事件循环内嵌套 asyncio）。"""
        return self._status.value

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    # --- 数据访问 ---
    async def get_series(self, station_id: int, hours: int) -> pd.DataFrame:
        end = datetime.now()
        start = end - timedelta(hours=hours)
        return self._ts_repo.read_series(station_id, start=start, end=end)

    def get_series_sync(self, station_id: int, hours: int) -> pd.DataFrame:
        end = datetime.now()
        start = end - timedelta(hours=hours)
        return self._ts_repo.read_series(station_id, start=start, end=end)

    def latest(self, station_id: int) -> Optional[dict]:
        return self._ts_repo.latest(station_id)

    # --- 降雨预报双路（支撑 6h/12h 预见期，V1.3） ---
    def _future_truth(self, station_id: int) -> pd.DataFrame:
        """未来 12h 降雨真值（生成器产出，仅供模拟预报用——模拟源的「上帝视角」）。"""
        path = self._ts_repo.dir / f"station_{station_id}_future.parquet"
        if not path.exists():
            # 新建点位尚无未来真值文件（如设置页新增监测点）：返回空表而非让 .dt 崩溃
            return pd.DataFrame({
                "ts": pd.Series([], dtype="datetime64[ns]"),
                "rain_true": pd.Series([], dtype=float),
            })
        df = pd.read_parquet(path)
        df["ts"] = pd.to_datetime(df["ts"])
        return df

    def get_rain_forecast(
        self, station_id: int, t_issue: datetime, hours: int, step_minutes: int = 5
    ) -> pd.DataFrame:
        """产出 [t_issue, t_issue+hours] 的逐步降雨预报。

        确定性随机（以 station+issue 时间为种子），保证同一 issue 重复取数稳定。
        """
        # ---- 优先真接 Open-Meteo 真实降雨预报（去 mock） ----
        try:
            from app.infrastructure.datasource.openmeteo_client import get_real_rain_forecast
            real = get_real_rain_forecast(station_id, t_issue, hours, step_minutes)
            if real is not None and not real.empty:
                return real
        except Exception:
            pass  # 失败走模拟 fallback

        truth = self._future_truth(station_id)
        future_ts = pd.date_range(t_issue, periods=int(hours * 60 / step_minutes),
                                  freq=f"{step_minutes}min")
        seed = int(pd.Timestamp(t_issue).timestamp()) * 1000 + int(station_id)
        rng = np.random.default_rng(abs(seed) % (2**32))

        true_map = dict(zip(truth["ts"].dt.floor("min"), truth["rain_true"].astype(float)))
        true_vals = np.array(
            [float(true_map.get(ts, 0.0)) for ts in future_ts], dtype=float
        )

        # ε(h)：偏差与波动随预见期单调增大 + 峰值系统性低估
        n = len(future_ts)
        h_norm = np.linspace(0.0, 1.0, n)  # 0 → 1（预见期归一化）
        bias = -0.10 * h_norm               # 系统性低估随预见期增大
        sigma = 0.12 + 0.38 * h_norm        # 波动随预见期增大
        eps = rng.normal(bias, sigma)
        factor = np.clip(1.0 + eps, 0.0, 1.6)

        # 峰值额外低估：对超过 5mm 的时步再打 0.8 折（强对流典型缺陷）
        peak_mask = true_vals > 5.0
        factor = np.where(peak_mask, factor * 0.8, factor)

        forecast_vals = np.round(true_vals * factor, 2)
        return pd.DataFrame({"ts": future_ts, "rain_forecast": forecast_vals})

    def source_status_payload(self, data_age_min: Optional[float] = None) -> dict:
        """健康检查数据源三态 + 新鲜度（R2：状态纳入 STALE 判定）。"""
        status, detail = evaluate_source_status(
            self._status.value, data_age_min,
            stale_after_minutes=self._stale_after_minutes,
        )
        return {
            "type": "simulated",
            "status": status,
            "detail": self._last_error or detail,
            "data_age_min": round(data_age_min, 1) if data_age_min is not None else None,
        }
