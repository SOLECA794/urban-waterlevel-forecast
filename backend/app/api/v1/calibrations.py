"""校准任务接口（🔶 重训占位留白）：返回受理回执，状态持久为 pending。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import Container, container_dep
from app.core.response import ok
from app.schemas.payloads import CalibrationCreateIn

router = APIRouter(prefix="/calibrations", tags=["calibrations"])


@router.post("")
def create_calibration(body: CalibrationCreateIn, c: Container = Depends(container_dep)):
    """POST /api/v1/calibrations —— 发起校准任务（重训占位）。

    # EXT-POINT(MODEL): 模型重训流水线——本期返回 calibration_id + status=pending，
    # 训练执行位待填充（特征窗口 → lgb/prophet 训练 → 新版本入库 → 人工确认激活）。
    """
    out = c.calibration_service.create_retrain_task(body.station_id, body.base_model_id)
    return ok(out)


@router.get("/{calibration_id}")
def get_calibration(calibration_id: int, c: Container = Depends(container_dep)):
    """GET /api/v1/calibrations/{id} —— 查询校准任务状态（占位：pending）。"""
    return ok(c.calibration_service.get_task(calibration_id))
