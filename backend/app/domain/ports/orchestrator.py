"""ForecastOrchestrator Port（V1.3 新增，本期做实）—— 即 Agent-A 预测编排智能体。

语义与 Agent-B（对话式）不同：Agent-A 是应用层内部的决策组件，非对话、非 LLM。
在每次预测前做出五项决策（D1 模型选择 / D2 融合权重 / D3 修正策略 /
D4 置信区间自适应 / D5 降级决策），全部记录、全部可解释（forecast_decision 表）。
本期实现 RuleBasedOrchestrator（纯规则，零依赖）；将来可升级 bandit/RL/LLM 策略。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


@dataclass
class SourceQuality:
    """数据源质量画像（D2/D4/D5 的输入依据）。"""

    status: str = "STREAMING"        # SourceStatus
    missing_rate: float = 0.0        # 最近窗口缺失率
    last_sample_age_min: float = 0.0  # 最新样本距今年龄（分钟）
    rain_bias: float = 0.0           # 近期雨量计偏差（相对量）
    recent_rmse: Optional[float] = None  # 近期预测误差（m），来自 forecast_point 回填


@dataclass
class ForecastContext:
    station_id: int
    station_code: str = ""
    lead_hours: int = 1
    history_rows: int = 0
    min_rows: int = 0
    innovation: float = 0.0          # 最近新息：actual - predicted（m）
    fcst_shift: float = 0.0          # 最新预报量 − 上一版预报量（mm）
    quality: SourceQuality = field(default_factory=SourceQuality)
    active_model_type: str = "linear_response"


@dataclass
class ForecastDecision:
    """五项决策结果（写 forecast_decision 表）。"""

    selected_model: str = "linear_response"   # D1
    fusion_weights: dict = field(             # D2：w_level / w_rain / w_fcst
        default_factory=lambda: {"level": 0.45, "rain": 0.35, "fcst": 0.2}
    )
    revision_alpha: float = 0.6               # D3
    ci_scale: float = 1.0                     # D4
    degraded: bool = False                    # D5
    reason: str = ""                          # 人话解释（前端 + explain_forecast）


@runtime_checkable
class ForecastOrchestrator(Protocol):
    def decide(self, ctx: ForecastContext) -> ForecastDecision: ...
