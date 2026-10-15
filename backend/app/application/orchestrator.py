"""RuleBasedOrchestrator（✅ 本期做实）—— Agent-A 预测编排智能体。

纯 Python 规则、零依赖、无需 LLM、无需联网（03 缺口补齐 §2）。
五项决策全部落 forecast_decision 表、全部可解释。
将来升级 bandit/RL 选模型或 LLM 生成策略：仅替换本类实现，调用方不变。

# EXT-POINT(AGENT): Agent-A 策略升级位——RuleBased → bandit/RL/LLM 策略生成，
# 只需实现 ForecastOrchestrator Port 并在容器中替换绑定。
"""
from __future__ import annotations

import math

from app.domain.ports.orchestrator import ForecastContext, ForecastDecision, SourceQuality


class RuleBasedOrchestrator:
    """规则驱动的预测编排决策（D1–D5）。"""

    def __init__(self, revision_cfg, forecast_cfg):
        self._revision_cfg = revision_cfg
        self._forecast_cfg = forecast_cfg

    def decide(self, ctx: ForecastContext) -> ForecastDecision:
        q: SourceQuality = ctx.quality
        reasons: list = []
        degraded = False

        # --- D5 降级决策：数据源断流 → NaiveModel + 标注「数据延迟」 ---
        if q.status in ("ERROR", "DISCONNECTED"):
            degraded = True
            selected = "naive"
            reasons.append(f"数据源状态 {q.status}，降级为持久性模型并标注数据延迟")
        elif q.last_sample_age_min > 30:
            degraded = True
            selected = "naive"
            reasons.append(f"最新样本已滞后 {q.last_sample_age_min:.0f} 分钟，降级为持久性模型")
        elif ctx.history_rows < ctx.min_rows:
            # --- D1 数据不足 → NaiveModel ---
            selected = "naive"
            reasons.append(
                f"历史数据 {ctx.history_rows} 行不足最小窗口 {ctx.min_rows} 行，选持久性模型"
            )
        else:
            selected = "nonlinear"  # 默认主力：非线性汇流（特征工程+参数自学习）
            reasons.append(f"历史数据充足（{ctx.history_rows} 行），选用非线性汇流模型（多窗口特征+自学习参数）")

        if ctx.lead_hours in (6, 12):
            reasons.append(f"{ctx.lead_hours}h 预见期强制启用降雨预报序列输入（D1）")

        # --- D2 多源融合权重：w ∝ 1/(1+质量惩罚)，归一化 ---
        level_penalty = 3.0 * q.missing_rate + min(q.last_sample_age_min / 60.0, 1.0)
        rain_penalty = abs(q.rain_bias)
        fcst_penalty = 0.25 * (ctx.lead_hours / 12.0)  # 预见期越长预报越不可信
        w_level = 1.0 / (1.0 + level_penalty)
        w_rain = 1.0 / (1.0 + rain_penalty)
        w_fcst = 1.0 / (1.0 + fcst_penalty)
        total = w_level + w_rain + w_fcst
        weights = {
            "level": round(w_level / total, 3),
            "rain": round(w_rain / total, 3),
            "fcst": round(w_fcst / total, 3),
        }
        if q.missing_rate > 0.1:
            reasons.append(
                f"水位数据缺失率 {q.missing_rate:.0%}，水位源权重下调至 {weights['level']}"
            )

        # --- D3 修正策略：新息超阈值 → 强修正 α=0.6，否则温和修正 α=0.3 ---
        alpha = 0.0
        if self._revision_cfg.enabled and not degraded:
            if abs(ctx.innovation) > self._revision_cfg.innovation_threshold:
                alpha = self._revision_cfg.alpha
                reasons.append(
                    f"新息 {ctx.innovation:+.3f} m 超阈值，启用强修正 α={alpha}"
                )
            else:
                alpha = self._revision_cfg.alpha * 0.5
                reasons.append(f"新息平稳（{ctx.innovation:+.3f} m），温和修正 α={alpha:.2f}")
        elif degraded:
            reasons.append("降级状态下关闭协同修正，仅输出模型原始预测")
        else:
            reasons.append("协同修正已关闭（配置 revision.enabled=false）")

        # --- D4 置信区间自适应：宽度 ∝ 近期RMSE × √h，数据质量差则加宽 ---
        ci_scale = 1.0
        if q.recent_rmse:
            ci_scale *= max(0.5, min(3.0, q.recent_rmse / 0.05))
        if q.missing_rate > 0.05:
            ci_scale *= 1.0 + 2.0 * q.missing_rate
        if degraded:
            ci_scale *= 1.5
        ci_scale = round(ci_scale, 3)

        return ForecastDecision(
            selected_model=selected,
            fusion_weights=weights,
            revision_alpha=round(alpha, 3),
            ci_scale=ci_scale,
            degraded=degraded,
            reason="；".join(reasons),
        )
