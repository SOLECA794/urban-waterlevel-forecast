"""SQLAlchemy 2.0 声明基类与公共字段。

说明：文档口径为 Alembic 迁移管理；本期以 SQLAlchemy metadata 建表（幂等
create_all）+ scripts/generate_demo_data.py 种子化替代，migrations/ 目录保留
扩展说明（EXT-POINT），已在交付报告记录偏离理由（演示环境一键启动优先）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def now() -> datetime:
    """统一使用本地朴素时间（演示系统单一时区部署的工作假设）。"""
    return datetime.now()
