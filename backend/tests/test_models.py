"""占位模型与协同修正契约测试：结构、形态、衰减。"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.core.config import ForecastConfig, RevisionConfig
from app.application.orchestrator import RuleBasedOrchestrator
from app.application.revision_service import ForecastRevisionService
from app.domain.ports.orchestrator import ForecastContext, SourceQuality
from app.infrastructure.forecast.linear_response import LinearResponseModel
from app.infrastructure.forecast.naive_model import NaiveModel
from app.infrastructure.forecast.params import ModelParams


def _window(hours: int = 6) -> pd.DataFrame:
    ts = pd.date_range(end=datetime.now(), periods=hours * 12, freq="5min")
    rng = np.random.default_rng(7)
    rain = np.where(rng.random(len(ts)) < 0.1, rng.uniform(0, 3, len(ts)), 0.0)
    rain[-24:] += 8.0  # 近 2 小时暴雨
    level = np.zeros(len(ts))
    lvl = 1.2
    for i in range(len(ts)):
        lvl += 0.006 * rain[max(0, i - 11):i + 1].sum() / 12 - 0.01 * (lvl - 1.0)
        level[i] = lvl
    future_ts = pd.date_range(ts[-1] + pd.Timedelta(minutes=5), periods=144, freq="5min")
    return pd.DataFrame({
        "ts": list(ts) + list(future_ts),
        "level": list(level) + [np.nan] * 144,
        "rain_observed": list(rain) + [np.nan] * 144,
        "rain_forecast": [np.nan] * len(ts) + list(rng.uniform(0, 2, 144)),
    })


@pytest.mark.parametrize("model_cls", [NaiveModel, LinearResponseModel])
def test_model_contract(model_cls):
    """占位模型返回结构与真模型完全一致（points/peak/CI 一个不少）。"""
    m = model_cls(ModelParams())
    result = m.predict(_window(), horizon_min=180)
    assert len(result.points) == 36
    p = result.points[0]
    assert hasattr(p, "t") and hasattr(p, "level_raw") and hasattr(p, "lower")
    assert result.peak_level >= max(p.level_raw for p in result.points) - 1e-9
    assert result.confidence_interval["upper"] > result.confidence_interval["lower"]
    assert result.model_id and result.inference_ms >= 0


def test_linear_response_rain_causes_rise():
    """降雨驱动 + 退水形态：有雨窗口的预测应高于无雨输入。"""
    m = LinearResponseModel(ModelParams())
    with_rain = m.predict(_window(), horizon_min=180)
    win = _window()
    win["rain_forecast"] = 0.0
    no_rain = m.predict(win, horizon_min=180)
    assert with_rain.peak_level >= no_rain.peak_level - 0.01


def test_ci_widens_with_horizon():
    m = LinearResponseModel(ModelParams())
    r1 = m.predict(_window(), horizon_min=60)
    r12 = m.predict(_window(), horizon_min=720)
    w1 = r1.points[0].upper - r1.points[0].lower
    w12 = r12.points[-1].upper - r12.points[-1].lower
    assert w12 > w1 * 2  # 12h 区间明显更宽（M4 验收）


def test_revision_decays_with_time():
    """修正量随时间衰减：越远的未来修正越少。"""
    svc = ForecastRevisionService(RevisionConfig())
    decision = RuleBasedOrchestrator(RevisionConfig(), ForecastConfig()).decide(
        ForecastContext(station_id=1, history_rows=100, min_rows=72, innovation=0.2)
    )
    raw = [
        type("P", (), {"t": datetime.now() + timedelta(minutes=k * 30),
                       "level_raw": 2.0, "lower": 1.9, "upper": 2.1})()
        for k in range(5)
    ]
    out = svc.apply(raw, decision, innovation=0.2)
    revs = [abs(r) for _, r, _ in out]
    assert all(revs[i] > revs[i + 1] for i in range(len(revs) - 1))


def test_orchestrator_rules():
    orch = RuleBasedOrchestrator(RevisionConfig(), ForecastConfig())
    healthy = orch.decide(ForecastContext(station_id=1, history_rows=200, min_rows=72))
    assert healthy.selected_model == "linear_response" and not healthy.degraded
    stale = orch.decide(ForecastContext(
        station_id=1, history_rows=200, min_rows=72,
        quality=SourceQuality(status="ERROR", last_sample_age_min=999),
    ))
    assert stale.selected_model == "naive" and stale.degraded and "数据延迟" in stale.reason
    insufficient = orch.decide(ForecastContext(station_id=1, history_rows=10, min_rows=72))
    assert insufficient.selected_model == "naive"
    # 数据质量差 → 水位源权重下调（V1.3 验收）
    dirty = orch.decide(ForecastContext(
        station_id=1, history_rows=200, min_rows=72,
        quality=SourceQuality(missing_rate=0.5),
    ))
    assert dirty.fusion_weights["level"] < healthy.fusion_weights["level"]
