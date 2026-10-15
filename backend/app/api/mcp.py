"""MCP 接入位（🔶 占位）：把 ToolRegistry 暴露为 Model Context Protocol 服务。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import Container, container_dep
from app.core.response import ok

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/capabilities")
def mcp_capabilities(c: Container = Depends(container_dep)):
    """GET /api/v1/mcp/capabilities —— MCP 能力描述（占位）。

    # EXT-POINT(INTEGRATION): MCP Server 填充位——任何支持 MCP 的客户端
    # （Claude Desktop / Cursor / 自研 Agent）都将能直接调用本系统能力；
    # 系统不绑定任何一家 Agent 框架（V1.2 §4.5）。
    """
    return ok({
        "protocol": "mcp",
        "status": "reserved",
        "tools": [t["name"] for t in c.tool_registry.schema_payload()],
        "note": "MCP Server 为预留接入位（EXT-POINT(INTEGRATION)），当前返回能力清单",
    })
