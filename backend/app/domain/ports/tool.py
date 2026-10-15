"""Tool Port（V1.2 新增，本期做实）：把系统能力暴露为可被 Agent 调用的函数。

risk_level 运行时强制校验：L2 无人工确认令牌则拒绝执行（1602）。
L3（自动执行）永不做——防汛预警发布责任必须由人承担（系统设计约束）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional, Protocol, runtime_checkable

RiskLevel = Literal["L0", "L1", "L2"]


@dataclass
class ToolResult:
    success: bool = True
    data: Any = None
    message: str = ""


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str            # 给 LLM 看的用途说明
    parameters: Dict[str, Any]  # JSON Schema
    risk_level: RiskLevel

    async def execute(self, **kwargs) -> ToolResult: ...


@dataclass
class ToolCallRecord:
    """一次工具调用的轨迹（落 agent_tool_call 表，兼作审计日志）。"""

    tool_name: str
    risk_level: str
    args: Dict[str, Any] = field(default_factory=dict)
    result_summary: str = ""
    success: bool = True
    latency_ms: int = 0
    confirmed: Optional[bool] = None
