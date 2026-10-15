"""预测接口：发起预测 / 预测详情 / Agent-A 编排决策。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.deps import Container, container_dep
from app.core.errors import BizError
from app.core.response import ok, page
from app.schemas.payloads import PredictIn

router = APIRouter(tags=["forecasts"])


@router.get("/forecasts")
def list_forecasts(
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(10, ge=1, le=50),
    station_id: Optional[int] = Query(None),
    c: Container = Depends(container_dep),
):
    """GET /api/v1/forecasts —— 全局最近预测记录（总览页）。

    说明：05 接口表未列出全局预测列表；总览页「最近预测记录」（04 §6.1）需要，
    为前端必要补充（已在偏离记录中说明）。
    """
    rows, total = c.forecast_repo.list_all(page_no, page_size, station_id)
    names = {s.station_id: s for s in c.station_repo.list()}
    items = [
        {
            "forecast_id": f.forecast_id,
            "station_id": f.station_id,
            "station_code": names[f.station_id].station_code if f.station_id in names else None,
            "station_name": names[f.station_id].station_name if f.station_id in names else None,
            "model_type": f.model_type,
            "lead_hours": f.lead_hours,
            "predict_time": f.predict_time,
            "peak_level": f.peak_level,
            "peak_time": f.peak_time,
            "rmse": f.rmse,
            "degraded": bool(f.degraded),
            "remark": f.remark,
        }
        for f in rows
    ]
    return ok(page(items, total, page_no, page_size))


@router.post("/stations/{station_id}/predict")
def predict(station_id: int, body: PredictIn, c: Container = Depends(container_dep)):
    """POST /api/v1/stations/{id}/predict —— 发起水位预测（真流程 + 占位模型）。

    返回结构与将来真模型完全一致：points / peak_level / confidence_interval /
    decision（Agent-A 编排决策）+ alert（研判结果）。
    """
    out = c.forecast_service.run_prediction(
        station_id, body.lead_hours, model_id=body.model_id
    )
    return ok(out)


@router.get("/stations/{station_id}/forecasts/{forecast_id}")
def forecast_detail(station_id: int, forecast_id: int, c: Container = Depends(container_dep)):
    """GET /api/v1/stations/{id}/forecasts/{fid} —— 预测详情（逐点曲线复现）。"""
    f = c.forecast_repo.get(forecast_id)
    if f is None or f.station_id != station_id:
        raise BizError(1404, f"预测 {forecast_id} 不存在（RESOURCE_NOT_FOUND）")
    points = c.forecast_repo.get_points(forecast_id)
    decision = c.forecast_repo.get_decision(forecast_id)
    import json as _json

    return ok({
        "forecast_id": f.forecast_id,
        "station_id": f.station_id,
        "model_id": f.model_id,
        "model_type": f.model_type,
        "lead_hours": f.lead_hours,
        "predict_time": f.predict_time,
        "horizon_end_time": f.horizon_end_time,
        "peak_level": f.peak_level,
        "peak_time": f.peak_time,
        "rmse": f.rmse,
        "mae": f.mae,
        "degraded": bool(f.degraded),
        "remark": f.remark,
        "points": [
            {"t": p.target_time, "level_raw": p.pred_level_raw, "level": p.pred_level,
             "revision": p.revision, "lower": p.lower_bound, "upper": p.upper_bound,
             "actual_level": p.actual_level}
            for p in points
        ],
        "decision": {
            "selected_model": decision.selected_model,
            "fusion_weights": _json.loads(decision.fusion_weights) if decision.fusion_weights else {},
            "revision_alpha": decision.revision_alpha,
            "ci_scale": decision.ci_scale,
            "degraded": bool(decision.degraded),
            "reason": decision.reason,
        } if decision else None,
    })


@router.get("/forecasts/{forecast_id}/decision")
def forecast_decision(forecast_id: int, c: Container = Depends(container_dep)):
    """GET /api/v1/forecasts/{id}/decision —— Agent-A 编排决策详情（D1–D5 全可解释）。"""
    decision = c.forecast_repo.get_decision(forecast_id)
    if decision is None:
        f = c.forecast_repo.get(forecast_id)
        if f is None:
            raise BizError(1404, f"预测 {forecast_id} 不存在（RESOURCE_NOT_FOUND）")
        raise BizError(1404, f"预测 {forecast_id} 无编排决策记录（RESOURCE_NOT_FOUND）")
    import json as _json

    return ok({
        "forecast_id": forecast_id,
        "decision_id": decision.decision_id,
        "selected_model": decision.selected_model,
        "fusion_weights": _json.loads(decision.fusion_weights) if decision.fusion_weights else {},
        "revision_alpha": decision.revision_alpha,
        "ci_scale": decision.ci_scale,
        "degraded": bool(decision.degraded),
        "reason": decision.reason,
        "create_time": decision.create_time,
    })
