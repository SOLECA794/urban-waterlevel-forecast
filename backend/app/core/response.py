"""统一响应封装 {code, message, data}（NFR-9）与分页结构 {items,total,page,page_size}。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def ok(data: Any = None, message: str = "ok") -> Dict[str, Any]:
    return {"code": 0, "message": message, "data": data}


def fail(code: int, message: str, data: Any = None) -> Dict[str, Any]:
    return {"code": code, "message": message, "data": data}


def page(items: List[Any], total: int, page_no: int = 1, page_size: int = 20) -> Dict[str, Any]:
    return {"items": items, "total": total, "page": page_no, "page_size": page_size}
