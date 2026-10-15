"""FastAPI 依赖注入：Port → Adapter 绑定（V1.2 §3）。

这里是最接近「组合根」的位置：应用层/领域层只 import 本模块提供的容器，
不 import 任何具体 Adapter。测试时替换容器成员即可 mock。
"""
from __future__ import annotations

from functools import lru_cache

from app.application.agent_service import AgentService
from app.application.alert_service import AlertService
from app.application.calibration_service import CalibrationService
from app.application.forecast_service import ForecastService
from app.application.orchestrator import RuleBasedOrchestrator
from app.application.revision_service import ForecastRevisionService
from app.application.station_service import StationService
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.infrastructure.agent.echo_agent import EchoAgent
from app.infrastructure.agent.tool_registry import ToolRegistry
from app.infrastructure.agent.tools.builtin_tools import build_tools
from app.infrastructure.datasource.rolling_generator import RollingSimGenerator
from app.infrastructure.datasource.simulated_source import SimulatedSource
from app.infrastructure.forecast.registry import ModelRegistry
from app.infrastructure.persistence.database import create_engine_for, init_db, make_session_factory
from app.infrastructure.persistence.duckdb_analytics import DuckDBAnalytics
from app.infrastructure.persistence.parquet_store import ParquetTimeSeriesRepository
from app.infrastructure.persistence.sqlite_repo import (
    AgentRepository,
    AlertRepository,
    EventRepository,
    ForecastRepository,
    ModelRepository,
    StationRepository,
    TaskRepository,
)
from app.infrastructure.scheduler.jobs import SchedulerService

# 纯判定函数（R2 可单测）：模块级别导入，别名避免与本地语义混淆
from app.infrastructure.datasource.simulated_source import (
    evaluate_source_status as _evaluate_status,
)

logger = get_logger("core.deps")


class Container:
    """应用组装根：唯一的 Port→Adapter 绑定位置。"""

    def __init__(self, settings: Settings):
        self.settings = settings

        # --- 持久化 ---
        self.engine = create_engine_for(settings)
        init_db(self.engine, settings)
        self.session_factory = make_session_factory(self.engine)

        self.station_repo = StationRepository(self.session_factory)
        self.model_repo = ModelRepository(self.session_factory)
        self.forecast_repo = ForecastRepository(self.session_factory)
        self.alert_repo = AlertRepository(self.session_factory)
        self.agent_repo = AgentRepository(self.session_factory)
        self.task_repo = TaskRepository(self.session_factory)
        self.event_repo = EventRepository(self.session_factory)

        self.ts_repo = ParquetTimeSeriesRepository(settings.parquet_dir)
        self.duckdb = DuckDBAnalytics(settings.parquet_dir)

        # --- 数据源（配置驱动：simulated / real） ---
        if settings.datasource.type == "real":
            # EXT-POINT(DATASOURCE): 切换真实数据源——实现 RealSourceAdapter 后在此绑定
            raise RuntimeError(
                "datasource.type=real 需先按 RealSourceAdapter 的 EXT-POINT(DATASOURCE) 完成实现"
            )
        self.datasource = SimulatedSource(
            self.ts_repo,
            interval_minutes=settings.datasource.interval_minutes,
            missing_cycles=settings.datasource.error_after_missing_cycles,
            stale_after_minutes=settings.datasource.stale_after_minutes,
        )

        # --- 滚动观测数据生成器（评审 R1：相对时间滚动窗口，样本永不冻结） ---
        # EXT-POINT(DATASOURCE): 真实数据源接入后由真实采集适配器替换 tick 实现
        self.generator = RollingSimGenerator(
            self.ts_repo,
            stations_provider=lambda: [
                {"station_id": s.station_id, "base_level": s.base_level, "response_k": s.response_k}
                for s in self.station_repo.list(enabled_only=True)
            ],
            linear_params=settings.forecast.linear_response,
            step_minutes=settings.datasource.interval_minutes,
        )

        # --- 领域服务 ---
        self.orchestrator = RuleBasedOrchestrator(settings.revision, settings.forecast)
        self.revision_service = ForecastRevisionService(settings.revision)
        self.registry = ModelRegistry(settings.forecast)
        self.alert_service = AlertService(settings.alert, self.alert_repo)

        self.forecast_service = ForecastService(
            settings=settings,
            station_repo=self.station_repo,
            model_repo=self.model_repo,
            forecast_repo=self.forecast_repo,
            alert_repo=self.alert_repo,
            alert_service=self.alert_service,
            orchestrator=self.orchestrator,
            revision_service=self.revision_service,
            registry=self.registry,
            datasource=self.datasource,
            ts_repo=self.ts_repo,
        )
        self.station_service = StationService(
            self.station_repo, self.forecast_repo, self.alert_repo, self.ts_repo
        )
        self.calibration_service = CalibrationService(
            self.model_repo, self.task_repo, self.ts_repo, settings.forecast
        )

        # --- Agent ---
        self.tool_registry = ToolRegistry(confirm_token=settings.agent.confirm_token)
        for tool in build_tools(self):
            self.tool_registry.register(tool)
        self.echo_agent = EchoAgent()
        self.agent_service = AgentService(
        self.agent_repo, self.tool_registry, self.echo_agent,
        station_service=self.station_service,
        alert_repo=self.alert_repo,
        forecast_repo=self.forecast_repo,
    )

        # --- 调度器 ---
        self.scheduler = SchedulerService(self)

    # ------------------------------------------------------------------
    def health_payload(self) -> dict:
        active = self.model_repo.get_active()
        models = self.model_repo.list()
        from app.domain.models import Forecast, Station

        with self.session_factory() as s:
            station_n = len(s.query(Station).all())
            forecast_n = len(s.query(Forecast).all())
        ds = self._datasource_status_with_freshness()
        return {
            "status": "ok" if ds["status"] in ("READY", "STREAMING") else (
                "stale" if ds["status"] == "STALE" else "degraded"
            ),
            "time": __import__("datetime").datetime.now(),
            "datasource": ds,
            "model": {
                "active": (active.model_type + ":" + active.version) if active else None,
                "loaded": active is not None,
                "available": [m.model_type for m in models if m.model_file],
            },
            "database": {
                "status": "ok",
                "engine": "sqlite",
                "stations": station_n,
                "forecasts": forecast_n,
            },
        }

    def _datasource_status_with_freshness(self) -> dict:
        """R2 + R3：新鲜度判定 → STALE 时触发生成器自愈 → 复查后如实上报。"""
        age = self.generator.freshness_age_minutes()
        stale_after = self.settings.datasource.stale_after_minutes
        status, detail = _evaluate_status(self.datasource.status_value, age, stale_after)
        if status == "STALE":
            # R3 自愈：滚动生成器停滞时自动补齐样本并写日志（2 分钟内应恢复）
            logger.warning(
                "stale data detected (age=%.1fmin); triggering generator self-heal",
                age if age is not None else -1,
                extra={"event": "self_heal_trigger"},
            )
            self.generator.catch_up()
            age = self.generator.freshness_age_minutes()
            status, _ = _evaluate_status(self.datasource.status_value, age, stale_after)
            if status != "STALE":
                detail = f"检测到数据滞后并已自动恢复（生成器自愈补齐，当前滞后 {age:.1f} 分钟）"
            else:
                detail = f"观测数据滞后 {age:.1f} 分钟，自愈未完成（请检查 data/parquet 写权限）"
        ds = self.datasource.source_status_payload(data_age_min=age)
        ds["status"] = status
        ds["detail"] = self.datasource.last_error or detail
        return ds


@lru_cache(maxsize=1)
def get_container() -> Container:
    return Container(get_settings())


def container_dep() -> Container:
    return get_container()
