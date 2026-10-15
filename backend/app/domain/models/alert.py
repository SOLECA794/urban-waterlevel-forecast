"""预警记录 + 内涝事件表（04 §4.3）。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now

LEVEL_RANK = {"blue": 1, "yellow": 2, "orange": 3, "red": 4}


class Alert(Base):
    __tablename__ = "alert"

    alert_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("station.station_id"), nullable=False
    )
    forecast_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("forecast.forecast_id"), nullable=True
    )
    level: Mapped[str] = mapped_column(String(8), nullable=False)  # blue/yellow/orange/red
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    peak_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    peak_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lead_minutes_advantage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # V1.3：6h/12h 长预见期预警标记「参考级」，浅色区分、不计入有效统计
    is_reference: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lead_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    alert_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now)
    resolve_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class FloodEvent(Base):
    """内涝事件库（V1.2 新增）：Agent 历史类比检索 + 极端样本 + 演示回放。"""

    __tablename__ = "flood_event"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    peak_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    peak_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    total_rainfall: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_rain_intensity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_alert_level: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    response_actions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
