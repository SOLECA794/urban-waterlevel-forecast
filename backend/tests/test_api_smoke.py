"""接口冒烟测试：覆盖全部 ✅ 形态接口 + 留白接口契约（防止留白被写成 404）。"""
from __future__ import annotations


def _body(resp):
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data.keys()) >= {"code", "message", "data"}, f"响应缺少统一结构: {data}"
    return data


# --- 健康检查 ---
def test_health(client):
    d = _body(client.get("/api/v1/health"))
    assert d["code"] == 0
    assert d["data"]["datasource"]["status"] in ("READY", "STREAMING")
    assert d["data"]["model"]["loaded"] is True
    assert d["data"]["database"]["status"] == "ok"


# --- 监测点 ---
def test_stations_list(client):
    d = _body(client.get("/api/v1/stations"))
    assert d["code"] == 0 and len(d["data"]) >= 6
    item = d["data"][0]
    assert {"station_code", "station_name", "current", "alert", "thresholds"} <= set(item)


def test_station_detail(client):
    d = _body(client.get("/api/v1/stations/1"))
    assert d["code"] == 0 and d["data"]["station_id"] == 1
    assert "alert_stats" in d["data"]


def test_station_series(client):
    d = _body(client.get("/api/v1/stations/1/series?hours=6"))
    assert d["code"] == 0 and len(d["data"]["points"]) > 12
    assert {"ts", "level", "rain_observed"} <= set(d["data"]["points"][0])


def test_station_crud(client):
    d = _body(client.post("/api/v1/stations", json={
        "station_name": "测试点位", "threshold_yellow": 2.0, "base_level": 1.0,
    }))
    assert d["code"] == 0
    sid = d["data"]["station_id"]
    d = _body(client.put(f"/api/v1/stations/{sid}", json={"threshold_yellow": 2.1}))
    assert d["data"]["thresholds"]["yellow"] == 2.1
    d = _body(client.delete(f"/api/v1/stations/{sid}"))
    assert d["data"]["deleted"] is True


# --- 预测（1h/3h/6h/12h 全预见期） ---
def test_predict_all_horizons(client):
    widths = {}
    for lead in (1, 3, 6, 12):
        d = _body(client.post(f"/api/v1/stations/1/predict", json={"lead_hours": lead}))
        assert d["code"] == 0, d
        data = d["data"]
        assert len(data["points"]) == lead * 12  # 5min 步长
        p0 = data["points"][0]
        assert {"t", "level_raw", "level", "lower", "upper"} <= set(p0)
        assert data["decision"]["selected_model"] in ("naive", "linear_response")
        last = data["points"][-1]
        widths[lead] = last["upper"] - last["lower"]  # 预见期末端的区间宽度
    # 预见期越长置信区间越宽（V1.3 验收）
    assert widths[12] > widths[1]
    assert widths[6] > widths[1]


def test_predict_invalid_horizon(client):
    d = _body(client.post("/api/v1/stations/1/predict", json={"lead_hours": 5}))
    assert d["code"] == 400


def test_predict_data_not_enough(client):
    d = _body(client.post("/api/v1/stations", json={"station_name": "空点位"}))
    sid = d["data"]["station_id"]
    d = _body(client.post(f"/api/v1/stations/{sid}/predict", json={"lead_hours": 1}))
    assert d["code"] == 1301  # DATA_NOT_ENOUGH


# --- Agent-A 决策可追溯 ---
def test_decision_traceable(client):
    d = _body(client.post("/api/v1/stations/1/predict", json={"lead_hours": 3}))
    fid = d["data"]["forecast_id"]
    d = _body(client.get(f"/api/v1/forecasts/{fid}/decision"))
    assert d["code"] == 0
    assert d["data"]["selected_model"] in ("naive", "linear_response")
    assert {"level", "rain", "fcst"} <= set(d["data"]["fusion_weights"])
    assert d["data"]["reason"]


# --- 预警 ---
def test_alert_flow(client):
    # S001 暴雨场景：预测应产生预警
    _body(client.post("/api/v1/stations/1/predict", json={"lead_hours": 1}))
    _body(client.post("/api/v1/stations/1/predict", json={"lead_hours": 12}))
    d = _body(client.get("/api/v1/stations/1/alerts"))
    assert d["code"] == 0 and d["data"]["total"] >= 1
    d = _body(client.get("/api/v1/alerts?status=active"))
    assert d["code"] == 0
    ref = [i for i in d["data"]["items"] if i["is_reference"]]
    eff = [i for i in d["data"]["items"] if not i["is_reference"]]
    assert len(ref) >= 1  # 12h 预警为参考级
    for i in ref:
        assert i["lead_hours"] >= 6


def test_current_alert(client):
    d = _body(client.get("/api/v1/stations/1/alert"))
    assert d["code"] == 0 and "alert" in d["data"] and "thresholds" in d["data"]


# --- 模型可插拔（S7） ---
def test_model_switch_changes_curve(client):
    d = _body(client.get("/api/v1/models"))
    models = {m["model_type"]: m for m in d["data"]}
    assert "naive" in models and "linear_response" in models
    mid_linear = models["linear_response"]["model_id"]
    mid_naive = models["naive"]["model_id"]

    _body(client.post(f"/api/v1/models/{mid_linear}/activate"))
    p_linear = _body(client.post("/api/v1/stations/1/predict", json={"lead_hours": 1}))["data"]
    _body(client.post(f"/api/v1/models/{mid_naive}/activate"))
    p_naive = _body(client.post("/api/v1/stations/1/predict", json={"lead_hours": 1}))["data"]
    # 切换模型 → 曲线变化，业务代码不动（S7 验收）
    assert p_linear["peak_level"] != p_naive["peak_level"]
    assert p_naive["decision"]["selected_model"] == "naive"
    _body(client.post(f"/api/v1/models/{mid_linear}/activate"))  # 还原


# --- 参数校准（V1.3 做实）---
def test_calibrate_params(client):
    d = _body(client.get("/api/v1/models"))
    mid = next(m["model_id"] for m in d["data"] if m["model_type"] == "linear_response")
    d = _body(client.post(f"/api/v1/models/{mid}/calibrate-params?station_id=1"))
    assert d["code"] == 0
    assert {"rmse_before", "rmse_after", "params_after"} <= set(d["data"])


# --- 校准重训占位（留白契约）---
def test_retrain_placeholder(client):
    d = _body(client.post("/api/v1/calibrations", json={"station_id": 1}))
    assert d["code"] == 0 and d["data"]["status"] == "pending"
    cid = d["data"]["calibration_id"]
    d = _body(client.get(f"/api/v1/calibrations/{cid}"))
    assert d["data"]["status"] == "pending"


# --- 工具与 Agent ---
def test_tools_registry(client):
    d = _body(client.get("/api/v1/tools"))
    names = [t["name"] for t in d["data"]]
    assert "explain_forecast" in names and "calibrate_params" in names
    assert all(t["risk_level"] in ("L0", "L1", "L2") for t in d["data"])  # 无 L3


def test_l2_tool_requires_confirm(client):
    d = _body(client.post("/api/v1/tools/update_station_threshold/invoke", json={
        "args": {"station_id": 1, "thresholds": {"yellow": 2.05}},
    }))
    assert d["code"] == 1602  # TOOL_CONFIRM_REQUIRED
    d = _body(client.post("/api/v1/tools/update_station_threshold/invoke", json={
        "args": {"station_id": 1, "thresholds": {"yellow": 2.05}},
        "confirm_token": "CONFIRMED",
    }))
    assert d["code"] == 0


def test_agent_chat_flow(client):
    d = _body(client.post("/api/v1/agent/sessions/test-sess-1/messages",
                          json={"message": "查看当前预警"}))
    assert d["code"] == 0
    assert d["data"]["tool_calls"], "应记录工具调用轨迹"
    d2 = _body(client.get("/api/v1/agent/sessions/test-sess-1/tool-calls"))
    assert d2["data"]


def test_tool_not_found(client):
    d = _body(client.post("/api/v1/tools/no_such_tool/invoke", json={"args": {}}))
    assert d["code"] == 1601


# --- SSE / MCP 预留（留白契约：不是 404）---
def test_sse_reserved(client):
    resp = client.get("/api/v1/stream/alerts")
    assert resp.status_code == 200
    assert b"reserved" in resp.content


def test_mcp_reserved(client):
    d = _body(client.get("/api/v1/mcp/capabilities"))
    assert d["data"]["status"] == "reserved"
