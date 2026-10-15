"""结构化日志（JSON 行格式），trace_id 贯穿一次预测生命周期。

说明：文档口径为 structlog；为保证依赖极简（NFR-1/依赖极简约束），本期用
标准库 logging + JSON 格式化器实现同等能力，属已记录的实现层偏离。
日志按天滚动（NFR-11）。
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import sys
import time
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Optional

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "trace_id": trace_id_var.get(),
            "msg": record.getMessage(),
        }
        for key in ("station_id", "forecast_id", "lead_hours", "model", "tool", "session_id", "event"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO", log_dir: Optional[Path] = None) -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = JsonFormatter()
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.TimedRotatingFileHandler(
            log_dir / "app.log", when="midnight", backupCount=14, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)


def new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
