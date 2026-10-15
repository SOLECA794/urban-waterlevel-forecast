"""Agent Port（V1.2 新增，本期占位）：Agent-B 交互智能体（对话式）。

本期 EchoAgent 占位：关键词匹配选工具 → 执行 → 包装回答；
无 LLM 也能演示「提问 → 选工具 → 执行 → 回答」完整链路。
将来填充：实现本 Port（LangGraph 或自研编排），调用方不变。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Optional, Protocol, runtime_checkable


@dataclass
class AgentEvent:
    """流式事件（SSE 预留）。type: message / tool_call / token / done"""

    type: str
    content: str = ""
    payload: dict = field(default_factory=dict)


@dataclass
class AgentReply:
    """非流式回复（REST 通道本期使用）。"""

    session_id: str
    answer: str
    tool_calls: list = field(default_factory=list)  # list[ToolCallRecord]


@runtime_checkable
class Agent(Protocol):
    async def chat(self, session_id: str, message: str) -> AsyncIterator[AgentEvent]: ...
    async def get_session(self, session_id: str) -> Optional[dict]: ...
