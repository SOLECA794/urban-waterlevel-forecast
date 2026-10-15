"""业务错误码与业务异常（05 后端规划书 §6.1）。

约定：HTTP 状态码表达协议层结果；业务 code 表达数据源/预测/模型等应用状态。
前端禁止仅凭 HTTP 200 判定业务成功（NFR-9）。

错误码表中 1102/1404/400/500 为本期扩展码（05 表未覆盖通用资源缺失场景），
已在最终交付报告的“与文档偏离”一节记录。
"""
from __future__ import annotations

from typing import Any, Optional


class ErrorCode:
    OK = 0
    # --- 数据源 ---
    SOURCE_NOT_CONNECTED = 1001
    SOURCE_STREAM_ERROR = 1002
    # --- 监测点 ---
    STATION_STATE_INVALID = 1101
    STATION_NOT_FOUND = 1102          # 扩展码
    # --- 模型 ---
    MODEL_NOT_READY = 1201
    MODEL_INPUT_MISMATCH = 1202
    # --- 数据 ---
    DATA_NOT_ENOUGH = 1301
    DATABASE_ERROR = 1401
    RESOURCE_NOT_FOUND = 1404         # 扩展码（通用资源缺失）
    # --- Agent / 工具 ---
    TOOL_NOT_FOUND = 1601
    TOOL_CONFIRM_REQUIRED = 1602
    # --- 协议层 ---
    PARAM_INVALID = 400               # 扩展码（参数校验失败）
    INTERNAL_ERROR = 500              # 扩展码（未捕获异常）

    DESCRIPTION = {
        0: "OK",
        1001: "SOURCE_NOT_CONNECTED",
        1002: "SOURCE_STREAM_ERROR",
        1101: "STATION_STATE_INVALID",
        1102: "STATION_NOT_FOUND",
        1201: "MODEL_NOT_READY",
        1202: "MODEL_INPUT_MISMATCH",
        1301: "DATA_NOT_ENOUGH",
        1401: "DATABASE_ERROR",
        1404: "RESOURCE_NOT_FOUND",
        1601: "TOOL_NOT_FOUND",
        1602: "TOOL_CONFIRM_REQUIRED",
        400: "PARAM_INVALID",
        500: "INTERNAL_ERROR",
    }


class BizError(Exception):
    """业务异常：路由层捕获后输出统一 {code, message, data}。"""

    def __init__(self, code: int, message: str, data: Any = None, http_status: int = 200):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
        self.http_status = http_status
