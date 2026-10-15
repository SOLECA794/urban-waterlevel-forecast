"""Agent 接口：工具注册表 / 会话消息（EchoAgent 链路）/ 会话列表与轨迹。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import Container, container_dep
from app.core.response import ok
from app.schemas.payloads import AgentMessageIn, ToolInvokeIn

router = APIRouter(tags=["agent"])


@router.get("/tools")
def list_tools(c: Container = Depends(container_dep)):
    """GET /api/v1/tools —— 工具注册表（Agent-B 与 MCP 共用的能力清单）。"""
    return ok(c.tool_registry.schema_payload())


@router.post("/agent/sessions/{session_id}/messages")
async def post_message(
    session_id: str, body: AgentMessageIn, c: Container = Depends(container_dep)
):
    """POST /api/v1/agent/sessions/{id}/messages —— Agent 会话消息。

    本期 EchoAgent（占位）：关键词匹配选工具 → ToolRegistry 执行 → 包装回答，
    工具调用轨迹落 agent_tool_call（兼作审计日志）。SSE 流式返回预留：
    # EXT-POINT(AGENT): 切换流式输出（text/event-stream）待 Agent 推理填充。
    """
    out = await c.agent_service.handle_message(
        session_id, body.message, confirm_token=body.confirm_token
    )
    return ok(out)


@router.get("/agent/sessions")
def list_sessions(c: Container = Depends(container_dep)):
    """GET /api/v1/agent/sessions —— 会话列表（Agent 控制台左栏）。"""
    return ok(c.agent_service.list_sessions())


@router.get("/agent/sessions/{session_id}/messages")
def list_messages(session_id: str, c: Container = Depends(container_dep)):
    """GET /api/v1/agent/sessions/{id}/messages —— 会话消息流。"""
    return ok(c.agent_service.messages(session_id))


@router.get("/agent/sessions/{session_id}/tool-calls")
def list_tool_calls(session_id: str, c: Container = Depends(container_dep)):
    """GET /api/v1/agent/sessions/{id}/tool-calls —— 工具调用轨迹（右栏面板）。"""
    return ok(c.agent_service.tool_calls(session_id))


@router.post("/tools/{tool_name}/invoke")
async def invoke_tool(
    tool_name: str, body: ToolInvokeIn, c: Container = Depends(container_dep)
):
    """POST /api/v1/tools/{name}/invoke —— 直接调用工具（L2 需人工确认令牌）。"""
    result = await c.tool_registry.invoke(
        tool_name, body.args, confirm_token=body.confirm_token
    )
    return ok({"tool": tool_name, "success": result.success,
               "message": result.message, "data": result.data})


# ------------------------------------------------------------------
# 主动巡检（Agent 值班台）
# ------------------------------------------------------------------
@router.get("/agent/patrol/recent")
def recent_patrols(c: Container = Depends(container_dep)):
    """GET /api/v1/agent/patrol/recent —— Agent 最近 N 条主动巡检摘要（值班台/态势横幅读）。"""
    return ok(c.agent_service.recent_patrols(limit=10))


@router.post("/agent/patrol/run")
def run_patrol(c: Container = Depends(container_dep)):
    """POST /api/v1/agent/patrol/run —— 手动触发一次主动巡检（演示/调试用）。"""
    return ok(c.agent_service.patrol())