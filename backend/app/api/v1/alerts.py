"""预警接口：全局预警列表（预警中心）+ 统计。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.deps import Container, container_dep
from app.core.response import ok, page
from app.api.v1.stations import _alert_item

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
def list_alerts(
    page_no: int = Query(1, alias="page", ge=1),
    page_size: int = Query(20, ge=1, le=100),
    station_id: Optional[int] = Query(None),
    level: Optional[str] = Query(None, description="blue/yellow/orange/red"),
    status: Optional[str] = Query(None, description="active/resolved"),
    is_reference: Optional[bool] = Query(None, description="参考级（6h/12h）预警筛选"),
    hours: Optional[int] = Query(None, ge=1, le=720, description="最近 N 小时"),
    c: Container = Depends(container_dep),
):
    """GET /api/v1/alerts —— 预警中心列表（时间倒序，多维筛选）。

    说明：05 接口表仅列出 /stations/{id}/alerts；预警中心页需要全局列表，
    本接口为前端 FR-5.4 的必要补充（已在偏离记录中说明）。
    """
    start = datetime.now() - timedelta(hours=hours) if hours else None
    rows, total = c.alert_repo.list_page(
        page=page_no, page_size=page_size, station_id=station_id, level=level,
        status=status, is_reference=is_reference, start=start,
    )
    items = [_alert_item(c, a) for a in rows]
    return ok(page(items, total, page_no, page_size))


@router.get("/publish-records")
def alert_publish_records(
    limit: int = Query(50, ge=1, le=200, description="取最近 N 条预警生成发布记录"),
    c: Container = Depends(container_dep),
):
    """GET /api/v1/alerts/publish-records —— 预警联动发布记录（评审 P2-9）。

    需求书原话「联动消息、信息屏或其他发布渠道」：推送本身是 EXT-POINT 占位，
    但占位 ≠ 不可见。本接口按每条有效预警生成三条 mock 发布记录：
      站内消息 sent / 信息屏 simulated / 短信 placeholder（灰显）。
    记录由预警数据确定性派生（record_id 稳定），不新增存储表。

    # EXT-POINT(INTEGRATION): 短信网关 / 真实消息推送接入位——接入后
    # 将「派生 mock」替换为真实发送回执落库（建议新增 alert_publish 表）。
    """
    rows, _ = c.alert_repo.list_page(page=1, page_size=limit)
    records = []
    for a in rows:
        st = c.station_repo.get(a.station_id)
        sname = st.station_name if st else f"站点 {a.station_id}"
        level_name = {"blue": "蓝色", "yellow": "黄色", "orange": "橙色", "red": "红色"}.get(a.level, a.level)
        ref = "（参考级）" if a.is_reference else ""
        base = int(a.alert_id) * 10
        records.extend([
            {
                "record_id": f"PB{base + 1}",
                "alert_id": a.alert_id,
                "station_name": sname,
                "level": a.level,
                "channel": "站内消息",
                "channel_code": "IN_APP",
                "status": "sent",
                "detail": f"已向防汛值班群推送{level_name}预警{ref}：{sname}",
                "publish_time": a.alert_time,
            },
            {
                "record_id": f"PB{base + 2}",
                "alert_id": a.alert_id,
                "station_name": sname,
                "level": a.level,
                "channel": "信息屏",
                "channel_code": "INFO_SCREEN",
                "status": "simulated",
                "detail": f"路段信息屏文案已模拟下发（mock）：{sname} 注意积水",
                "publish_time": a.alert_time,
            },
            {
                "record_id": f"PB{base + 3}",
                "alert_id": a.alert_id,
                "station_name": sname,
                "level": a.level,
                "channel": "短信",
                "channel_code": "SMS",
                "status": "placeholder",
                "detail": "EXT-POINT(INTEGRATION)：短信网关未接入，发布留白占位",
                "publish_time": a.alert_time,
            },
        ])
    return ok({"items": records, "total": len(records),
               "note": "站内消息/信息屏为演示通道（mock）；短信为真实渠道占位（EXT-POINT(INTEGRATION)）"})


@router.get("/stats")
def alert_stats(c: Container = Depends(container_dep)):
    """GET /api/v1/alerts/stats —— 今日预警统计（有效/参考级分列，V1.3）。"""
    from app.domain.models import Alert

    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    rows, total = c.alert_repo.list_page(page=1, page_size=1000, start=start)
    by_level = {"blue": 0, "yellow": 0, "orange": 0, "red": 0}
    reference = 0
    active = 0
    max_level = None
    rank_map = {"blue": 1, "yellow": 2, "orange": 3, "red": 4}
    for a in rows:
        by_level[a.level] = by_level.get(a.level, 0) + 1
        if a.is_reference:
            reference += 1
        else:
            active += 1 if a.status == "active" else 0
            if max_level is None or rank_map.get(a.level, 0) > rank_map.get(max_level, 0):
                max_level = a.level
    return ok({
        "today_total": total,
        "effective_total": total - reference,
        "reference_total": reference,
        "active_total": active,
        "by_level": by_level,
        "max_effective_level": max_level,
    })
