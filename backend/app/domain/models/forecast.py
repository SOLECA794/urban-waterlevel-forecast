"""预测主记录 + 逐点明细 + Agent-A 编排决策（04 §4.3 / 05 §5.2）。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now


class Forecast(Base):
    __tablename__ = "forecast"

    forecast_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[int] = mapped_column(Integer, ForeignKey("station.station_id"), nullable=False)
    model_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("model.model_id"), nullable=True)
    model_type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    lead_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    predict_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now)
    horizon_end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    peak_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    peak_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rmse: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 事后与实况对比误差
    mae: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    degraded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now)


class ForecastPoint(Base):
    """预测逐点明细（FR-3.4 必做）。

    pred_level_raw：模型原始输出；revision：协同修正量（可正可负）；
    pred_level = pred_level_raw + revision。三值并存同时满足 FR-3.7
    「原始输出与平滑后曲线同时保存」。actual_level 事后回填，支撑精度评估。
    """

    __tablename__ = "forecast_point"

    forecast_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("forecast.forecast_id"), primary_key=True
    )
    lead_minutes: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    pred_level_raw: Mapped[float] = mapped_column(Float, nullable=False)
    revision: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pred_level: Mapped[float] = mapped_column(Float, nullable=False)
    lower_bound: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    upper_bound: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class ForecastDecision(Base):
    """Agent-A 编排决策记录（D1–D5 全部落库、全部可解释）。"""

    __tablename__ = "forecast_decision"

    decision_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    forecast_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("forecast.forecast_id"), nullable=False
    )
    selected_model: Mapped[str] = mapped_column(String(32), nullable=False)  # D1
    fusion_weights: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # D2 JSON
    revision_alpha: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # D3
    ci_scale: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # D4
    degraded: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)  # D5
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 人话解释
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now)
