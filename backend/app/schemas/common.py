"""统一响应契约：{code, message, data} 与分页 {items,total,page,page_size}。"""
from __future__ import annotations

from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """全局统一响应封装（NFR-9）。前端禁止仅凭 HTTP 200 判定业务成功。"""

    code: int = 0
    message: str = "ok"
    data: Optional[T] = None


class PageData(BaseModel, Generic[T]):
    items: List[T] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class HealthOut(BaseModel):
    status: str
    time: Any = None
    datasource: Dict[str, Any] = {}
    model: Dict[str, Any] = {}
    database: Dict[str, Any] = {}
