"""模型版本表（FR-6.5：数据结构必须到位）。"""
from __future__ import annotations

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now


class Model(Base):
    __tablename__ = "model"

    model_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    # naive / linear_response / lgbm（预留）/ prophet（预留）/ tcn（预留）
    model_type: Mapped[str] = mapped_column(String(32), nullable=False)
    algorithm_config: Mapped[str] = mapped_column(Text, nullable=True)  # 超参配置 JSON
    rmse: Mapped[float] = mapped_column(Float, nullable=True)
    mae: Mapped[float] = mapped_column(Float, nullable=True)
    model_file: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    create_time: Mapped[now] = mapped_column(DateTime, nullable=False, default=now)
    update_time: Mapped[now] = mapped_column(DateTime, nullable=False, default=now, onupdate=now)
