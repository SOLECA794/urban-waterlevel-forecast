"""模拟事件注入接口（评审 P1-7「演示钥匙」）——纯增量新增，不影响既有契约。

用途：演示时无法被动等待模拟器自己下雨，通过本接口主动注入一场极端降雨：
  1) 观测链路：滚动生成器后续 tick 落入暴雨雨强 → 实况水位抬头；
  2) 预测链路：同一份雨真值写入 *_future.parquet → 降雨预报可见 →
     预测曲线越过阈值 → 产生带提前量的预警。

安全：需要演示钥匙（config datasource.demo_key，环境变量 WL_DEMO_KEY 覆盖），
防止演示环境被误触发；真实数据源下本接口应整体下线（EXT-POINT 已标注）。
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.deps import Container, container_dep
from app.core.errors import BizError
from app.core.logging import get_logger
from app.core.response import ok

router = APIRouter(prefix="/sim", tags=["simulation"])

logger = get_logger("api.sim")

# 强度档位（与 RollingSimGenerator.INTENSITY_PRESETS 一致，接口层做入参校验）
_ALLOWED_INTENSITY = {"light", "moderate", "heavy", "extreme"}


class SimEventIn(BaseModel):
    station_id: int = Field(..., description="监测点 ID")
    intensity: str = Field("extreme", description="强度档位：light/moderate/heavy/extreme")
    demo_key: str = Field(..., description="演示钥匙（config datasource.demo_key）")


@router.post("/events")
def inject_rain_event(body: SimEventIn, c: Container = Depends(container_dep)):
    """POST /api/v1/sim/events —— 注入极端降雨事件（演示钥匙校验）。

    注入成功后立即为该站触发一轮预测（后台线程），让预警/提前量在
    演示现场数十秒内可见，而不必等下一个滚动预测周期。
    """
    # 演示钥匙校验（错误钥匙一律拒绝，避免误触发演示数据）
    if body.demo_key != c.settings.datasource.demo_key:
        raise BizError(1403, "演示钥匙不正确（DEMO_KEY_INVALID）")
    if body.intensity not in _ALLOWED_INTENSITY:
        raise BizError(400, f"不支持的强度档位 {body.intensity}，可选 {sorted(_ALLOWED_INTENSITY)}（PARAM_INVALID）")
    station = c.station_repo.get(body.station_id)
    if station is None:
        raise BizError(1102, f"监测点 {body.station_id} 不存在（STATION_NOT_FOUND）")
    if not station.enabled:
        raise BizError(1101, f"监测点 {station.station_code} 已停用（STATION_STATE_INVALID）")

    event = c.generator.inject_event(body.station_id, body.intensity)

    # 后台触发一轮该站预测（1h/3h），演示叙事：注入 → 水位抬升 → 预警
    prediction_triggered = True

    def _predict_async():
        try:
            c.forecast_service.run_prediction(body.station_id, 1)
            c.forecast_service.run_prediction(body.station_id, 3)
        except Exception:
            logger.warning("post-inject prediction failed", exc_info=True)

    threading.Thread(target=_predict_async, daemon=True).start()

    return ok({
        "event_id": event["event_id"],
        "station_id": body.station_id,
        "station_code": station.station_code,
        "station_name": station.station_name,
        "intensity": event["intensity"],
        "intensity_label": event["intensity_label"],
        "peak_mm_per_step": event["peak_mm_per_step"],
        "duration_minutes": event["duration_minutes"],
        "start_ts": event["start_ts"],
        "end_ts": event["end_ts"],
        "injected_at": event["injected_at"],
        "note": "观测雨强将从下一采样周期起计入；降雨预报已可见本次事件，滚动预测正在执行",
        "prediction_triggered": prediction_triggered,
    })


@router.get("/events")
def list_sim_events(
    limit: int = Query(20, ge=1, le=100),
    c: Container = Depends(container_dep),
):
    """GET /api/v1/sim/events —— 近期注入的模拟事件列表（只读）。"""
    return ok(c.generator.active_events(limit=limit))
