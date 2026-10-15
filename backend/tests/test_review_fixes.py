"""评审修复项测试：R1 滚动生成器 / R2 新鲜度 STALE / R3 自愈 / P1-7 事件注入 /
P1-3 实况回填 / P1-5 降级一致性 / P2-9 发布记录。

R1 可测性设计：RollingSimGenerator.tick/catch_up/inject_event 均接受显式
now 参数（可注入时钟），测试不依赖真实时间推进。
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest


def _body(resp):
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data.keys()) >= {"code", "message", "data"}, f"响应缺少统一结构: {data}"
    return data


# ---------------------------------------------------------------------------
# R1：滚动生成器（可注入时钟）
# ---------------------------------------------------------------------------
def _make_generator(tmp_path, stations=None):
    from app.core.config import LinearResponseParams
    from app.infrastructure.datasource.rolling_generator import RollingSimGenerator
    from app.infrastructure.persistence.parquet_store import ParquetTimeSeriesRepository

    ts_repo = ParquetTimeSeriesRepository(tmp_path)
    stations = stations or [{"station_id": 1, "base_level": 1.2, "response_k": 0.008}]
    gen = RollingSimGenerator(ts_repo, lambda: stations, LinearResponseParams(), step_minutes=5)
    return gen, ts_repo


def test_r1_tick_uses_relative_time_and_advances(tmp_path):
    """R1 验收：样本时间戳以 now 为基准滚动前进，data_age 始终 < 10 分钟。"""
    gen, repo = _make_generator(tmp_path)
    t0 = datetime(2026, 10, 3, 10, 2, 30)
    gen.tick(now=t0)
    first = repo.latest(1)
    assert first is not None
    assert first["ts"] == datetime(2026, 10, 3, 10, 0)  # floor 到 5min 步长

    t1 = t0 + timedelta(minutes=6)
    gen.tick(now=t1)
    second = repo.latest(1)
    assert second["ts"] == datetime(2026, 10, 3, 10, 5)
    # 连续两次采样（间隔 6 分钟）：最新样本滞后 < 10 分钟（§9 验收口径）
    assert (t1 - second["ts"]) < timedelta(minutes=10)
    assert second["ts"] > first["ts"]


def test_r1_tick_does_not_duplicate_samples(tmp_path):
    gen, repo = _make_generator(tmp_path)
    t0 = datetime(2026, 10, 3, 10, 0)
    gen.tick(now=t0)
    gen.tick(now=t0 + timedelta(seconds=30))  # 未到下一采样点
    df = repo.read_series(1)
    assert len(df) == len(df.drop_duplicates(subset="ts"))


def test_r1_multi_station_and_level_continuity(tmp_path):
    stations = [
        {"station_id": 1, "base_level": 1.2, "response_k": 0.008},
        {"station_id": 2, "base_level": 1.0, "response_k": 0.010},
    ]
    gen, repo = _make_generator(tmp_path, stations)
    t0 = datetime(2026, 10, 3, 10, 0)
    for i in range(5):
        gen.tick(now=t0 + timedelta(minutes=5 * i))
    df = repo.read_series(2)
    assert list(df["ts"])[-1] == datetime(2026, 10, 3, 10, 20)
    # 水位在基流附近、非负、无 NaN
    assert df["level"].notna().all()
    assert (df["level"] > 0).all()


# ---------------------------------------------------------------------------
# R2：健康检查纳入新鲜度（纯函数判定）
# ---------------------------------------------------------------------------
def test_r2_evaluate_source_status():
    from app.infrastructure.datasource.simulated_source import STALE_STATUS, evaluate_source_status

    # 链路正常 + 样本新鲜 → 维持 STREAMING
    assert evaluate_source_status("STREAMING", 5.0, 30)[0] == "STREAMING"
    # 链路正常但样本滞后 45 分钟 → STALE（评审取证场景：误报「运行正常」的修复）
    status, detail = evaluate_source_status("STREAMING", 166.6, 30)
    assert status == STALE_STATUS
    assert "滞后" in detail
    # 链路异常优先于新鲜度
    assert evaluate_source_status("ERROR", 1.0, 30)[0] == "ERROR"
    # 无样本不崩溃
    assert evaluate_source_status("READY", None, 30)[0] == "READY"


# ---------------------------------------------------------------------------
# R2 + R3：容器健康检查（共享测试容器）
# ---------------------------------------------------------------------------
def test_r2_health_reports_stale_when_generator_blocked(client):
    """人为让样本「过旧」→ 健康检查必须改判 STALE，不再误报运行正常。"""
    from app.core.deps import get_container

    c = get_container()
    orig_fresh = c.generator.freshness_age_minutes
    orig_catch_up = c.generator.catch_up
    try:
        c.generator.freshness_age_minutes = lambda *a, **k: 45.0  # 样本滞后 45 分钟
        c.generator.catch_up = lambda *a, **k: 0                  # 屏蔽自愈，观察 STALE 判定
        d = _body(client.get("/api/v1/health"))
        ds = d["data"]["datasource"]
        assert ds["status"] == "STALE"
        assert "滞后" in ds["detail"]
        assert d["data"]["status"] == "stale"
        assert ds["data_age_min"] == 45.0
    finally:
        c.generator.freshness_age_minutes = orig_fresh
        c.generator.catch_up = orig_catch_up


def test_r3_health_self_heals_stale_generator(client):
    """R3：STALE 触发自动补齐后，样本恢复新鲜（data_age_min < 10）。"""
    from app.core.deps import get_container

    c = get_container()
    orig_fresh = c.generator.freshness_age_minutes
    orig_catch_up = c.generator.catch_up
    state = {"age_calls": 0, "heals": 0}

    def fake_age(*a, **k):
        state["age_calls"] += 1
        return 45.0 if state["age_calls"] == 1 else 2.0  # 自愈前 45min → 自愈后 2min

    def fake_catch_up(*a, **k):
        state["heals"] += 1
        return 12

    try:
        c.generator.freshness_age_minutes = fake_age
        c.generator.catch_up = fake_catch_up
        d = _body(client.get("/api/v1/health"))
        ds = d["data"]["datasource"]
        assert state["heals"] == 1, "STALE 时应触发生成器自愈"
        assert ds["status"] in ("READY", "STREAMING")
        assert ds["data_age_min"] == 2.0
        assert "自动恢复" in ds["detail"]
    finally:
        c.generator.freshness_age_minutes = orig_fresh
        c.generator.catch_up = orig_catch_up


# ---------------------------------------------------------------------------
# P1-7：极端降雨事件注入（演示钥匙）
# ---------------------------------------------------------------------------
def test_p1_7_inject_requires_demo_key(client):
    d = _body(client.post("/api/v1/sim/events", json={
        "station_id": 1, "intensity": "extreme", "demo_key": "wrong-key",
    }))
    assert d["code"] == 1403


def test_p1_7_inject_rejects_bad_intensity(client):
    d = _body(client.post("/api/v1/sim/events", json={
        "station_id": 1, "intensity": "typhoon", "demo_key": "FANGXUN-DEMO",
    }))
    assert d["code"] == 400


def test_p1_7_inject_event_rain_reaches_observed_and_forecast(tmp_path):
    """注入 → 观测雨强/水位抬升 + 未来真值可见（预测链路能提前看到上涨）。"""
    gen, repo = _make_generator(tmp_path)
    t0 = datetime(2026, 10, 3, 10, 0)
    gen.tick(now=t0)
    gen.tick(now=t0 + timedelta(minutes=5))
    before_level = repo.latest(1)["level"]

    ev = gen.inject_event(1, "extreme", now=t0 + timedelta(minutes=6))
    assert ev["event_id"] and ev["peak_mm_per_step"] > 0

    # 未来真值文件已包含事件雨量（降雨预报取数来源）
    fut = pd.read_parquet(tmp_path / "station_1_future.parquet")
    assert fut["rain_true"].sum() > 0

    # 推进穿过事件窗口：观测雨强出现峰值、水位明显抬升
    peak_rain = 0.0
    for i in range(1, 26):
        gen.tick(now=t0 + timedelta(minutes=6 + 5 * i))
        peak_rain = max(peak_rain, float(repo.read_series(1).iloc[-1]["rain_observed"]))
    assert peak_rain >= ev["peak_mm_per_step"] * 0.8
    after_level = repo.latest(1)["level"]
    assert after_level > before_level + 0.05  # 水位抬升可见


def test_p1_7_inject_api_flow(client):
    """API 全链路：钥匙校验 → 注入成功 → 事件列表可见 → 触发预测不报错。"""
    d = _body(client.post("/api/v1/sim/events", json={
        "station_id": 1, "intensity": "extreme", "demo_key": "FANGXUN-DEMO",
    }))
    assert d["code"] == 0
    assert d["data"]["event_id"]
    assert d["data"]["prediction_triggered"] is True

    d2 = _body(client.get("/api/v1/sim/events"))
    assert any(e["event_id"] == d["data"]["event_id"] for e in d2["data"])

    # 注入后可正常预测（后台预测线程异步执行，此处验证主链路不被破坏）
    d3 = _body(client.post("/api/v1/stations/1/predict", json={"lead_hours": 1}))
    assert d3["code"] == 0


# ---------------------------------------------------------------------------
# P1-3：actual_level 滚动回填（RMSE 不再空转）
# ---------------------------------------------------------------------------
def test_p1_3_backfill_actual_and_rmse(client):
    from app.core.deps import get_container
    from app.domain.models import ForecastPoint

    c = get_container()
    d = _body(client.post("/api/v1/stations/1/predict", json={"lead_hours": 1}))
    fid = d["data"]["forecast_id"]

    # 模拟「目标时刻一过、实测已落地」：把前 6 个点的 target_time 挪到最近样本时刻
    latest = c.ts_repo.latest(1)
    assert latest is not None
    target = latest["ts"]
    with c.session_factory() as s:
        pts = (
            s.query(ForecastPoint)
            .filter(ForecastPoint.forecast_id == fid)
            .order_by(ForecastPoint.lead_minutes)
            .limit(6)
            .all()
        )
        for p in pts:
            p.target_time = target
        s.commit()

    n = c.forecast_service.backfill_actuals()
    assert n >= 6

    d2 = _body(client.get("/api/v1/stations/1/forecasts"))
    row = next(r for r in d2["data"]["items"] if r["forecast_id"] == fid)
    assert row["rmse"] is not None  # RMSE 有值（评审 P1-3 后端闭环）


# ---------------------------------------------------------------------------
# P1-5：降级态 D1 一致性（实际执行模型）
# ---------------------------------------------------------------------------
def test_p1_5_degraded_ignores_manual_model(client):
    """降级时人工指定 linear_response 也必须实际执行 naive，D1 不自相矛盾。"""
    from app.core.deps import get_container

    c = get_container()
    d = _body(client.post("/api/v1/stations", json={
        "station_name": "降级一致性测试点", "base_level": 1.0,
    }))
    sid = d["data"]["station_id"]

    # 100 行历史，但全部结束于 2 小时前 → 样本滞后 120min > 30min → D5 降级
    end = datetime.now() - timedelta(hours=2)
    ts = pd.date_range(end=end, periods=100, freq="5min")
    c.ts_repo.write_series(sid, pd.DataFrame({"ts": ts, "level": 1.0, "rain_observed": 0.0}))

    models = _body(client.get("/api/v1/models"))["data"]
    mid = next(m["model_id"] for m in models if m["model_type"] == "linear_response")

    d = _body(client.post(f"/api/v1/stations/{sid}/predict",
                          json={"lead_hours": 1, "model_id": mid}))
    assert d["code"] == 0
    data = d["data"]
    assert data["degraded"] is True
    assert data["model_type"] == "naive"                      # 实际执行模型
    assert data["decision"]["selected_model"] == "naive"      # D1 与实际一致
    assert "忽略人工指定模型" in data["decision"]["reason"]
    # 横幅（degraded）与 D1 同源同值：两侧都来自 decision.degraded + selected_model
    assert (data["degraded"] and data["decision"]["degraded"]) is True


# ---------------------------------------------------------------------------
# P2-9：发布记录（mock 通道 + EXT-POINT 标注）
# ---------------------------------------------------------------------------
def test_p2_9_publish_records(client):
    # 先确保至少有一条预警
    _body(client.post("/api/v1/stations/1/predict", json={"lead_hours": 1}))
    d = _body(client.get("/api/v1/alerts/publish-records"))
    assert d["code"] == 0
    items = d["data"]["items"]
    assert items, "应有发布记录"
    channels = {i["channel_code"] for i in items}
    assert {"IN_APP", "INFO_SCREEN", "SMS"} <= channels
    # 短信为占位渠道：状态 placeholder + EXT-POINT 标注
    sms = [i for i in items if i["channel_code"] == "SMS"]
    assert all(i["status"] == "placeholder" for i in sms)
    assert all("EXT-POINT(INTEGRATION)" in (i["detail"] or "") for i in sms)
    # 站内消息已发送、信息屏模拟下发
    assert all(i["status"] == "sent" for i in items if i["channel_code"] == "IN_APP")
    assert all(i["status"] == "simulated" for i in items if i["channel_code"] == "INFO_SCREEN")


# ---------------------------------------------------------------------------
# 增量回归：health 新增字段不破坏原契约
# ---------------------------------------------------------------------------
def test_health_payload_includes_freshness_fields(client):
    d = _body(client.get("/api/v1/health"))
    ds = d["data"]["datasource"]
    assert {"type", "status", "detail", "data_age_min"} <= set(ds.keys())
    assert d["data"]["database"]["status"] == "ok"
