"""NaiveModel 持久性模型（✅ 占位实现，兜底）。

level(t+h) = level(t) + (base_level − level(t)) × decay × h
任何情况下都能跑，用于验证环境与降级（Agent-A D5）。
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from app.infrastructure.forecast.params import ModelParams, effective_ci
from app.domain.ports.forecast_model import (
    ForecastPointResult,
    ForecastResult,
    ModelMeta,
)


class NaiveModel:
    name = "NaiveModel"
    version = "v1.0"
    model_type = "naive"

    def __init__(self, params: ModelParams):
        self.params = params
        self._recent_rmse: float | None = None  # noqa: UP045（兼容 3.11 语法用 Optional）

    def fit(self, history: pd.DataFrame) -> None:
        # 持久性模型无训练过程；保留 fit 以满足统一接口（FR-3.7）
        return None

    def set_recent_rmse(self, rmse: float | None) -> None:
        self._recent_rmse = rmse

    def predict(self, window: pd.DataFrame, horizon_min: int) -> ForecastResult:
        import time as _time

        t0 = _time.perf_counter()
        levels_valid = window["level"].dropna()
        if levels_valid.empty:
            from app.core.errors import BizError

            raise BizError(1301, "历史数据不足，无法预测（DATA_NOT_ENOUGH）")

        step_min = 5
        n_steps = max(1, int(horizon_min // step_min))
        idx_last = levels_valid.index[-1]
        level_now = float(levels_valid.iloc[-1])
        base = self.params.base_level
        decay = self.params.decay

        start_ts = pd.Timestamp(window.loc[idx_last, "ts"])
        points: list[ForecastPointResult] = []
        for k in range(1, n_steps + 1):
            h = k * step_min / 60.0
            lvl = level_now + (base - level_now) * decay * h
            half = effective_ci(self.params.ci_base, self._recent_rmse, h,
                                self.params.ci_sqrt_factor)
            points.append(
                ForecastPointResult(
                    t=(start_ts + timedelta(minutes=k * step_min)).to_pydatetime(),
                    level_raw=round(float(lvl), 4),
                    lower=round(float(lvl - half), 4),
                    upper=round(float(lvl + half), 4),
                )
            )
        peak = max(points, key=lambda p: p.level_raw)
        result = ForecastResult(
            points=points,
            peak_level=peak.level_raw,
            peak_time=peak.t,
            confidence_interval={
                "lower": min(p.lower for p in points),
                "upper": max(p.upper for p in points),
            },
            model_id=f"{self.model_type}:{self.version}",
            inference_ms=int((_time.perf_counter() - t0) * 1000),
            notes=["持久性模型：水位向基流缓慢回落（占位实现，接口与真模型一致）"],
        )
        return result

    def describe(self) -> ModelMeta:
        return ModelMeta(
            name=self.name, version=self.version, model_type=self.model_type,
            description="持久性占位模型：当前水位向基准水位缓慢回落（纯 numpy）",
        )
