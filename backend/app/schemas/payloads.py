"""业务请求/响应契约。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


# --- 请求体 ---
class PredictIn(BaseModel):
    lead_hours: int = Field(..., description="预见期（1/3/6/12，受配置 lead_hours 约束）")
    model_id: Optional[int] = Field(None, description="指定模型（S7 演示用，缺省用激活模型）")


class StationCreateIn(BaseModel):
    station_name: str
    location: Optional[str] = None
    kind: Optional[str] = None
    threshold_blue: Optional[float] = None
    threshold_yellow: Optional[float] = None
    threshold_orange: Optional[float] = None
    threshold_red: Optional[float] = None
    base_level: Optional[float] = None
    response_k: Optional[float] = None
    enabled: bool = True


class StationUpdateIn(StationCreateIn):
    station_name: Optional[str] = None  # 更新时全部可省


class CalibrationCreateIn(BaseModel):
    station_id: Optional[int] = None
    base_model_id: Optional[int] = None


class AgentMessageIn(BaseModel):
    message: str
    confirm_token: Optional[str] = Field(
        None, description="L2 工具人工确认令牌（如 CONFIRMED）"
    )


class ToolInvokeIn(BaseModel):
    args: Dict[str, Any] = {}
    confirm_token: Optional[str] = None
