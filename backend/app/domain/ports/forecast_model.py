"""ForecastModel Port（04 §5.4 / 05 §4.2）。

ForecastResult 结构与将来真模型完全一致：points / peak_level / peak_time /
confidence_interval / model_id / inference_ms。占位模型（Naive / LinearResponse）
返回结构一比一相同（07 验收 · 占位层）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol, runtime_checkable

import pandas as pd


@dataclass
class ModelMeta:
    name: str
    version: str
    model_type: str
    description: str = ""


@dataclass
class ForecastPointResult:
    t: datetime
    level_raw: float
    lower: float
    upper: float


@dataclass
class ForecastResult:
    points: list = field(default_factory=list)  # list[ForecastPointResult]
    peak_level: float = 0.0
    peak_time: Optional[datetime] = None
    confidence_interval: dict = field(default_factory=dict)
    model_id: str = ""
    inference_ms: int = 0
    # 模型附加说明（写入 remark，供前端/Agent 解释）
    notes: list = field(default_factory=list)


@runtime_checkable
class ForecastModel(Protocol):
    name: str
    version: str
    model_type: str

    def fit(self, history: pd.DataFrame) -> None: ...
    def predict(self, window: pd.DataFrame, horizon_min: int) -> ForecastResult: ...
    def describe(self) -> ModelMeta: ...
