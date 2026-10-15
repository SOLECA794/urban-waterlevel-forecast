"""监测点用例：列表 / 详情 / 增删改（FR-5.6）。"""
from __future__ import annotations

from typing import Optional

from app.core.errors import BizError
from app.domain.models import LEVEL_RANK
from app.infrastructure.persistence.sqlite_repo import (
    AlertRepository,
    ForecastRepository,
    StationRepository,
)


class StationService:
    def __init__(
        self,
        station_repo: StationRepository,
        forecast_repo: ForecastRepository,
        alert_repo: AlertRepository,
        ts_repo,
    ):
        self._stations = station_repo
        self._forecasts = forecast_repo
        self._alerts = alert_repo
        self._ts_repo = ts_repo

    def _current_payload(self, station_id: int) -> dict:
        latest = self._ts_repo.latest(station_id)
        if latest is None:
            return {"level": None, "ts": None, "rain_observed": None, "data_age_min": None}
        age = None
        if latest.get("ts"):
            from datetime import datetime

            age = round((datetime.now() - latest["ts"]).total_seconds() / 60.0, 1)
        return {
            "level": latest.get("level"),
            "ts": latest.get("ts"),
            "rain_observed": latest.get("rain_observed"),
            "data_age_min": age,
        }

    def _alert_payload(self, station_id: int) -> dict:
        current = self._alerts.current_effective(station_id)
        rank = 0
        if current is not None:
            rank = LEVEL_RANK.get(current.level, 0)
        return {
            "rank": rank,
            "level": current.level if current else None,
            "alert_id": current.alert_id if current else None,
            "reason": current.reason if current else None,
            "is_reference": bool(current.is_reference) if current else False,
            "lead_minutes_advantage": current.lead_minutes_advantage if current else None,
        }

    def list_payload(self) -> list:
        out = []
        for st in self._stations.list():
            cur = self._current_payload(st.station_id)
            ap = self._alert_payload(st.station_id)
            out.append({
                "station_id": st.station_id,
                "station_code": st.station_code,
                "station_name": st.station_name,
                "location": st.location,
                "kind": st.kind,
                "enabled": bool(st.enabled),
                "thresholds": {
                    "blue": st.threshold_blue, "yellow": st.threshold_yellow,
                    "orange": st.threshold_orange, "red": st.threshold_red,
                },
                "current": cur,
                "alert": ap,
            })
        # 卡片按预警等级排序：红 > 橙 > 黄 > 蓝 > 正常（04 §6.1）
        out.sort(key=lambda x: (-x["alert"]["rank"], x["station_id"]))
        return out

    def detail_payload(self, station_id: int) -> dict:
        st = self._stations.get(station_id)
        if st is None:
            raise BizError(1102, f"监测点 {station_id} 不存在（STATION_NOT_FOUND）")
        cur = self._current_payload(station_id)
        ap = self._alert_payload(station_id)
        # 今日预警统计（含参考级单列）
        alerts, total = self._alerts.list_page(page=1, page_size=1000, station_id=station_id)
        today_stats = {"total": 0, "by_level": {"blue": 0, "yellow": 0, "orange": 0, "red": 0},
                       "reference": 0, "active": 0}
        for a in alerts:
            today_stats["total"] += 1
            today_stats["by_level"][a.level] = today_stats["by_level"].get(a.level, 0) + 1
            if a.is_reference:
                today_stats["reference"] += 1
            if a.status == "active":
                today_stats["active"] += 1
        return {
            "station_id": st.station_id,
            "station_code": st.station_code,
            "station_name": st.station_name,
            "location": st.location,
            "kind": st.kind,
            "enabled": bool(st.enabled),
            "base_level": st.base_level,
            "response_k": st.response_k,
            "thresholds": {
                "blue": st.threshold_blue, "yellow": st.threshold_yellow,
                "orange": st.threshold_orange, "red": st.threshold_red,
            },
            "current": cur,
            "alert": ap,
            "alert_stats": today_stats,
        }

    def create(self, **kwargs) -> dict:
        st = self._stations.create(**kwargs)
        return self.detail_payload(st.station_id)

    def update(self, station_id: int, **kwargs) -> dict:
        st = self._stations.update(station_id, **kwargs)
        if st is None:
            raise BizError(1102, f"监测点 {station_id} 不存在（STATION_NOT_FOUND）")
        return self.detail_payload(station_id)

    def delete(self, station_id: int) -> dict:
        st = self._stations.get(station_id)
        if st is None:
            raise BizError(1102, f"监测点 {station_id} 不存在（STATION_NOT_FOUND）")
        hard = self._stations.delete(station_id)
        return {"station_id": station_id, "deleted": hard,
                "note": None if hard else "该点位存在预测/预警记录，已转为停用（保留追溯链）"}
