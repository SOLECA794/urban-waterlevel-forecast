"""LightGBM 模型（🔶 占位留白）：实现位已留好，本期不安装（ADR-6）。

占位 ≠ 缺失：完整接口签名 + 合规行为（抛出可解释错误）+ EXT-POINT 标注。
将来填充：pip install lightgbm 后实现 fit/predict，配置 forecast.model_type: lgbm 即切换。
"""
from __future__ import annotations

import pandas as pd

from app.core.errors import BizError
from app.domain.ports.forecast_model import ForecastResult, ModelMeta
from app.infrastructure.forecast.params import ModelParams


class LgbmModel:
    """LightGBM 真模型基线（本期占位，model_type: lgbm）。"""

    name = "LgbmModel"
    version = "v0.0-placeholder"
    model_type = "lgbm"

    def __init__(self, params: ModelParams):
        self.params = params

    def fit(self, history: pd.DataFrame) -> None:
        # EXT-POINT(MODEL): LightGBM 训练——特征工程输出（滑动窗口统计/累计降雨/
        # 雨强峰值/水位变化率/预见期预报量/时间特征）→ lgb.train；
        # 模型文件落 checkpoints/，新版本写 model 表并经人工确认后激活（FR-6.3）。
        raise BizError(
            1201,
            "LightGBM 模型为占位实现（MODEL_NOT_READY）："
            "按 EXT-POINT(MODEL) 说明安装 lightgbm 并实现 fit/predict",
        )

    def predict(self, window: pd.DataFrame, horizon_min: int) -> ForecastResult:
        # EXT-POINT(MODEL): LightGBM 推理——返回结构与真模型完全一致
        # （points / peak_level / confidence_interval / model_id / inference_ms）。
        raise BizError(
            1201,
            "LightGBM 模型为占位实现（MODEL_NOT_READY）："
            "按 EXT-POINT(MODEL) 说明安装 lightgbm 并实现 fit/predict",
        )

    def describe(self) -> ModelMeta:
        return ModelMeta(
            name=self.name, version=self.version, model_type=self.model_type,
            description="LightGBM 占位实现位（EXT-POINT(MODEL)：安装后填充）",
        )
