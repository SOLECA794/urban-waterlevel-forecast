"""SSE 流式接口（🔶 预留）：Agent 流式输出与预警事件推送。"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.deps import Container, container_dep

router = APIRouter(tags=["stream"])


@router.get("/stream/alerts")
async def stream_alerts(c: Container = Depends(container_dep)):
    """GET /api/v1/stream/alerts —— SSE 预警事件推送（预留）。

    # EXT-POINT(INTEGRATION): SSE 推送——本期 REST + 30s 轮询已满足 NFR-7；
    # Agent 阶段在此填充事件总线（预警生成/解除、Agent token 流），
    # 前端 useSSE composable 已就绪，可无改动切换。
    """

    async def gen():
        yield f": ping {json.dumps({'type': 'reserved'})}\n\n".encode()
        payload = {
            "code": 0,
            "message": "ok",
            "data": {"type": "reserved", "note": "SSE 事件推送为预留能力（EXT-POINT(INTEGRATION)），当前无业务事件流"},
        }
        yield f"event: reserved\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
        await asyncio.sleep(0.1)

    return StreamingResponse(gen(), media_type="text/event-stream")
