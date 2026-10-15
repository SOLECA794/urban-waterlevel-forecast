"""SQLite 引擎与会话管理；建表（幂等）与种子数据。"""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, load_stations_yaml
from app.core.logging import get_logger
from app.domain.models import (
    AgentMessage,
    AgentSession,
    AgentToolCall,
    Alert,
    Base,
    FloodEvent,
    Forecast,
    ForecastDecision,
    ForecastPoint,
    Model,
    Source,
    Station,
    Task,
)

logger = get_logger("persistence.database")

# 导入即注册全部 ORM 模型（create_all 用）
ALL_MODELS = [
    Source, Station, Model, Forecast, ForecastPoint, ForecastDecision,
    Alert, FloodEvent, Task, AgentSession, AgentMessage, AgentToolCall,
]


def create_engine_for(settings: Settings) -> Engine:
    sqlite_file = settings.sqlite_file
    sqlite_file.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{sqlite_file.as_posix()}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def init_db(engine: Engine, settings: Settings, seed: bool = True) -> None:
    """建表（幂等）；seed=True 时按 stations.yaml 同步监测点与模型版本。"""
    Base.metadata.create_all(engine)
    if not seed:
        return
    with Session(engine) as session:
        _seed(session, settings)
        session.commit()
    logger.info("database initialized", extra={"event": "db_init"})


def _seed(session: Session, settings: Settings) -> None:
    # 1) 数据源
    source = session.execute(
        select(Source).where(Source.source_code == "SIM-001")
    ).scalar_one_or_none()
    if source is None:
        session.add(
            Source(
                source_code="SIM-001",
                source_name="模拟数据源（实况+预报双路）",
                type="simulated",
                status="STREAMING",
                config_json=json.dumps(
                    {"interval_minutes": settings.datasource.interval_minutes},
                    ensure_ascii=False,
                ),
            )
        )
        session.flush()

    source = session.execute(select(Source).where(Source.source_code == "SIM-001")).scalar_one()
    source.status = "STREAMING"

    # 2) 监测点（以 stations.yaml 为准同步；已有则更新阈值/参数）
    cfg = load_stations_yaml()
    for item in cfg.get("stations", []):
        row = session.execute(
            select(Station).where(Station.station_code == item["station_code"])
        ).scalar_one_or_none()
        if row is None:
            row = Station(
                station_code=item["station_code"],
                station_name=item["station_name"],
                location=item.get("location"),
                kind=item.get("kind"),
                source_id=source.source_id,
                threshold_blue=item.get("threshold_blue"),
                threshold_yellow=item.get("threshold_yellow"),
                threshold_orange=item.get("threshold_orange"),
                threshold_red=item.get("threshold_red"),
                base_level=item.get("base_level"),
                response_k=item.get("response_k"),
                enabled=bool(item.get("enabled", True)),
            )
            session.add(row)
        else:
            row.station_name = item["station_name"]
            row.threshold_blue = item.get("threshold_blue", row.threshold_blue)
            row.threshold_yellow = item.get("threshold_yellow", row.threshold_yellow)
            row.threshold_orange = item.get("threshold_orange", row.threshold_orange)
            row.threshold_red = item.get("threshold_red", row.threshold_red)
            row.base_level = item.get("base_level", row.base_level)
            row.response_k = item.get("response_k", row.response_k)
            row.enabled = bool(item.get("enabled", True))
    session.flush()

    # 3) 模型版本（占位模型 ×2，支撑 S7 模型可插拔演示）
    seeded_models = [
        dict(model_name="持久性模型（Naive）", version="v1.0", model_type="naive",
             model_file="checkpoints/naive_v1.json", active=False,
             algorithm_config=json.dumps({"decay": settings.forecast.linear_response.decay})),
        dict(model_name="降雨线性响应模型（LinearResponse）", version="v1.0",
             model_type="linear_response", model_file="checkpoints/linear_v1.json",
             active=True,
             algorithm_config=json.dumps(
                 settings.forecast.linear_response.model_dump(), ensure_ascii=False)),
        # EXT-POINT(MODEL): LightGBM / Prophet / TCN 真模型版本在此注册
        dict(model_name="LightGBM 模型（占位，未实现）", version="v0.0-placeholder",
             model_type="lgbm", model_file="", active=False,
             algorithm_config=json.dumps({"status": "placeholder"})),
    ]
    for m in seeded_models:
        exists = session.execute(
            select(Model).where(
                Model.model_type == m["model_type"], Model.version == m["version"]
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(Model(**m))
    session.flush()

    # 激活状态唯一化：默认激活配置指定的类型
    active_type = settings.forecast.model_type
    for row in session.execute(select(Model)).scalars():
        row.active = row.model_type == active_type

    # 4) 内涝事件库（供 Agent 历史类比检索演示）
    if session.execute(select(FloodEvent).limit(1)).scalar_one_or_none() is None:
        stations = session.execute(select(Station)).scalars().all()
        base_t = None
        for st in stations:
            if base_t is None:
                base_t = st.create_time
        if base_t is not None:
            samples = [
                ("S001", 2.85, 12.5, 46.2, "orange", "启动泵站 2 台，封闭下穿隧道"),
                ("S002", 2.62, 10.0, 38.7, "orange", "布设移动泵车，交通管制"),
                ("S003", 2.30, 8.5, 30.1, "yellow", "河道预泄，巡查堤防"),
            ]
            for code, peak, total, inten, level, action in samples:
                st = session.execute(
                    select(Station).where(Station.station_code == code)
                ).scalar_one_or_none()
                if st is None:
                    continue
                session.add(
                    FloodEvent(
                        station_id=st.station_id,
                        start_time=base_t - timedelta(days=30),
                        end_time=base_t - timedelta(days=30) + timedelta(hours=6),
                        peak_level=peak,
                        peak_time=base_t - timedelta(days=30) + timedelta(hours=3),
                        total_rainfall=total,
                        max_rain_intensity=inten,
                        max_alert_level=level,
                        response_actions=action,
                        remark="历史事件样例（模拟）",
                    )
                )


def reset_db(engine: Engine) -> None:
    """删除并重建全部表（generate_demo_data --reset 使用）。"""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
