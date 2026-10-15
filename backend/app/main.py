"""FastAPI 入口： lifespan + 统一响应/异常处理 + /api/v1 路由 + 单端口静态托管。

最终部署形态（主控会话指定）：**单端口** —— FastAPI 同时托管 frontend/dist
静态文件与 /api/v1 接口（文档 04 §7.2 为 Nginx + backend 双端口，此处按主控
口径合并，已在交付报告记录）。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import mcp, sse
from app.api.v1 import agent_api, alerts, calibrations, forecasts, health, models, sim_api, stations
from app.core.config import get_settings
from app.core.deps import get_container
from app.core.errors import BizError
from app.core.logging import get_logger, new_trace_id, setup_logging, trace_id_var
from app.core.response import fail

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(log_dir=Path(__file__).resolve().parent.parent / "data" / "logs")
    settings = get_settings()
    container = get_container()
    # 数据源连接（READY/STREAMING）
    await container.datasource.connect({})
    await container.datasource.start_stream(None)
    # 滚动观测生成器：启动即自愈补齐一次（R1/R3，重启后样本立即恢复新鲜）
    container.generator.catch_up()
    # 调度器（滚动预测 + 实况回填 + 生成器 tick）
    container.scheduler.start()
    if settings.app.auto_forecast_on_startup:
        container.scheduler.run_startup_round()
    logger.info("application started", extra={"event": "startup", "trace_id": "-"})
    yield
    container.scheduler.shutdown()
    await container.datasource.disconnect()
    logger.info("application stopped", extra={"event": "shutdown"})


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app.name,
        version="1.0.0",
        description="脚手架 + 可运行原型：数据接入 → 治理 → 预测（Agent-A 编排 + 协同修正）→ 研判 → 预警",
        lifespan=lifespan,
    )

    # ---- 路由 ----
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(stations.router, prefix="/api/v1")
    app.include_router(forecasts.router, prefix="/api/v1")
    app.include_router(alerts.router, prefix="/api/v1")
    app.include_router(models.router, prefix="/api/v1")
    app.include_router(calibrations.router, prefix="/api/v1")
    app.include_router(agent_api.router, prefix="/api/v1")
    app.include_router(sim_api.router, prefix="/api/v1")
    app.include_router(sse.router, prefix="/api/v1")
    app.include_router(mcp.router, prefix="/api/v1")

    # ---- 统一异常处理（{code,message,data}，NFR-8/NFR-9） ----
    @app.exception_handler(BizError)
    async def biz_error_handler(request: Request, exc: BizError):
        logger.warning("biz error %s: %s", exc.code, exc.message,
                       extra={"trace_id": trace_id_var.get()})
        return JSONResponse(status_code=exc.http_status,
                            content=fail(exc.code, exc.message, exc.data))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=200,
            content=fail(400, f"参数校验失败（PARAM_INVALID）：{exc.errors()[:3]}"),
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        logger.exception("unhandled error", extra={"trace_id": trace_id_var.get()})
        return JSONResponse(status_code=500,
                            content=fail(500, f"服务内部错误（INTERNAL_ERROR）：{exc}"))

    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        trace_id_var.set(new_trace_id())
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id_var.get()
        return response

    # ---- 单端口：托管 frontend/dist（SPA fallback） ----
    dist = settings.frontend_dist
    if dist is not None:
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            if full_path.startswith(("api/", "docs", "openapi.json", "redoc")):
                return JSONResponse(status_code=404, content=fail(1404, "资源不存在"))
            candidate = (dist / full_path).resolve()
            try:
                candidate.relative_to(dist.resolve())
            except ValueError:
                candidate = dist / "index.html"
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

        logger.info("static hosting enabled: %s", dist)
    else:
        @app.get("/", include_in_schema=False)
        async def root():
            return fail(1404, "前端构建产物 dist/ 未找到：请先执行 frontend 的 npm run build")
        logger.warning("frontend dist not found; API-only mode")

    return app


app = create_app()
