"""模型注册与工厂：按 model_type 构造实现（配置驱动，S7 可插拔）。

新增模型三步：实现 ForecastModel Port + 在此注册 + 配置加一项，业务层不动。
"""
from __future__ import annotations

import json
from typing import Dict, Optional

from app.core.config import ForecastConfig
from app.core.errors import BizError
from app.domain.models import Model as ModelRow
from app.domain.models import Station
from app.infrastructure.forecast.linear_response import LinearResponseModel
from app.infrastructure.forecast.naive_model import NaiveModel
from app.infrastructure.forecast.params import ModelParams
from app.infrastructure.forecast.lgbm_model import LgbmModel
from app.infrastructure.forecast.nonlinear_model import NonlinearRunoffModel

_MODEL_TYPES = ("naive", "linear_response", "lgbm", "nonlinear")


def build_params(cfg: ForecastConfig, station: Optional[Station],
                 algorithm_config: Optional[str] = None,
                 station_id: Optional[int] = None) -> ModelParams:
    """构造模型参数：默认 ← 站点覆盖（base/response_k） ← 标定覆盖（calibration）。"""
    base = cfg.linear_response.model_dump()
    params = ModelParams(**base)
    if station is not None:
        if station.base_level is not None:
            params.base_level = float(station.base_level)
        if station.response_k is not None:
            params.response_k = float(station.response_k)
    if algorithm_config and station_id is not None:
        try:
            cfg_obj = json.loads(algorithm_config)
            calib = (cfg_obj.get("calibration") or {}).get(str(station_id))
            if calib:
                p = calib.get("params") or {}
                for key in ("gain", "response_k", "base_level", "kernel_len", "kernel_tau"):
                    if key in p:
                        setattr(params, key, p[key])
        except (ValueError, TypeError):
            pass
    return params


class ModelRegistry:
    """按需构造模型实例（占位模型无状态，构造开销可忽略）。"""

    def __init__(self, cfg: ForecastConfig):
        self._cfg = cfg

    def create(self, model_type: str, params: ModelParams):
        if model_type == "naive":
            return NaiveModel(params)
        if model_type == "linear_response":
            return LinearResponseModel(params)
        if model_type == "lgbm":
            return LgbmModel(params)  # 占位：predict 会抛 MODEL_NOT_READY
        if model_type == "nonlinear":
            return NonlinearRunoffModel(params)
        raise BizError(1202, f"未知模型类型 {model_type}（MODEL_INPUT_MISMATCH）")

    def create_from_row(self, row: ModelRow, station: Station) -> object:
        params = build_params(
            self._cfg, station, row.algorithm_config if row else None,
            station.station_id if station else None,
        )
        model = self.create(row.model_type if row else self._cfg.model_type, params)
        # EXT-POINT(MODEL): 真模型版本在此加载 model_file（checkpoints/）反序列化
        return model

    def available_types(self):
        return _MODEL_TYPES
