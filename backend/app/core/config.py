"""分层配置：default.yaml + stations.yaml + 环境变量覆盖。

配置驱动一切（NFR-3）：数据源类型、模型类型、点位、阈值、预见期全部外置，
改场景不改代码。
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/
PROJECT_ROOT = BACKEND_ROOT.parent                             # 项目根目录


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class AppConfig(BaseModel):
    name: str = "城市内涝（积水）水位预测预警系统"
    host: str = "0.0.0.0"
    port: int = 8000
    # 启动时是否立即执行一轮滚动预测（演示数据就绪）；测试可关闭
    auto_forecast_on_startup: bool = True


class DatasourceConfig(BaseModel):
    type: str = "simulated"        # simulated / real（real 走 RealSourceAdapter，本期占位）
    interval_minutes: int = 5      # 采样间隔
    history_hours: int = 72        # 模拟历史序列长度
    error_after_missing_cycles: int = 3  # 连续 3 个采样周期无数据置 ERROR（FR-1.3）
    # 评审 R2：数据新鲜度判定阈值——最新样本滞后超过该分钟数判 STALE（不再误报正常）
    stale_after_minutes: float = 30.0
    # 评审 P1-7：模拟事件注入的演示钥匙（防止演示环境被误触发；生产须环境变量注入）
    demo_key: str = "FANGXUN-DEMO"


class LinearResponseParams(BaseModel):
    """LinearResponseModel 与模拟数据生成器共用的同一套响应参数（ADR-3）。"""
    gain: float = 0.006            # 有效降雨(mm) → 水位(m) 的总增益
    kernel_len: int = 12           # 汇流滞后核长度（步，5min/步 → 1h）
    kernel_tau: float = 5.0        # 核形状参数
    response_k: float = 0.010      # 每步退水系数（站点可覆盖）
    decay: float = 0.08            # NaiveModel 向基流回落速率（/h）


class ForecastConfig(BaseModel):
    model_type: str = "linear_response"   # naive / linear_response
    lead_hours: List[int] = Field(default_factory=lambda: [1, 3, 6, 12])
    step_minutes: int = 5
    min_history_hours: int = 6
    schedule_minutes: int = 5      # 滚动预测周期（FR-3.2）
    smoothing_alpha: float = 0.6
    linear_response: LinearResponseParams = Field(default_factory=LinearResponseParams)


class RevisionConfig(BaseModel):
    """多源协同修正（V1.3 §7.5）：多源加权新息 + 时间衰减。"""
    enabled: bool = True
    alpha: float = 0.6             # 修正强度（D3 决策默认值）
    rho: float = 0.85              # 时间衰减因子（/步）：越远的未来修正越少
    beta: float = 0.02             # 置信区间展宽系数（/min）
    innovation_threshold: float = 0.05  # 新息超过该值(m)才启用强修正
    rain_gain: float = 0.004       # 降雨新息(mm) → 水位(m) 换算增益


class AlertConfig(BaseModel):
    dedup_minutes: int = 30        # 同级/更高级生效预警去重窗口（FR-4.3）
    resolve_minutes: int = 15      # 回落持续该时长后解除（FR-4.4）
    default_thresholds: Dict[str, float] = Field(
        default_factory=lambda: {"blue": 1.8, "yellow": 2.2, "orange": 2.6, "red": 3.0}
    )


class StorageConfig(BaseModel):
    data_dir: str = "data"
    sqlite_path: str = "data/app.db"
    parquet_dir: str = "data/parquet"


class AgentConfig(BaseModel):
    echo_enabled: bool = True
    # L2 工具人工确认令牌（演示用固定值；生产环境必须改为环境变量注入）
    confirm_token: str = "CONFIRMED"


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    datasource: DatasourceConfig = Field(default_factory=DatasourceConfig)
    forecast: ForecastConfig = Field(default_factory=ForecastConfig)
    revision: RevisionConfig = Field(default_factory=RevisionConfig)
    alert: AlertConfig = Field(default_factory=AlertConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)

    # 运行时派生路径
    def resolve_data_dir(self) -> Path:
        p = Path(self.storage.data_dir)
        if not p.is_absolute():
            p = BACKEND_ROOT / p
        return p

    @property
    def sqlite_file(self) -> Path:
        p = Path(self.storage.sqlite_path)
        if not p.is_absolute():
            p = BACKEND_ROOT / p
        return p

    @property
    def parquet_dir(self) -> Path:
        p = Path(self.storage.parquet_dir)
        if not p.is_absolute():
            p = BACKEND_ROOT / p
        return p

    @property
    def frontend_dist(self) -> Optional[Path]:
        """单端口部署形态：FastAPI 同时托管 frontend/dist（主控会话指定，文档外口径）。"""
        env = os.getenv("FRONTEND_DIST")
        if env:
            p = Path(env)
            return p if p.exists() else None
        p = PROJECT_ROOT / "frontend" / "dist"
        return p if (p / "index.html").exists() else None


def load_settings() -> Settings:
    """读取 config/default.yaml，再用环境变量 WL__SECTION__KEY 覆盖（简化版：仅支持整体节替换）。"""
    data = _load_yaml(BACKEND_ROOT / "config" / "default.yaml")
    settings = Settings.model_validate(data)
    # 环境变量覆盖常用项
    if os.getenv("WL_PORT"):
        settings.app.port = int(os.getenv("WL_PORT"))
    if os.getenv("WL_HOST"):
        settings.app.host = os.getenv("WL_HOST")
    if os.getenv("WL_DATASOURCE_TYPE"):
        settings.datasource.type = os.getenv("WL_DATASOURCE_TYPE")
    if os.getenv("WL_DEMO_KEY"):
        settings.datasource.demo_key = os.getenv("WL_DEMO_KEY")
    if os.getenv("WL_FORECAST_MODEL"):
        settings.forecast.model_type = os.getenv("WL_FORECAST_MODEL")
    if os.getenv("WL_SQLITE_PATH"):
        settings.storage.sqlite_path = os.getenv("WL_SQLITE_PATH")
    if os.getenv("WL_PARQUET_DIR"):
        settings.storage.parquet_dir = os.getenv("WL_PARQUET_DIR")
    if os.getenv("WL_AUTO_FORECAST") is not None:
        settings.app.auto_forecast_on_startup = os.getenv("WL_AUTO_FORECAST").lower() in ("1", "true", "yes")
    return settings


def load_stations_yaml() -> Dict[str, Any]:
    return _load_yaml(BACKEND_ROOT / "config" / "stations.yaml")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
