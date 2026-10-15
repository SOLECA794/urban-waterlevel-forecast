"""Agent 会话用例（Agent-B 占位 + Tool 做实）：

提问 → EchoAgent 关键词匹配选工具 → ToolRegistry 执行（风险分级校验）→
回答 + 工具调用轨迹（agent_tool_call 落库，兼作审计日志）。

升级：从被动问答扩展为「主动防汛值班 agent」——
每轮滚动预测后自动 patrol()，综合水位/预警/预测生成人话汛情摘要，
落 agent_message（session_id=system-patrol），前端值班台与态势横幅读取。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import List, Optional

from app.core.logging import get_logger
from app.infrastructure.agent.tool_registry import ToolRegistry
from app.infrastructure.persistence.sqlite_repo import AgentRepository

logger = get_logger("application.agent")

PATROL_SESSION = "system-patrol"
LEVEL_CN = {"blue": "蓝色", "yellow": "黄色", "orange": "橙色", "red": "红色"}


class AgentService:
    def __init__(self, agent_repo: AgentRepository, registry: ToolRegistry, agent,
                 station_service=None, alert_repo=None, forecast_repo=None):
        self._repo = agent_repo
        self._registry = registry
        self._agent = agent  # EchoAgent（关键词路由）
        self._station_svc = station_service
        self._alerts = alert_repo
        self._forecasts = forecast_repo

    def new_session(self, title: Optional[str] = None) -> dict:
        session_id = uuid.uuid4().hex[:12]
        row = self._repo.get_or_create_session(session_id, title)
        return {"session_id": row.session_id, "title": row.title,
                "create_time": row.create_time}

    def list_sessions(self) -> list:
        return [
            {"session_id": s.session_id, "title": s.title,
             "create_time": s.create_time, "status": s.status}
            for s in self._repo.list_sessions()
        ]

    def messages(self, session_id: str) -> list:
        return [
            {"message_id": m.message_id, "role": m.role, "content": m.content,
             "create_time": m.create_time}
            for m in self._repo.list_messages(session_id)
        ]

    def tool_calls(self, session_id: str) -> list:
        return [
            {"call_id": c.call_id, "tool_name": c.tool_name, "risk_level": c.risk_level,
             "args": json.loads(c.args_json) if c.args_json else {},
             "result_summary": c.result_summary, "success": bool(c.success),
             "latency_ms": c.latency_ms, "create_time": c.create_time}
            for c in self._repo.list_tool_calls(session_id)
        ]

    # ------------------------------------------------------------------
    # 主动巡检（Agent 从被动问答 → 值班台主动推送）
    # ------------------------------------------------------------------
    def patrol(self) -> dict:
        """综合当前水位/预警/预测，生成人话汛情摘要并落库。"""
        if self._station_svc is None:
            return {"ok": False, "reason": "station_service not wired"}

        stations = self._station_svc.list_payload()
        enabled = [s for s in stations if s.get("enabled", True)]
        active_alerts, _ = self._alerts.list_page(page=1, page_size=50, status="active") \
            if self._alerts else ([], 0)
        active_valid = [a for a in active_alerts if not a.is_reference]
        active_ref = [a for a in active_alerts if a.is_reference]

        now_hm = datetime.now().strftime("%H:%M")
        lines: List[str] = [f"【自动巡检 {now_hm}】"]
        lines.append(
            f"当前 {len(enabled)} 个监测点在线，"
            f"生效预警 {len(active_valid)} 条"
            + (f"（另有 {len(active_ref)} 条参考级）" if active_ref else "")
            + "。"
        )

        critical = sorted(enabled, key=lambda s: -s["alert"]["rank"])[0] if enabled else None
        if critical and critical["alert"]["rank"] > 0:
            lv = critical["alert"]["level"]
            cur = critical["current"]["level"]
            th_val = critical["thresholds"].get(lv)
            gap = (th_val - cur) if (cur is not None and th_val) else None
            lead = critical["alert"].get("lead_minutes_advantage")
            lead_txt = f"，较阈值报警提前 {lead} 分钟" if lead else ""
            lines.append(
                f"⚠ 重点关注：{critical['station_name']}（{critical['station_code']}）"
                f"触发{LEVEL_CN.get(lv, lv)}预警，当前水位 {cur:.2f} m"
                + (f"，距{LEVEL_CN.get(lv, lv)}阈值 {gap:.2f} m" if gap is not None else "")
                + lead_txt + "。"
            )
            if lv in ("orange", "red"):
                lines.append("建议：立即通知排涝队伍待命，关注上游降雨，必要时启动封路转移。")
            elif lv == "yellow":
                lines.append("建议：安排值班员现场盯守，准备移动排涝泵，关注 1 小时内水位变化。")
            else:
                lines.append("建议：正常值守，关注降雨趋势即可。")
        else:
            rising = []
            for s in enabled:
                cur = s["current"]["level"]
                th_yellow = s["thresholds"].get("yellow")
                if cur is not None and th_yellow and cur > th_yellow * 0.8:
                    rising.append(s)
            if rising:
                names = "、".join(s["station_name"] for s in rising)
                lines.append(f"注意：{names} 水位已接近黄色阈值（>80%），需关注。")
            else:
                lines.append("全域水位平稳，无生效预警，继续正常值守。")

        text = "\n".join(lines)
        self._repo.get_or_create_session(PATROL_SESSION, title="Agent 自动巡检")
        self._repo.add_message(PATROL_SESSION, "assistant", text)

        return {
            "ok": True,
            "time": datetime.now().isoformat(timespec="seconds"),
            "text": text,
            "stations_online": len(enabled),
            "active_alerts": len(active_valid),
            "reference_alerts": len(active_ref),
            "critical_station": critical["station_name"] if critical and critical["alert"]["rank"] > 0 else None,
        }

    def recent_patrols(self, limit: int = 10) -> list:
        """读最近 N 条巡检摘要（前端值班台用）。"""
        msgs = self._repo.list_messages(PATROL_SESSION)
        return [
            {"message_id": m.message_id, "content": m.content, "create_time": m.create_time}
            for m in msgs[-limit:][::-1]
        ]

    async def handle_message(
        self, session_id: str, message: str, confirm_token: Optional[str] = None
    ) -> dict:
        self._repo.get_or_create_session(session_id)
        self._repo.add_message(session_id, "user", message)

        def _persist(record) -> None:
            self._repo.add_tool_call(
                session_id=session_id,
                tool_name=record.tool_name,
                risk_level=record.risk_level,
                args_json=json.dumps(record.args, ensure_ascii=False, default=str),
                result_summary=record.result_summary,
                success=record.success,
                latency_ms=record.latency_ms,
            )

        reply = await self._agent.chat(session_id, message)
        answer_parts: List[str] = []
        for step in reply.tool_calls:
            try:
                result = await self._registry.invoke(
                    step["tool"], step.get("args"), confirm_token=confirm_token,
                    session_id=session_id, persist=_persist,
                )
                answer_parts.append(
                    self._agent.format_answer(step["tool"], result)
                )
            except Exception as exc:
                answer_parts.append(f"工具 {step['tool']} 执行失败：{exc}")
        answer = "\n\n".join(answer_parts) if answer_parts else reply.answer
        self._repo.add_message(session_id, "assistant", answer)
        return {
            "session_id": session_id,
            "answer": answer,
            "tool_calls": self.tool_calls(session_id)[-len(reply.tool_calls):] if reply.tool_calls else [],
            "mode": "echo_agent(占位)：关键词匹配选工具，无 LLM",
        }
