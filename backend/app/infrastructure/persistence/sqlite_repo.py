"""SQLite 业务仓储实现（Station/Forecast/Alert/Model/Agent 三表等）。

业务读写全部走 SQLite；时序明细走 Parquet；分析走 DuckDB。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.domain.models import (
    AgentMessage,
    AgentSession,
    AgentToolCall,
    Alert,
    FloodEvent,
    Forecast,
    ForecastDecision,
    ForecastPoint,
    LEVEL_RANK,
    Model,
    Source,
    Station,
    Task,
)


class StationRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def list(self, enabled_only: bool = False) -> List[Station]:
        with self.session_factory() as s:
            stmt = select(Station).order_by(Station.station_id)
            if enabled_only:
                stmt = stmt.where(Station.enabled.is_(True))
            return list(s.execute(stmt).scalars())

    def get(self, station_id: int) -> Optional[Station]:
        with self.session_factory() as s:
            return s.get(Station, station_id)

    def get_by_code(self, station_code: str) -> Optional[Station]:
        with self.session_factory() as s:
            return s.execute(
                select(Station).where(Station.station_code == station_code)
            ).scalar_one_or_none()

    def next_code(self) -> str:
        with self.session_factory() as s:
            n = s.execute(select(func.count(Station.station_id))).scalar() or 0
            return f"S{n + 1:03d}"

    def create(self, **kwargs) -> Station:
        with self.session_factory() as s:
            if not kwargs.get("station_code"):
                kwargs["station_code"] = self.next_code()
            row = Station(**kwargs)
            s.add(row)
            s.commit()
            return row

    def update(self, station_id: int, **kwargs) -> Optional[Station]:
        fields = {
            k: v
            for k, v in kwargs.items()
            if k in {
                "station_name", "location", "kind", "threshold_blue", "threshold_yellow",
                "threshold_orange", "threshold_red", "base_level", "response_k", "enabled",
            }
        }
        if not fields:
            return self.get(station_id)
        fields["update_time"] = datetime.now()
        with self.session_factory() as s:
            s.execute(update(Station).where(Station.station_id == station_id).values(**fields))
            s.commit()
        return self.get(station_id)

    def delete(self, station_id: int) -> bool:
        """删除监测点：有预测/预警记录时退化为停用（保护追溯链）。"""
        with self.session_factory() as s:
            fc = s.execute(
                select(func.count(Forecast.forecast_id)).where(Forecast.station_id == station_id)
            ).scalar() or 0
            al = s.execute(
                select(func.count(Alert.alert_id)).where(Alert.station_id == station_id)
            ).scalar() or 0
            if fc or al:
                s.execute(
                    update(Station).where(Station.station_id == station_id).values(
                        enabled=False, update_time=datetime.now()
                    )
                )
                s.commit()
                return False
            s.execute(delete(Station).where(Station.station_id == station_id))
            s.commit()
            return True


class ModelRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def list(self) -> List[Model]:
        with self.session_factory() as s:
            return list(s.execute(select(Model).order_by(Model.model_id)).scalars())

    def get(self, model_id: int) -> Optional[Model]:
        with self.session_factory() as s:
            return s.get(Model, model_id)

    def get_active(self) -> Optional[Model]:
        with self.session_factory() as s:
            return s.execute(select(Model).where(Model.active.is_(True))).scalar_one_or_none()

    def activate(self, model_id: int) -> Optional[Model]:
        with self.session_factory() as s:
            row = s.get(Model, model_id)
            if row is None or not row.model_file:
                return None
            s.execute(update(Model).values(active=False))
            row.active = True
            s.commit()
            return row

    def save_calibration(
        self, model_id: int, station_id: int, params: Dict[str, Any],
        rmse_before: float, rmse_after: float, mae_before: float, mae_after: float,
    ) -> Optional[Model]:
        """把站点级标定参数写入 model.algorithm_config JSON（参数校准做实）。"""
        with self.session_factory() as s:
            row = s.get(Model, model_id)
            if row is None:
                return None
            cfg = {}
            if row.algorithm_config:
                try:
                    cfg = json.loads(row.algorithm_config)
                except (ValueError, TypeError):
                    cfg = {}
            calib = cfg.get("calibration", {})
            calib[str(station_id)] = {
                "params": params,
                "rmse_before": rmse_before, "rmse_after": rmse_after,
                "mae_before": mae_before, "mae_after": mae_after,
                "calibrated_at": datetime.now().isoformat(timespec="seconds"),
            }
            cfg["calibration"] = calib
            row.algorithm_config = json.dumps(cfg, ensure_ascii=False)
            row.rmse = rmse_after
            row.mae = mae_after
            row.update_time = datetime.now()
            s.commit()
            return row


class ForecastRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def create(self, **kwargs) -> Forecast:
        with self.session_factory() as s:
            row = Forecast(**kwargs)
            s.add(row)
            s.commit()
            s.refresh(row)
            return row

    def add_points(self, forecast_id: int, points: List[Dict[str, Any]]) -> None:
        with self.session_factory() as s:
            for p in points:
                s.add(ForecastPoint(forecast_id=forecast_id, **p))
            s.commit()

    def add_decision(self, **kwargs) -> ForecastDecision:
        with self.session_factory() as s:
            row = ForecastDecision(**kwargs)
            s.add(row)
            s.commit()
            return row

    def get(self, forecast_id: int) -> Optional[Forecast]:
        with self.session_factory() as s:
            return s.get(Forecast, forecast_id)

    def get_points(self, forecast_id: int) -> List[ForecastPoint]:
        with self.session_factory() as s:
            return list(
                s.execute(
                    select(ForecastPoint)
                    .where(ForecastPoint.forecast_id == forecast_id)
                    .order_by(ForecastPoint.lead_minutes)
                ).scalars()
            )

    def get_decision(self, forecast_id: int) -> Optional[ForecastDecision]:
        with self.session_factory() as s:
            return s.execute(
                select(ForecastDecision)
                .where(ForecastDecision.forecast_id == forecast_id)
                .order_by(ForecastDecision.decision_id.desc())
            ).scalars().first()

    def latest_for_station(self, station_id: int, lead_hours: Optional[int] = None) -> Optional[Forecast]:
        with self.session_factory() as s:
            stmt = select(Forecast).where(Forecast.station_id == station_id)
            if lead_hours is not None:
                stmt = stmt.where(Forecast.lead_hours == lead_hours)
            return s.execute(stmt.order_by(Forecast.forecast_id.desc())).scalars().first()

    def list_for_station(
        self, station_id: int, page: int = 1, page_size: int = 10
    ) -> Tuple[List[Forecast], int]:
        with self.session_factory() as s:
            total = s.execute(
                select(func.count(Forecast.forecast_id)).where(Forecast.station_id == station_id)
            ).scalar() or 0
            rows = s.execute(
                select(Forecast)
                .where(Forecast.station_id == station_id)
                .order_by(Forecast.forecast_id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars()
            return list(rows), int(total)

    def list_all(self, page: int = 1, page_size: int = 10,
                 station_id: Optional[int] = None) -> Tuple[List[Forecast], int]:
        """全局预测记录（总览页「最近预测」）。"""
        with self.session_factory() as s:
            cnt = select(func.count(Forecast.forecast_id))
            stmt = select(Forecast)
            if station_id is not None:
                stmt = stmt.where(Forecast.station_id == station_id)
                cnt = cnt.where(Forecast.station_id == station_id)
            total = s.execute(cnt).scalar() or 0
            rows = s.execute(
                stmt.order_by(Forecast.forecast_id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars()
            return list(rows), int(total)

    def pending_actual_points(self, now: Optional[datetime] = None) -> List[ForecastPoint]:
        """target_time 已过且实况尚未回填的逐点（供精度闭环）。"""
        now = now or datetime.now()
        with self.session_factory() as s:
            return list(
                s.execute(
                    select(ForecastPoint)
                    .where(ForecastPoint.target_time <= now)
                    .where(ForecastPoint.actual_level.is_(None))
                    .limit(2000)
                ).scalars()
            )

    def backfill_actual(self, updates: List[Tuple[int, int, float]]) -> int:
        """批量回填 actual_level：[(forecast_id, lead_minutes, actual)]。"""
        if not updates:
            return 0
        with self.session_factory() as s:
            for fid, lm, actual in updates:
                s.execute(
                    update(ForecastPoint)
                    .where(ForecastPoint.forecast_id == fid)
                    .where(ForecastPoint.lead_minutes == lm)
                    .values(actual_level=actual)
                )
            # 顺手计算 forecast 级 RMSE/MAE
            fid_set = {fid for fid, _, _ in updates}
            for fid in fid_set:
                rows = s.execute(
                    select(ForecastPoint).where(ForecastPoint.forecast_id == fid)
                ).scalars()
                pairs = [
                    (r.pred_level, r.actual_level)
                    for r in rows
                    if r.actual_level is not None
                ]
                if len(pairs) >= 3:
                    import math

                    rmse = math.sqrt(sum((p - a) ** 2 for p, a in pairs) / len(pairs))
                    mae = sum(abs(p - a) for p, a in pairs) / len(pairs)
                    s.execute(
                        update(Forecast)
                        .where(Forecast.forecast_id == fid)
                        .values(rmse=round(rmse, 4), mae=round(mae, 4))
                    )
            s.commit()
            return len(updates)

    def recent_rmse_for_station(self, station_id: int, limit: int = 20) -> Optional[float]:
        with self.session_factory() as s:
            val = s.execute(
                select(func.avg(Forecast.rmse))
                .where(Forecast.station_id == station_id)
                .where(Forecast.rmse.is_not(None))
                .order_by(Forecast.forecast_id.desc())
                .limit(limit)
            ).scalar()
            return float(val) if val is not None else None


class AlertRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def create(self, **kwargs) -> Alert:
        with self.session_factory() as s:
            row = Alert(**kwargs)
            s.add(row)
            s.commit()
            return row

    def update(self, alert_id: int, **kwargs) -> None:
        with self.session_factory() as s:
            s.execute(update(Alert).where(Alert.alert_id == alert_id).values(**kwargs))
            s.commit()

    def get(self, alert_id: int) -> Optional[Alert]:
        with self.session_factory() as s:
            return s.get(Alert, alert_id)

    def active_for_station(self, station_id: int) -> List[Alert]:
        with self.session_factory() as s:
            return list(
                s.execute(
                    select(Alert)
                    .where(Alert.station_id == station_id)
                    .where(Alert.status == "active")
                    .order_by(Alert.alert_id.desc())
                ).scalars()
            )

    def current_effective(self, station_id: int) -> Optional[Alert]:
        """当前有效预警（非参考级中最高级）。"""
        rows = self.active_for_station(station_id)
        effective = [a for a in rows if not a.is_reference]
        if not effective:
            return None
        return max(effective, key=lambda a: LEVEL_RANK.get(a.level, 0))

    def list_page(
        self,
        page: int = 1,
        page_size: int = 20,
        station_id: Optional[int] = None,
        level: Optional[str] = None,
        status: Optional[str] = None,
        is_reference: Optional[bool] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Tuple[List[Alert], int]:
        with self.session_factory() as s:
            stmt = select(Alert)
            cnt = select(func.count(Alert.alert_id))
            conds = []
            if station_id is not None:
                conds.append(Alert.station_id == station_id)
            if level:
                conds.append(Alert.level == level)
            if status:
                conds.append(Alert.status == status)
            if is_reference is not None:
                conds.append(Alert.is_reference.is_(is_reference))
            if start is not None:
                conds.append(Alert.alert_time >= start)
            if end is not None:
                conds.append(Alert.alert_time <= end)
            for c in conds:
                stmt = stmt.where(c)
                cnt = cnt.where(c)
            total = s.execute(cnt).scalar() or 0
            rows = s.execute(
                stmt.order_by(Alert.alert_time.desc(), Alert.alert_id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars()
            return list(rows), int(total)

    def today_count(self, effective_only: bool = True) -> int:
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        with self.session_factory() as s:
            stmt = select(func.count(Alert.alert_id)).where(Alert.alert_time >= start)
            if effective_only:
                stmt = stmt.where(Alert.is_reference.is_(False))
            return s.execute(stmt).scalar() or 0

    def resolve_stale(self, station_id: int, peak_below_blue: bool, resolve_minutes: int) -> int:
        """预测峰值回落至蓝线下且持续 resolve_minutes → 解除（FR-4.4 简化实现）。"""
        if not peak_below_blue:
            return 0
        cutoff = datetime.now() - timedelta(minutes=resolve_minutes)
        n = 0
        with self.session_factory() as s:
            rows = s.execute(
                select(Alert)
                .where(Alert.station_id == station_id)
                .where(Alert.status == "active")
                .where(Alert.alert_time <= cutoff)
            ).scalars()
            for a in rows:
                a.status = "resolved"
                a.resolve_time = datetime.now()
                n += 1
            if n:
                s.commit()
        return n


class AgentRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def get_or_create_session(self, session_id: str, title: Optional[str] = None) -> AgentSession:
        with self.session_factory() as s:
            row = s.get(AgentSession, session_id)
            if row is None:
                row = AgentSession(session_id=session_id, title=title or "新会话")
                s.add(row)
                s.commit()
            return row

    def list_sessions(self, limit: int = 50) -> List[AgentSession]:
        with self.session_factory() as s:
            return list(
                s.execute(
                    select(AgentSession)
                    .order_by(AgentSession.create_time.desc())
                    .limit(limit)
                ).scalars()
            )

    def add_message(self, session_id: str, role: str, content: str) -> AgentMessage:
        with self.session_factory() as s:
            row = AgentMessage(session_id=session_id, role=role, content=content)
            s.add(row)
            s.commit()
            return row

    def list_messages(self, session_id: str, limit: int = 100) -> List[AgentMessage]:
        with self.session_factory() as s:
            return list(
                s.execute(
                    select(AgentMessage)
                    .where(AgentMessage.session_id == session_id)
                    .order_by(AgentMessage.message_id)
                    .limit(limit)
                ).scalars()
            )

    def add_tool_call(self, **kwargs) -> AgentToolCall:
        with self.session_factory() as s:
            row = AgentToolCall(**kwargs)
            s.add(row)
            s.commit()
            return row

    def list_tool_calls(self, session_id: str, limit: int = 50) -> List[AgentToolCall]:
        with self.session_factory() as s:
            return list(
                s.execute(
                    select(AgentToolCall)
                    .where(AgentToolCall.session_id == session_id)
                    .order_by(AgentToolCall.call_id.desc())
                    .limit(limit)
                ).scalars()
            )


class TaskRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def create(self, task_type: str, request: Dict[str, Any], status: str = "pending") -> Task:
        with self.session_factory() as s:
            row = Task(task_type=task_type, status=status,
                       request_json=json.dumps(request, ensure_ascii=False))
            s.add(row)
            s.commit()
            return row

    def get(self, task_id: int) -> Optional[Task]:
        with self.session_factory() as s:
            return s.get(Task, task_id)


class EventRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def search_similar(self, station_id: Optional[int], peak_min: Optional[float]) -> List[FloodEvent]:
        with self.session_factory() as s:
            stmt = select(FloodEvent)
            if station_id is not None:
                stmt = stmt.where(FloodEvent.station_id == station_id)
            if peak_min is not None:
                stmt = stmt.where(FloodEvent.peak_level >= peak_min)
            return list(s.execute(stmt.order_by(FloodEvent.peak_level.desc()).limit(20)).scalars())
