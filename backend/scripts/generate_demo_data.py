"""模拟数据生成/重置脚本（M2 · ADR-3）。

形态合理而非水文严格：与 LinearResponseModel 共用同一套响应参数递推生成
「降雨 → 滞后汇流上涨 → 退水」的水位序列；注入不同强度的暴雨事件制造
预警演示场景。

存储划分（避免未来真值泄漏为「实况」）：
  data/parquet/station_{id}.parquet          已观测段（ts / level / rain_observed）
  data/parquet/station_{id}_future.parquet   未来 12h 降雨真值（ts / rain_true），
                                             仅供 SimulatedSource 生成「降雨预报」用
对 S001/S002/S003/S006 注入「未来暴雨」（仅出现在预报中），
支撑 6h/12h 预见期与参考级预警演示（V1.3 §8.1）。

用法：
  python scripts/generate_demo_data.py            # 生成（已存在则跳过）
  python scripts/generate_demo_data.py --reset    # 清空重建
  python scripts/generate_demo_data.py --hours 96 --seed 42
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings, load_stations_yaml  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.infrastructure.forecast.params import build_kernel  # noqa: E402
from app.infrastructure.persistence.database import (  # noqa: E402
    create_engine_for,
    init_db,
    make_session_factory,
    reset_db,
)
from app.infrastructure.persistence.duckdb_analytics import DuckDBAnalytics  # noqa: E402
from app.infrastructure.persistence.parquet_store import ParquetTimeSeriesRepository  # noqa: E402
from app.infrastructure.persistence.sqlite_repo import StationRepository  # noqa: E402

STEP_MIN = 5


def storm_shape(steps: int, peak: float, rng) -> np.ndarray:
    """雨强时程曲线：快速起涨 → 峰值 → 指数退去。"""
    t = np.linspace(0, 1, steps)
    rise = 1 - np.exp(-t * 8)
    fall = np.exp(-np.maximum(t - 0.45, 0) * 6)
    shape = rise * fall
    jitter = rng.uniform(0.85, 1.15, steps)
    return np.round(np.clip(shape * peak * jitter, 0, None), 2)


def gen_rain(kind: str, hist_steps: int, future_steps: int, rng) -> np.ndarray:
    """基础毛毛雨 + 注入暴雨；storm1 峰值落在 now 前 ~1h，storm2 位于 now + 90min 起。"""
    total = hist_steps + future_steps
    rain = np.where(rng.random(total) < 0.06, rng.uniform(0.1, 0.6, total), 0.0)
    cfg = {"heavy": (36, 10.0), "moderate": (30, 5.0), "light": (24, 2.2)}.get(kind, (24, 2.2))
    dur, peak = cfg
    now_idx = hist_steps - 1
    if dur:
        start = max(0, now_idx - dur + 6)  # 尾部略越过 now，峰值在 now 前 ~1.2h
        end = min(total, start + dur)
        rain[start:end] += storm_shape(end - start, peak, rng)
    if kind in ("heavy", "moderate"):  # 未来暴雨：仅预报可见
        s2 = min(total - 1, now_idx + 18)
        e2 = min(total, s2 + 24)
        rain[s2:e2] += storm_shape(e2 - s2, 7.0, rng)
    return rain


def gen_station_series(kind: str, base_level: float, response_k: float, cfg_params,
                       hist_steps: int, future_steps: int, seed: int) -> tuple:
    """与 LinearResponseModel 同参递推（ADR-3）；返回 (观测段 df, 未来真值 df)。"""
    rng = np.random.default_rng(seed)
    rain = gen_rain(kind, hist_steps, future_steps, rng)
    kernel = build_kernel(cfg_params.kernel_len, cfg_params.kernel_tau)
    gain = cfg_params.gain

    level = np.zeros(hist_steps)
    lvl = base_level + rng.uniform(-0.02, 0.02)
    for i in range(hist_steps):
        lo = max(0, i - len(kernel) + 1)
        seg = rain[lo:i + 1]
        if len(seg) < len(kernel):
            seg = np.pad(seg, (len(kernel) - len(seg), 0))
        inflow = gain * float(np.dot(kernel, seg))
        lvl = lvl + inflow - response_k * (lvl - base_level)
        lvl += rng.normal(0, 0.0015)  # 传感器噪声
        level[i] = max(lvl, 0.0)

    end = datetime.now().replace(second=0, microsecond=0)
    ts_hist = pd.date_range(end=end, periods=hist_steps, freq=f"{STEP_MIN}min")
    obs = pd.DataFrame({"ts": ts_hist, "level": np.round(level, 4),
                        "rain_observed": np.round(rain[:hist_steps], 2)})
    miss_idx = rng.choice(hist_steps, size=max(1, hist_steps // 600), replace=False)
    obs.loc[miss_idx, "level"] = np.nan  # 偶发缺失（FR-2.3 短缺失插值）

    ts_future = pd.date_range(start=ts_hist[-1] + pd.Timedelta(minutes=STEP_MIN),
                              periods=future_steps, freq=f"{STEP_MIN}min")
    fut = pd.DataFrame({"ts": ts_future, "rain_true": np.round(rain[hist_steps:], 2)})
    return obs, fut


def main() -> int:
    parser = argparse.ArgumentParser(description="生成/重置模拟数据")
    parser.add_argument("--reset", action="store_true", help="清空并重建全部数据")
    parser.add_argument("--hours", type=int, default=None, help="历史序列长度（小时）")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    setup_logging()
    settings = get_settings()
    if args.hours:
        settings.datasource.history_hours = args.hours

    engine = create_engine_for(settings)
    if args.reset:
        settings.sqlite_file.unlink(missing_ok=True)
        for p in settings.parquet_dir.glob("station_*.parquet"):
            p.unlink()
        reset_db(engine)
    init_db(engine, settings, seed=True)

    ts_repo = ParquetTimeSeriesRepository(settings.parquet_dir)
    duck = DuckDBAnalytics(settings.parquet_dir)
    stations = StationRepository(make_session_factory(engine))
    cfg_params = settings.forecast.linear_response

    station_rows = stations.list()
    cfg = {s["station_code"]: s for s in load_stations_yaml().get("stations", [])}
    hist_steps = int(settings.datasource.history_hours * 60 / STEP_MIN)
    future_steps = int(12 * 60 / STEP_MIN)  # 未来 12h 降雨真值（供预报取数）

    print(f"生成模拟数据：{len(station_rows)} 个监测点 × {hist_steps} 步历史（5min）+ {future_steps} 步未来真值")
    for idx, st in enumerate(station_rows):
        meta = cfg.get(st.station_code, {})
        obs, fut = gen_station_series(
            kind=meta.get("storm", "light"),
            base_level=float(meta.get("base_level", st.base_level or 1.0)),
            response_k=float(meta.get("response_k", st.response_k or 0.01)),
            cfg_params=cfg_params,
            hist_steps=hist_steps,
            future_steps=future_steps,
            seed=args.seed + idx * 7 + 1,
        )
        ts_repo.write_series(st.station_id, obs)
        fut.to_parquet(settings.parquet_dir / f"station_{st.station_id}_future.parquet", index=False)
        peak = obs["level"].max()
        cur = obs["level"].dropna().iloc[-1]
        print(
            f"  {st.station_code} {st.station_name}: rows={len(obs)} "
            f"当前={cur:.2f}m 峰值={peak:.2f}m 未来12h雨量={fut['rain_true'].sum():.0f}mm"
        )
    print("完成：SQLite（业务）+ Parquet（观测序列/未来真值）已就绪，DuckDB 可直读分析。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
