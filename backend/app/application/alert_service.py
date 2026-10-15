"""研判预警服务（FR-4）：阈值判定 / 提前量 / 参考级 / 去重 / 解除。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from app.core.config import AlertConfig
from app.core.logging import get_logger
from app.domain.models import Alert, LEVEL_RANK, Forecast, Station
from app.infrastructure.persistence.sqlite_repo import AlertRepository

logger = get_logger("application.alert")


class AlertService:
    def __init__(self, cfg: AlertConfig, alert_repo: AlertRepository):
        self._cfg = cfg
        self._repo = alert_repo

    def thresholds_of(self, station: Station) -> dict:
        """站点阈值，缺项回退全局默认并在原因中标注（FR-4.6）。"""
        defaults = self._cfg.default_thresholds
        used_default = []
        out = {}
        for lvl in ("blue", "yellow", "orange", "red"):
            v = getattr(station, f"threshold_{lvl}", None)
            if v is None:
                v = defaults[lvl]
                used_default.append(lvl)
            out[lvl] = float(v)
        return out, used_default

    def classify(self, peak_level: float, thresholds: dict) -> Optional[str]:
        """峰值对应的最高预警等级（未超蓝线 → None）。"""
        if peak_level >= thresholds["red"]:
            return "red"
        if peak_level >= thresholds["orange"]:
            return "orange"
        if peak_level >= thresholds["yellow"]:
            return "yellow"
        if peak_level >= thresholds["blue"]:
            return "blue"
        return None

    def first_cross_time(
        self, points: list, threshold: float, t_now: datetime
    ) -> Optional[datetime]:
        """预测曲线首次越过阈值的时间点（含修正后值）。"""
        for p in points:
            if p.level >= threshold:
                return p.t
        return None

    def evaluate_after_forecast(
        self,
        station: Station,
        forecast: Forecast,
        points: list,
        lead_hours: int,
    ) -> Optional[Alert]:
        """预测完成后基于修正后曲线研判（FR-4.1/4.3/4.4 + V1.3 参考级）。"""
        thresholds, used_default = self.thresholds_of(station)
        peak = max(p.level for p in points) if points else 0.0
        peak_time = next((p.t for p in points if p.level == peak), None)
        # 起报时刻对齐预测曲线第一个点（start_ts），而非 datetime.now()——
        # 否则观测样本滞后时前半段预测落在"现在"之前，提前量被截为 0
        t_now = points[0].t if points else forecast.predict_time
        is_reference = lead_hours >= 6

        level = self.classify(peak, thresholds)

        # ---- V1.4 升级：持续时间 + 变化趋势 联合研判（FR 2.2） ----
        if level is not None:
            step_min = 5
            # 超蓝阈持续分钟数
            above = [p for p in points if p.level >= thresholds["blue"]]
            duration_min = len(above) * step_min
            # 后 1/3 段趋势斜率（m/步）
            tail = points[max(1, len(points) * 2 // 3):]
            slope = 0.0
            if len(tail) >= 2:
                slope = (tail[-1].level - tail[0].level) / max(1, len(tail) - 1)
            rank_order = ["blue", "yellow", "orange", "red"]
            rank = rank_order.index(level)
            extra_notes = []
            if duration_min >= 60 and rank < 3:
                rank += 1
                extra_notes.append(f"持续{duration_min}min超阈，等级上调")
            if slope > 0.02 and rank < 3:
                rank += 1
                extra_notes.append(f"雨势仍上升({slope:.3f}m/步)，等级上调")
            if slope < -0.01 and rank > 0:
                rank -= 1
                extra_notes.append(f"水位回落({slope:.3f}m/步)，等级下调")
            level = rank_order[rank]
            if extra_notes:
                thresholds, used_default = thresholds, used_default  # noqa
                pass

        if level is None:
            # 峰值回落 → 处理解除（FR-4.4，简化：预测峰值低于蓝线时解除过期生效预警）
            resolved = self._repo.resolve_stale(
                station.station_id, peak_below_blue=True,
                resolve_minutes=self._cfg.resolve_minutes,
            )
            if resolved:
                logger.info("alert resolved", extra={"station_id": station.station_id, "event": "alert_resolve"})
            return None

        crossing = self.first_cross_time(points, thresholds[level], t_now)
        advantage = None
        if crossing is not None:
            advantage = int(max(0, (crossing - t_now).total_seconds() // 60))
        reason = (
            f"预测峰值 {peak:.2f} m 于 {peak_time.strftime('%H:%M') if peak_time else '—'} "
            f"超过{self._level_name(level)}阈值 {thresholds[level]:.2f} m"
            f"（预见期 {lead_hours}h，口径：水位高程 m"
            + ("，使用默认阈值" if used_default else "") + "）"
        )

        # 去重：窗口内同站、同参考级分类，已有同级或更高级生效预警 → 更新而非新增（FR-4.3）
        existing = self._repo.active_for_station(station.station_id)
        cutoff = datetime.now() - timedelta(minutes=self._cfg.dedup_minutes)
        for a in existing:
            if a.is_reference != is_reference:
                continue
            if a.alert_time < cutoff:
                continue
            if LEVEL_RANK.get(a.level, 0) >= LEVEL_RANK[level]:
                self._repo.update(
                    a.alert_id,
                    forecast_id=forecast.forecast_id,
                    peak_level=peak,
                    peak_time=peak_time,
                    lead_minutes_advantage=advantage,
                    reason=reason,
                )
                return self._repo.get(a.alert_id)
            # 新等级更高 → 升级原预警（FR-4.2 简化：不要求持续时长）
            self._repo.update(
                a.alert_id,
                level=level,
                forecast_id=forecast.forecast_id,
                peak_level=peak,
                peak_time=peak_time,
                lead_minutes_advantage=advantage,
                reason=reason + "（等级上调）",
            )
            return self._repo.get(a.alert_id)

        alert = self._repo.create(
            station_id=station.station_id,
            forecast_id=forecast.forecast_id,
            level=level,
            reason=reason,
            peak_level=peak,
            peak_time=peak_time,
            lead_minutes_advantage=advantage,
            is_reference=is_reference,
            lead_hours=lead_hours,
            alert_time=datetime.now(),
            status="active",
        )
        logger.info(
            "alert created",
            extra={"station_id": station.station_id, "event": "alert_create",
                   "lead_hours": lead_hours},
        )
        return alert

    @staticmethod
    def _level_name(level: str) -> str:
        return {"blue": "蓝色", "yellow": "黄色", "orange": "橙色", "red": "红色"}.get(level, level)
