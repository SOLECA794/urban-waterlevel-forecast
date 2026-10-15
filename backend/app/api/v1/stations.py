"""监测点接口：列表 / 详情 / 增删改 / 时序 / 当前预警 / 预警记录 / 预测历史。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.deps import Container, container_dep
from app.core.response import ok, page
from app.schemas.payloads import StationCreateIn, StationUpdateIn

router = APIRouter(prefix="/stations", tags=["stations"])


def _series_payload(c: Container, station_id: int, hours: int, agg_minutes: int) -> dict:
    from datetime import datetime, timedelta

    df = c.ts_repo.read_series(station_id, start=datetime.now() - timedelta(hours=hours))
    if agg_minutes > 5 and not df.empty:
        # 分析查询走 DuckDB（V1.2 约定）：聚合重采样直读 Parquet
        f = (c.settings.parquet_dir / f"station_{station_id}.parquet").as_posix()
        try:
            df = c.duckdb.query(
                f"""
                SELECT date_trunc('minute', ts) - (epoch(ts) % {agg_minutes * 60}) * interval '1 second' AS ts,
                       arg_max(level, ts) AS level,
                       sum(rain_observed) AS rain_observed
                FROM read_parquet('{f}') GROUP BY 1 ORDER BY 1
                """
            )
        except Exception:
            df = c.ts_repo.read_series(station_id, start=datetime.now() - timedelta(hours=hours))
    points = [
        {"ts": str(r["ts"]),
         "level": None if r["level"] is None or r["level"] != r["level"] else round(float(r["level"]), 4),
         "rain_observed": round(float(r["rain_observed"] or 0), 3)}
        for _, r in df.iterrows()
    ]
    st = c.station_repo.get(station_id)
    return {
        "station_id": station_id,
        "station_code": st.station_code if st else None,
        "step_minutes": agg_minutes,
        "thresholds": {
            "blue": st.threshold_blue, "yellow": st.threshold_yellow,
            "orange": st.threshold_orange, "red": st.threshold_red,
        } if st else {},
        "points": points,
    }


@router.get("")
def list_stations(c: Container = Depends(container_dep)):
    """GET /api/v1/stations —— 监测点列表（按预警等级排序）。"""
    return ok(c.station_service.list_payload())


@router.post("")
def create_station(body: StationCreateIn, c: Container = Depends(container_dep)):
    """POST /api/v1/stations —— 创建监测点（FR-5.6 增）。"""
    return ok(c.station_service.create(**body.model_dump()))


@router.get("/{station_id}")
def station_detail(station_id: int, c: Container = Depends(container_dep)):
    """GET /api/v1/stations/{id} —— 详情 + 预警统计。"""
    return ok(c.station_service.detail_payload(station_id))


@router.put("/{station_id}")
def update_station(station_id: int, body: StationUpdateIn, c: Container = Depends(container_dep)):
    """PUT /api/v1/stations/{id} —— 修改（阈值改后下一次研判立即生效，FR-4.5）。"""
    data = body.model_dump(exclude_none=True)
    return ok(c.station_service.update(station_id, **data))


@router.delete("/{station_id}")
def delete_station(station_id: int, c: Container = Depends(container_dep)):
    """DELETE /api/v1/stations/{id} —— 删除（有追溯记录时退化为停用）。"""
    return ok(c.station_service.delete(station_id))


@router.get("/{station_id}/series")
def station_series(
    station_id: int,
    hours: int = Query(6, ge=1, le=168, description="回溯小时数"),
    agg_minutes: int = Query(5, ge=5, le=60, description="聚合粒度（分钟）"),
    c: Container = Depends(container_dep),
):
    """GET /api/v1/stations/{id}/series —— 历史水位/降雨序列（Parquet，聚合走 DuckDB）。"""
    return ok(_series_payload(c, station_id, hours, agg_minutes))


@router.get("/{station_id}/alert")
def station_current_alert(station_id: int, c: Container = Depends(container_dep)):
    """GET /api/v1/stations/{id}/alert —— 当前预警等级与原因。"""
    detail = c.station_service.detail_payload(station_id)
    latest = c.ts_repo.latest(station_id)
    return ok({
        "station_id": station_id,
        "current_level": latest["level"] if latest else None,
        "alert": detail["alert"],
        "thresholds": detail["thresholds"],
    })


@router.get("/{station_id}/alerts")
def station_alerts(
    station_id: int,
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(20, ge=1, le=100),
    level: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    is_reference: Optional[bool] = Query(None, description="参考级筛选（6h/12h）"),
    c: Container = Depends(container_dep),
):
    """GET /api/v1/stations/{id}/alerts —— 预警记录分页。"""
    rows, total = c.alert_repo.list_page(
        page=page_no, page_size=page_size, station_id=station_id,
        level=level, status=status, is_reference=is_reference,
    )
    items = [_alert_item(c, a) for a in rows]
    return ok(page(items, total, page_no, page_size))


@router.get("/{station_id}/forecasts")
def station_forecasts(
    station_id: int,
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(10, ge=1, le=50),
    c: Container = Depends(container_dep),
):
    """GET /api/v1/stations/{id}/forecasts —— 最近预测记录（前端详情页/总览页）。"""
    rows, total = c.forecast_repo.list_for_station(station_id, page_no, page_size)
    items = [_forecast_brief(c, f) for f in rows]
    return ok(page(items, total, page_no, page_size))


def _alert_item(c: Container, a) -> dict:
    st = c.station_repo.get(a.station_id)
    return {
        "alert_id": a.alert_id,
        "station_id": a.station_id,
        "station_code": st.station_code if st else None,
        "station_name": st.station_name if st else None,
        "forecast_id": a.forecast_id,
        "level": a.level,
        "reason": a.reason,
        "peak_level": a.peak_level,
        "peak_time": a.peak_time,
        "lead_minutes_advantage": a.lead_minutes_advantage,
        "is_reference": bool(a.is_reference),
        "lead_hours": a.lead_hours,
        "alert_time": a.alert_time,
        "resolve_time": a.resolve_time,
        "status": a.status,
    }


def _forecast_brief(c: Container, f) -> dict:
    alert = None
    if f.peak_level is not None:
        pass
    return {
        "forecast_id": f.forecast_id,
        "station_id": f.station_id,
        "model_type": f.model_type,
        "lead_hours": f.lead_hours,
        "predict_time": f.predict_time,
        "peak_level": f.peak_level,
        "peak_time": f.peak_time,
        "rmse": f.rmse,
        "degraded": bool(f.degraded),
        "remark": f.remark,
    }
