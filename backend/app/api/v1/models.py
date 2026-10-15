"""模型接口：列表 / 激活（S7 模型可插拔）/ 参数校准（V1.3 做实）。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.deps import Container, container_dep
from app.core.errors import BizError
from app.core.response import ok

router = APIRouter(prefix="/models", tags=["models"])


@router.get("")
def list_models(c: Container = Depends(container_dep)):
    """GET /api/v1/models —— 模型版本列表（含占位模型与标定参数）。"""
    import json as _json

    out = []
    for m in c.model_repo.list():
        cfg = {}
        if m.algorithm_config:
            try:
                cfg = _json.loads(m.algorithm_config)
            except (ValueError, TypeError):
                cfg = {}
        out.append({
            "model_id": m.model_id,
            "model_name": m.model_name,
            "version": m.version,
            "model_type": m.model_type,
            "active": bool(m.active),
            "rmse": m.rmse,
            "mae": m.mae,
            "model_file": m.model_file,
            "algorithm_config": cfg,
            "activatable": bool(m.model_file),  # 占位版本不可激活
        })
    return ok(out)


@router.post("/{model_id}/activate")
def activate_model(model_id: int, c: Container = Depends(container_dep)):
    """POST /api/v1/models/{id}/activate —— 切换当前模型（场景 S7）。"""
    row = c.model_repo.activate(model_id)
    if row is None:
        raise BizError(1201, f"模型 {model_id} 不存在或为占位版本，不可激活（MODEL_NOT_READY）")
    return ok({
        "model_id": row.model_id,
        "model_type": row.model_type,
        "version": row.version,
        "active": True,
        "note": "模型已切换：下一次预测生效，业务代码未改动（模型可插拔演示）",
    })


@router.post("/{model_id}/calibrate-params")
def calibrate_params(
    model_id: int,
    station_id: int = Query(..., description="标定目标监测点"),
    c: Container = Depends(container_dep),
):
    """POST /api/v1/models/{id}/calibrate-params —— 参数校准（V1.3 做实）。

    网格搜索标定 LinearResponseModel 的 gain/response_k，返回前后误差对比。
    """
    out = c.calibration_service.calibrate_params(model_id, station_id)
    return ok(out)
