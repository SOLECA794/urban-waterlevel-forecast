"""EchoAgent（🔶 Agent-B 占位实现）：关键词匹配选中 Tool → 执行 → 包装回答。

无 LLM 也能演示完整「提问 → 选工具 → 执行 → 回答」链路。

# EXT-POINT(AGENT): Agent-B 推理填充位——实现 Agent Port（LangGraph / 自研编排），
# 复用已有 ToolRegistry 与会话三表，前端无需改动（只需打开真实接口开关）。
"""
from __future__ import annotations

import re
from typing import AsyncIterator, Optional

from app.domain.ports.agent import AgentEvent, AgentReply
from app.domain.ports.tool import ToolResult


class EchoAgent:
    """关键词路由的占位 Agent（Agent-B）。"""

    name = "EchoAgent"

    # 关键词 → 工具与参数抽取规则
    _RULES = [
        (r"水位|点位|列表|监测点", "list_stations", {}),
        (r"预警|报警", "get_active_alerts", {}),
        (r"校准|标定", "calibrate_params", {}),
        (r"相似|历史.*事件|类似", "search_similar_events", {}),
        (r"报告|总结", "draft_alert_report", {}),
        (r"准确|精度|误差", "query_forecast_accuracy", {}),
        (r"阈值", "propose_threshold_change", {}),
        (r"为什么|解释|决策", "explain_forecast", {}),
        (r"预测|预报", "run_forecast", {}),
        (r"详情|状态", "get_station_status", {}),
        (r"序列|曲线|历史.*水位", "get_level_series", {}),
    ]

    async def chat(self, session_id: str, message: str) -> AgentReply:
        text = (message or "").strip()
        steps = self._route(text)
        if not steps:
            answer = (
                "我是占位交互智能体（EchoAgent，无 LLM）。我可以按关键词路由工具：\n"
                "· 「监测点/水位」→ list_stations\n"
                "· 「预警」→ get_active_alerts\n"
                "· 「S001 预测 3h」→ run_forecast\n"
                "· 「为什么选这个模型」→ explain_forecast\n"
                "· 「校准」→ calibrate_params；「报告」→ draft_alert_report；"
                "「阈值」→ propose_threshold_change（L2，需确认）\n"
                "# EXT-POINT(AGENT): 填充 LLM 推理后，此处将替换为真实对话编排"
            )
            return AgentReply(session_id=session_id, answer=answer, tool_calls=[])

        station_id = self._extract_station(text)
        lead = self._extract_lead(text)
        for kw, tool, base_args in steps:
            args = dict(base_args)
            if tool in ("run_forecast", "get_station_status", "get_level_series",
                        "explain_forecast", "query_forecast_accuracy"):
                if station_id is not None:
                    args.setdefault("station_id", station_id)
            if tool == "run_forecast" and lead is not None:
                args.setdefault("lead_hours", lead)
            return AgentReply(session_id=session_id, answer="",
                              tool_calls=[{"tool": tool, "args": args}])
        return AgentReply(session_id=session_id, answer="未匹配到可用工具", tool_calls=[])

    def _route(self, text: str):
        out = []
        for pattern, tool, args in self._RULES:
            if re.search(pattern, text):
                out.append((pattern, tool, args))
                if len(out) >= 1:
                    break
        return out

    @staticmethod
    def _extract_station(text: str) -> Optional[int]:
        m = re.search(r"S0*(\d+)", text)
        if m:
            return int(m.group(1))
        m = re.search(r"监测点\s*(\d+)", text)
        if m:
            return int(m.group(1))
        return None

    @staticmethod
    def _extract_lead(text: str) -> Optional[int]:
        m = re.search(r"(\d+)\s*h", text)
        if m and int(m.group(1)) in (1, 3, 6, 12):
            return int(m.group(1))
        return None

    def format_answer(self, tool: str, result: ToolResult) -> str:
        if not result.success:
            return f"【{tool}】执行失败：{result.message}"
        import json as _json

        data_str = _json.dumps(result.data, ensure_ascii=False, default=str)
        if len(data_str) > 1200:
            data_str = data_str[:1200] + "…（截断）"
        return f"【{tool}】{result.message or '执行成功'}\n{data_str}"

    # --- Agent Port 的流式接口（SSE 预留） ---
    async def stream_chat(self, session_id: str, message: str) -> AsyncIterator[AgentEvent]:
        # EXT-POINT(AGENT): SSE 流式输出填充位（token 流 / 工具事件流）
        reply = await self.chat(session_id, message)
        yield AgentEvent(type="message", content=reply.answer)
        yield AgentEvent(type="done")

    async def get_session(self, session_id: str) -> Optional[dict]:
        return {"session_id": session_id, "agent": self.name}
