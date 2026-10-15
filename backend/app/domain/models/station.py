"""监测点表 + 数据源表（04 系统设计说明书 §4.3）。"""
from __future__ import annotations

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now


class Source(Base):
    """数据源注册表（simulated / real）。"""

    __tablename__ = "source"

    source_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    source_name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="simulated")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DISCONNECTED")
    config_json: Mapped[str] = mapped_column(Text, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    create_time: Mapped[now] = mapped_column(DateTime, nullable=False, default=now)
    update_time: Mapped[now] = mapped_column(DateTime, nullable=False, default=now, onupdate=now)


class Station(Base):
    """监测点：四级阈值 + 基流水位 + 退水系数（LinearResponse 使用）。"""

    __tablename__ = "station"

    station_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    station_name: Mapped[str] = mapped_column(String(64), nullable=False)
    location: Mapped[str] = mapped_column(String(128), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=True)  # low-lying/road/river/pump
    source_id: Mapped[int] = mapped_column(Integer, nullable=True)
    threshold_blue: Mapped[float] = mapped_column(Float, nullable=True)
    threshold_yellow: Mapped[float] = mapped_column(Float, nullable=True)
    threshold_orange: Mapped[float] = mapped_column(Float, nullable=True)
    threshold_red: Mapped[float] = mapped_column(Float, nullable=True)
    base_level: Mapped[float] = mapped_column(Float, nullable=True)
    response_k: Mapped[float] = mapped_column(Float, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    create_time: Mapped[now] = mapped_column(DateTime, nullable=False, default=now)
    update_time: Mapped[now] = mapped_column(DateTime, nullable=False, default=now, onupdate=now)
