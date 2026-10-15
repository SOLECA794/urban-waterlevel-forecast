"""健康检查（NFR-11）：数据源/模型/数据库三态。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import Container, container_dep
from app.core.response import ok
from app.schemas.common import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health")
def health(c: Container = Depends(container_dep)):
    """GET /api/v1/health —— 返回数据源/模型/数据库三态。"""
    return ok(c.health_payload())


@router.get("/health/detail", response_model=None)
def health_detail(c: Container = Depends(container_dep)):
    return ok(HealthOut(**c.health_payload()).model_dump())
