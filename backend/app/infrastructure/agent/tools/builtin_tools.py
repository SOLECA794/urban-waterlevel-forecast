"""内置工具集（V1.2 §4.3 清单）：L0 只读 / L1 生成内容 / L2 建议变更。

L2 执行必须携带人工确认令牌（ToolRegistry.invoke 运行时强制校验）；
L3（自动执行）永不做——防汛预警发布责任必须由人承担。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

from app.core.errors import BizError
from app.domain.ports.tool import ToolResult


def _schema(props: Dict[str, Any], required: Optional[list] = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


# ---------------------------------------------------------------------------
# L0 只读
# ---------------------------------------------------------------------------
class ListStationsTool:
    name = "list_stations"
    description = "列出全部监测点及当前水位、预警等级、数据新鲜度"
    parameters = _schema({})
    risk_level = "L0"

    def __init__(self, station_service):
        self._svc = station_service

    async def execute(self, **kwargs) -> ToolResult:
        rows = self._svc.list_payload()
        brief = [
            {"station_code": r["station_code"], "name": r["station_name"],
             "level": r["current"]["level"], "alert": r["alert"]["level"],
             "enabled": r["enabled"]}
            for r in rows
        ]
        return ToolResult(True, brief, f"共 {len(brief)} 个监测点")


class GetStationStatusTool:
    name = "get_station_status"
    description = "查询单个监测点详情：当前水位、阈值、生效预警与统计"
    parameters = _schema({"station_id": {"type": "integer", "description": "监测点ID"}}, ["station_id"])
    risk_level = "L0"

    def __init__(self, station_service):
        self._svc = station_service

    async def execute(self, station_id: int, **kwargs) -> ToolResult:
        return ToolResult(True, self._svc.detail_payload(int(station_id)), "查询成功")


class GetLevelSeriesTool:
    name = "get_level_series"
    description = "查询历史水位/降雨序列（默认最近 6 小时，5 分钟步长）"
    parameters = _schema({
        "station_id": {"type": "integer"},
        "hours": {"type": "integer", "description": "回溯小时数，默认 6"},
    }, ["station_id"])
    risk_level = "L0"

    def __init__(self, ts_repo):
        self._ts_repo = ts_repo

    async def execute(self, station_id: int, hours: int = 6, **kwargs) -> ToolResult:
        from datetime import datetime, timedelta

        df = self._ts_repo.read_series(
            int(station_id), start=datetime.now() - timedelta(hours=int(hours))
        )
        if df.empty:
            return ToolResult(False, None, "该点位无时序数据")
        pts = [
            {"ts": str(r["ts"]), "level": round(float(r["level"]), 3),
             "rain": round(float(r["rain_observed"]), 2)}
            for _, r in df.tail(48).iterrows()
        ]
        return ToolResult(True, {"station_id": int(station_id), "points": pts},
                          f"返回最近 {len(pts)} 个采样点")


class RunForecastTool:
    name = "run_forecast"
    description = "对某监测点发起水位预测（Agent-A 编排 + 占位模型 + 协同修正）"
    parameters = _schema({
        "station_id": {"type": "integer"},
        "lead_hours": {"type": "integer", "enum": [1, 3, 6, 12], "description": "预见期"},
    }, ["station_id"])
    risk_level = "L0"

    def __init__(self, forecast_service):
        self._svc = forecast_service

    async def execute(self, station_id: int, lead_hours: int = 1, **kwargs) -> ToolResult:
        out = self._svc.run_prediction(int(station_id), int(lead_hours))
        return ToolResult(
            True,
            {"forecast_id": out["forecast_id"], "peak_level": out["peak_level"],
             "peak_time": str(out["peak_time"]), "decision": out["decision"],
             "alert": out["alert"]},
            f"预测完成：峰值 {out['peak_level']} m @ {out['peak_time']}",
        )


class GetActiveAlertsTool:
    name = "get_active_alerts"
    description = "查询当前全部生效预警（含参考级标记）"
    parameters = _schema({})
    risk_level = "L0"

    def __init__(self, alert_repo, station_repo):
        self._alerts = alert_repo
        self._stations = station_repo

    async def execute(self, **kwargs) -> ToolResult:
        rows, _ = self._alerts.list_page(page=1, page_size=50, status="active")
        names = {s.station_id: s.station_name for s in self._stations.list()}
        out = [
            {"alert_id": a.alert_id, "station": names.get(a.station_id, a.station_id),
             "level": a.level, "is_reference": bool(a.is_reference),
             "peak": a.peak_level, "reason": (a.reason or "")[:120],
             "lead_minutes_advantage": a.lead_minutes_advantage}
            for a in rows
        ]
        return ToolResult(True, out, f"生效预警 {len(out)} 条（含参考级）")


# ---------------------------------------------------------------------------
# L1 生成内容
# ---------------------------------------------------------------------------
class ExplainAlertTool:
    name = "explain_alert"
    description = "解释某条预警的成因：阈值、峰值、预见期、触发时间与提前量"
    parameters = _schema({"alert_id": {"type": "integer"}}, ["alert_id"])
    risk_level = "L1"

    def __init__(self, alert_repo, station_repo):
        self._alerts = alert_repo
        self._stations = station_repo

    async def execute(self, alert_id: int, **kwargs) -> ToolResult:
        a = self._alerts.get(int(alert_id))
        if a is None:
            raise BizError(1404, f"预警 {alert_id} 不存在（RESOURCE_NOT_FOUND）")
        st = self._stations.get(a.station_id)
        text = (
            f"预警 #{a.alert_id}：{st.station_name if st else a.station_id} "
            f"触发{a.level}级预警。{a.reason or ''} "
            + (f"本次预警较传统阈值报警提前 {a.lead_minutes_advantage} 分钟。" 
               if a.lead_minutes_advantage else "")
            + ("（参考级预警，由 6h/12h 长预见期生成，仅供参考）" if a.is_reference else "")
        )
        return ToolResult(True, {"alert_id": a.alert_id, "explanation": text}, "解释生成")


class ExplainForecastTool:
    """打通双层 Agent：直接读 Agent-A 的 forecast_decision 翻译成人话（V1.3）。"""

    name = "explain_forecast"
    description = "解释 Agent-A 的编排决策：为何选此模型、融合权重、修正强度与置信区间"
    parameters = _schema({"forecast_id": {"type": "integer", "description": "预测ID，缺省取最近一次"}},
                         [])
    risk_level = "L1"

    def __init__(self, forecast_repo, station_repo):
        self._forecasts = forecast_repo
        self._stations = station_repo

    async def execute(self, forecast_id: Optional[int] = None, **kwargs) -> ToolResult:
        if forecast_id is None:
            # 缺省取全局最近一次预测
            latest = None
            for st in self._stations.list():
                f = self._forecasts.latest_for_station(st.station_id)
                if f and (latest is None or f.forecast_id > latest.forecast_id):
                    latest = f
            if latest is None:
                return ToolResult(False, None, "系统尚无预测记录")
            f = latest
        else:
            f = self._forecasts.get(int(forecast_id))
            if f is None:
                raise BizError(1404, f"预测 {forecast_id} 不存在（RESOURCE_NOT_FOUND）")
        d = self._forecasts.get_decision(f.forecast_id)
        if d is None:
            return ToolResult(False, {"forecast_id": f.forecast_id}, "该预测无编排决策记录")
        try:
            weights = json.loads(d.fusion_weights) if d.fusion_weights else {}
        except (ValueError, TypeError):
            weights = {}
        st = self._stations.get(f.station_id)
        text = (
            f"预测 #{f.forecast_id}（{st.station_name if st else f.station_id}，"
            f"预见期 {f.lead_hours}h）："
            f"D1 选择「{d.selected_model}」模型；"
            f"D2 多源融合权重 水位{weights.get('level')}/降雨{weights.get('rain')}"
            f"/预报{weights.get('fcst')}；"
            f"D3 修正强度 α={d.revision_alpha}；"
            f"D4 置信区间系数 ×{d.ci_scale}；"
            f"D5 {'已降级（数据延迟）' if d.degraded else '未降级'}。"
            f"决策理由：{d.reason}"
        )
        return ToolResult(True, {"forecast_id": f.forecast_id, "explanation": text,
                                 "decision": {
                                     "selected_model": d.selected_model,
                                     "fusion_weights": weights,
                                     "revision_alpha": d.revision_alpha,
                                     "ci_scale": d.ci_scale,
                                     "degraded": bool(d.degraded),
                                     "reason": d.reason,
                                 }}, "决策解释生成")


class CalibrateParamsTool:
    name = "calibrate_params"
    description = "对 LinearResponseModel 做参数标定（网格搜索 gain/response_k），返回前后误差对比"
    parameters = _schema({
        "model_id": {"type": "integer", "description": "缺省取当前激活模型"},
        "station_id": {"type": "integer"},
    }, ["station_id"])
    risk_level = "L1"

    def __init__(self, calibration_service, model_repo):
        self._svc = calibration_service
        self._models = model_repo

    async def execute(self, station_id: int, model_id: Optional[int] = None, **kwargs) -> ToolResult:
        mid = model_id
        if mid is None:
            active = self._models.get_active()
            mid = active.model_id if active else None
        if mid is None:
            raise BizError(1201, "无可用模型（MODEL_NOT_READY）")
        out = self._svc.calibrate_params(int(mid), int(station_id))
        return ToolResult(True, out,
                          f"RMSE {out['rmse_before']} → {out['rmse_after']}（提升 {out['improved_pct']}%）")


class QueryForecastAccuracyTool:
    name = "query_forecast_accuracy"
    description = "查询某监测点近期预测误差（基于逐点实况回填计算 RMSE/MAE）"
    parameters = _schema({"station_id": {"type": "integer"}}, ["station_id"])
    risk_level = "L1"

    def __init__(self, forecast_repo):
        self._forecasts = forecast_repo

    async def execute(self, station_id: int, **kwargs) -> ToolResult:
        # EXT-POINT(ALGORITHM): 完整精度指标位——RMSE/MAE 已实现，
        # 峰值误差/峰值时间误差/POD/FAR/CSI 在此扩展（口径已由 forecast_point 预留）。
        rows, _ = self._forecasts.list_for_station(int(station_id), page=1, page_size=20)
        scored = [f for f in rows if f.rmse is not None]
        if not scored:
            return ToolResult(False, {"station_id": int(station_id)},
                              "暂无已回填实况的预测（滚动预测运行一段时间后再查询）")
        avg_rmse = sum(f.rmse for f in scored) / len(scored)
        return ToolResult(
            True,
            {"station_id": int(station_id), "scored_forecasts": len(scored),
             "avg_rmse": round(avg_rmse, 4),
             "recent": [{"forecast_id": f.forecast_id, "lead_hours": f.lead_hours,
                         "rmse": f.rmse, "mae": f.mae} for f in scored[:5]]},
            f"近期平均 RMSE {avg_rmse:.4f} m（{len(scored)} 次可评分预测）",
        )


class DraftAlertReportTool:
    name = "draft_alert_report"
    description = "基于当前生效预警生成结构化预警报告草稿（人工审阅后使用）"
    parameters = _schema({})
    risk_level = "L1"

    def __init__(self, alert_repo, station_repo):
        self._alerts = alert_repo
        self._stations = station_repo

    async def execute(self, **kwargs) -> ToolResult:
        # EXT-POINT(AGENT): LLM 增强位——结构化草稿由模板生成，叙述段落待接入 LLM。
        rows, _ = self._alerts.list_page(page=1, page_size=50, status="active")
        names = {s.station_id: s.station_name for s in self._stations.list()}
        report = {
            "title": "汛情预警报告（草稿）",
            "generated_at": str(datetime.now()),
            "effective_alerts": len([a for a in rows if not a.is_reference]),
            "reference_alerts": len([a for a in rows if a.is_reference]),
            "items": [
                {"station": names.get(a.station_id, a.station_id), "level": a.level,
                 "peak": a.peak_level, "reason": a.reason,
                 "lead_minutes_advantage": a.lead_minutes_advantage,
                 "is_reference": bool(a.is_reference)}
                for a in rows
            ],
            "note": "草稿仅供值班员参考，发布需人工确认（L3 永不做）",
        }
        return ToolResult(True, report, f"报告草稿已生成（{len(rows)} 条预警）")


class SearchSimilarEventsTool:
    name = "search_similar_events"
    description = "检索历史相似内涝事件（按站点/峰值水位过滤）"
    parameters = _schema({
        "station_id": {"type": "integer", "description": "缺省查全部"},
        "peak_min": {"type": "number", "description": "峰值水位下限(m)"},
    }, [])
    risk_level = "L1"

    def __init__(self, event_repo):
        self._events = event_repo

    async def execute(self, station_id: Optional[int] = None,
                      peak_min: Optional[float] = None, **kwargs) -> ToolResult:
        # EXT-POINT(INTEGRATION): 向量相似检索位——当前为结构化过滤；
        # 知识库阶段引入向量数据库前，先用 DuckDB 全文/数值检索兜底。
        rows = self._events.search_similar(
            int(station_id) if station_id else None,
            float(peak_min) if peak_min is not None else None,
        )
        out = [
            {"event_id": e.event_id, "station_id": e.station_id,
             "start_time": str(e.start_time), "peak_level": e.peak_level,
             "total_rainfall": e.total_rainfall, "max_alert_level": e.max_alert_level,
             "response_actions": e.response_actions}
            for e in rows
        ]
        return ToolResult(True, out, f"命中 {len(out)} 条历史事件")


# ---------------------------------------------------------------------------
# L2 建议变更（执行必须人工确认）
# ---------------------------------------------------------------------------
class ProposeThresholdChangeTool:
    name = "propose_threshold_change"
    description = "建议调整监测点阈值（给出依据，不直接修改；执行需人工确认 L2）"
    parameters = _schema({
        "station_id": {"type": "integer"},
        "level": {"type": "string", "enum": ["blue", "yellow", "orange", "red"]},
        "new_value": {"type": "number"},
    }, ["station_id"])
    risk_level = "L2"

    def __init__(self, station_repo, alert_repo):
        self._stations = station_repo
        self._alerts = alert_repo

    async def execute(self, station_id: int, level: Optional[str] = None,
                      new_value: Optional[float] = None, **kwargs) -> ToolResult:
        # EXT-POINT(AGENT): 建议生成算法位——当前基于近期预警频次的简单规则，
        # 可升级为基于 POD/FAR 的统计建议或 LLM 依据说明。
        st = self._stations.get(int(station_id))
        if st is None:
            raise BizError(1102, "监测点不存在（STATION_NOT_FOUND）")
        alerts, _ = self._alerts.list_page(page=1, page_size=200, station_id=st.station_id)
        freq = len(alerts)
        suggestion = (
            f"建议：{st.station_name} 近期预警 {freq} 条。"
            + ("预警频次偏高，建议上调黄色阈值 0.1–0.2 m 以减少误报；"
               if freq >= 5 else "预警频次正常，可维持现有阈值。")
        )
        return ToolResult(
            True,
            {"station_id": st.station_id, "suggestion": suggestion,
             "requested": {"level": level, "new_value": new_value},
             "requires_confirm": True,
             "confirm_hint": "确认执行请携带 confirm_token 调用本工具或使用设置页"},
            suggestion,
        )


class UpdateStationThresholdTool:
    name = "update_station_threshold"
    description = "实际修改监测点四级阈值（L2：必须携带人工确认令牌 confirm_token）"
    parameters = _schema({
        "station_id": {"type": "integer"},
        "thresholds": {"type": "object", "description": "{blue,yellow,orange,red}，至少一项"},
    }, ["station_id", "thresholds"])
    risk_level = "L2"

    def __init__(self, station_service):
        self._svc = station_service

    async def execute(self, station_id: int, thresholds: dict, **kwargs) -> ToolResult:
        allowed = {"blue", "yellow", "orange", "red"}
        fields = {}
        for k, v in (thresholds or {}).items():
            if k in allowed and v is not None:
                fields[f"threshold_{k}"] = float(v)
        if not fields:
            raise BizError(400, "未提供有效阈值字段（PARAM_INVALID）")
        self._svc.update(int(station_id), **fields)
        return ToolResult(True, {"station_id": int(station_id), "updated": fields},
                          "阈值已更新（人工确认已通过，下次研判立即生效）")


def build_tools(container) -> list:
    """按依赖组装全部工具（Tool 本期做实：REST 与 Tool 共用同一批 Service）。"""
    return [
        ListStationsTool(container.station_service),
        GetStationStatusTool(container.station_service),
        GetLevelSeriesTool(container.ts_repo),
        RunForecastTool(container.forecast_service),
        GetActiveAlertsTool(container.alert_repo, container.station_repo),
        ExplainAlertTool(container.alert_repo, container.station_repo),
        ExplainForecastTool(container.forecast_repo, container.station_repo),
        CalibrateParamsTool(container.calibration_service, container.model_repo),
        QueryForecastAccuracyTool(container.forecast_repo),
        DraftAlertReportTool(container.alert_repo, container.station_repo),
        SearchSimilarEventsTool(container.event_repo),
        ProposeThresholdChangeTool(container.station_repo, container.alert_repo),
        UpdateStationThresholdTool(container.station_service),
    ]
