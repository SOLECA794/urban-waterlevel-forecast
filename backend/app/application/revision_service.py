"""多源协同修正服务（V1.3 新增，✅ 做实）：多源加权新息 + 时间衰减。

「滚动预测」（重新算一遍）≠「滚动校正」（用已发生的事实修正尚未发生的预测）。
corrected(t) = predicted(t) + α·e·ρ^(Δt)，仅对 Δt > 0 时段生效；
置信区间同步展宽：width(t) = width_raw(t)·(1 + β·Δt)。

模型级在线学习明确不做（小样本强非平稳易发散）；预测级修正可随时关闭，
失败也只是回到原始预测——风险可控（05 §7.5 取舍表）。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from app.domain.ports.forecast_model import ForecastPointResult
from app.domain.ports.orchestrator import ForecastDecision


class ForecastRevisionService:
    def __init__(self, cfg):
        self._cfg = cfg  # RevisionConfig

    def apply(
        self,
        raw_points: List[ForecastPointResult],
        decision: ForecastDecision,
        t_now: Optional[datetime] = None,
        innovation: float = 0.0,
        rain_innovation_mm: float = 0.0,
        fcst_shift_mm: float = 0.0,
        event_bonus: float = 0.0,
        step_minutes: int = 5,
    ) -> List[Tuple[datetime, float, float]]:
        """对预测逐点做衰减修正，返回 [(t, revision, corrected_level)]。

        e = w_level·e_level + w_rain·e_rain + w_fcst·e_fcst（权重来自 Agent-A D2）
        """
        t_now = t_now or datetime.now()
        w = decision.fusion_weights or {"level": 0.45, "rain": 0.35, "fcst": 0.2}
        # 降雨类新息（mm）换算为水位（m）：乘以等效增益
        e_level = innovation
        e_rain = rain_innovation_mm * self._cfg.rain_gain
        e_fcst = fcst_shift_mm * self._cfg.rain_gain
        e = (
            w.get("level", 0.4) * e_level
            + w.get("rain", 0.3) * e_rain
            + w.get("fcst", 0.3) * e_fcst
        )
        # 已发生事件修正（FR二.3）：近24h有生效预警的站点，历史已证模型对其低估
        e += event_bonus
        alpha = decision.revision_alpha or 0.0
        rho = self._cfg.rho

        out: List[Tuple[datetime, float, float]] = []
        for p in raw_points:
            dt_min = max(0.0, (p.t - t_now).total_seconds() / 60.0)
            steps = dt_min / step_minutes
            if alpha and e:
                revision = alpha * e * (rho ** steps)
            else:
                revision = 0.0
            corrected = p.level_raw + revision
            out.append((p.t, round(revision, 5), round(corrected, 4)))
        return out

    def widen_ci(self, half_width: float, t: datetime, t_now: datetime) -> float:
        """置信区间随预见期展宽：width = width_raw·(1 + β·Δt)。"""
        dt_min = max(0.0, (t - t_now).total_seconds() / 60.0)
        return half_width * (1.0 + self._cfg.beta * dt_min)
