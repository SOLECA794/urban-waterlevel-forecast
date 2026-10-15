"""LinearResponseModel 降雨线性响应模型（✅ 占位实现，主力演示模型）。

Δlevel(t+h) = Σᵢ wᵢ·rain(t−i) − k·(level − base)
体现「降雨驱动 + 汇流滞后 + 退水」的正确业务形态；约二十行 numpy 代码。

窗口约定（应用层构造）：window 含列 ts / level / rain_observed / rain_forecast，
其中未来步的行 level 为 NaN、rain_forecast 有值；历史步反之。
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from app.domain.ports.forecast_model import (
    ForecastPointResult,
    ForecastResult,
    ModelMeta,
)
from app.infrastructure.forecast.params import ModelParams, effective_ci


class LinearResponseModel:
    name = "LinearResponseModel"
    version = "v1.0"
    model_type = "linear_response"

    def __init__(self, params: ModelParams):
        self.params = params
        self._recent_rmse: float | None = None  # noqa: UP045

    def fit(self, history: pd.DataFrame) -> None:
        # 线性响应模型参数由配置/标定给出（calibrate_params），fit 保留为接口一致性
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
        kernel = self.params.kernel()
        gain = self.params.gain
        k_rec = self.params.response_k
        base = self.params.base_level

        # 有效降雨输入：未来步取降雨预报（6h/12h 必需），历史步取实况
        rain_fc = window["rain_forecast"] if "rain_forecast" in window.columns else pd.Series(
            index=window.index, dtype=float
        )
        rain = rain_fc.fillna(window["rain_observed"]).fillna(0.0).to_numpy(dtype=float)

        level_now = float(levels_valid.iloc[-1])
        start_ts = pd.Timestamp(levels_valid.index[-1]) if isinstance(
            levels_valid.index[-1], pd.Timestamp
        ) else pd.Timestamp(window.loc[levels_valid.index[-1], "ts"])
        hist_len = len(levels_valid)  # 历史步数（与 rain 前段对齐）

        # 递推：level(j) = level(j-1) + gain·Σᵢ wᵢ·rain(t+j−i) − k·(level(j-1) − base)
        levels: list[float] = []
        lvl = level_now
        for j in range(1, n_steps + 1):
            idx = hist_len - 1 + j  # t+j 时刻在 rain 数组中的下标
            lo = idx - len(kernel) + 1
            seg = rain[max(0, lo): idx + 1]
            if len(seg) < len(kernel):
                seg = np.pad(seg, (len(kernel) - len(seg), 0))
            inflow = float(gain * np.dot(kernel, seg[-len(kernel):]))
            lvl = lvl + inflow - k_rec * (lvl - base)
            levels.append(max(float(lvl), 0.0))

        points: list[ForecastPointResult] = []
        for j, lvl in enumerate(levels, start=1):
            h = j * step_min / 60.0
            half = effective_ci(self.params.ci_base, self._recent_rmse, h,
                                self.params.ci_sqrt_factor)
            points.append(
                ForecastPointResult(
                    t=(start_ts + timedelta(minutes=j * step_min)).to_pydatetime(),
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
            notes=[
                "降雨线性响应：Σwᵢ·rain(t−i) 驱动上涨，k·(level−base) 退水（占位实现）",
            ],
        )
        return result

    def describe(self) -> ModelMeta:
        return ModelMeta(
            name=self.name, version=self.version, model_type=self.model_type,
            description="降雨线性响应占位模型：降雨驱动 + 汇流滞后 + 退水（纯 numpy）",
        )
