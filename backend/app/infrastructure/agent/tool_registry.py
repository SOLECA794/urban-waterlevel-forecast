"""工具注册表（✅ 本期做实）。

register / list / get / invoke；invoke 对 risk_level 做**运行时强制校验**：
L2 工具无人工确认令牌 → 拒绝执行（1602 TOOL_CONFIRM_REQUIRED）。
L3（自动执行）在注册表层面不存在——类型系统只允许 L0/L1/L2。
"""
from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional

from app.core.errors import BizError
from app.core.logging import get_logger
from app.domain.ports.tool import Tool, ToolCallRecord, ToolResult

logger = get_logger("agent.tool_registry")


class ToolRegistry:
    def __init__(self, confirm_token: str = "CONFIRMED"):
        self._tools: Dict[str, Tool] = {}
        self._confirm_token = confirm_token

    def register(self, tool: Tool) -> None:
        if tool.risk_level not in ("L0", "L1", "L2"):
            # L3 自动执行永不做：直接拒绝注册
            raise ValueError(f"工具 {tool.name} 的风险级别 {tool.risk_level} 不允许注册（L3 永不做）")
        self._tools[tool.name] = tool

    def list(self) -> List[Tool]:
        return list(self._tools.values())

    def get(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            raise BizError(1601, f"工具 {name} 不存在（TOOL_NOT_FOUND）")
        return tool

    def schema_payload(self) -> List[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
                "risk_level": t.risk_level,
            }
            for t in self._tools.values()
        ]

    async def invoke(
        self,
        name: str,
        args: Optional[dict] = None,
        confirm_token: Optional[str] = None,
        session_id: Optional[str] = None,
        persist: Optional[Callable[[ToolCallRecord], None]] = None,
    ) -> ToolResult:
        tool = self.get(name)
        if tool.risk_level == "L2":
            if confirm_token != self._confirm_token:
                # L2 必须人工确认（Human-in-the-loop，系统设计约束）
                raise BizError(
                    1602,
                    f"工具 {name} 为 L2 级（建议变更），必须携带人工确认令牌执行"
                    "（TOOL_CONFIRM_REQUIRED）",
                )
        t0 = time.perf_counter()
        try:
            result = await tool.execute(**(args or {}))
            record = ToolCallRecord(
                tool_name=name,
                risk_level=tool.risk_level,
                args=args or {},
                result_summary=str(result.message or "")[:500],
                success=bool(result.success),
                latency_ms=int((time.perf_counter() - t0) * 1000),
                confirmed=True if tool.risk_level == "L2" else None,
            )
        except BizError:
            raise
        except Exception as exc:  # 工具异常不冒泡为 500（NFR-8）
            logger.exception("tool %s failed", name)
            result = ToolResult(success=False, data=None, message=f"工具执行失败：{exc}")
            record = ToolCallRecord(
                tool_name=name, risk_level=tool.risk_level, args=args or {},
                result_summary=str(exc)[:500], success=False,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
        if persist is not None:
            try:
                persist(record)
            except Exception:  # 审计落库失败不影响执行结果
                logger.warning("agent_tool_call 落库失败", exc_info=True)
        return result
