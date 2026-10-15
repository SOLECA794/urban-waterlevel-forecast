"""DataSource Port（04 §5.3 / 05 §4.1）。

状态机：DISCONNECTED → CONNECTING → READY → STREAMING，异常转 ERROR，
恢复后自动重连（FR-1.3 / FR-1.4）。应用层只依赖本抽象，不 import 具体 Adapter。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable, Optional, Protocol, runtime_checkable

import pandas as pd


class SourceStatus(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    READY = "READY"
    STREAMING = "STREAMING"
    ERROR = "ERROR"


@dataclass
class SourceInfo:
    source_code: str
    source_name: str
    type: str
    stations: list = field(default_factory=list)
    interval_minutes: int = 5


@dataclass
class DataBlock:
    """一次采集的数据块：水位 + 实况降雨 +（可选）降雨预报。"""

    station_id: int
    df: pd.DataFrame


@runtime_checkable
class DataSource(Protocol):
    async def connect(self, config: dict) -> SourceInfo: ...
    async def disconnect(self) -> bool: ...
    async def start_stream(
        self, sink: Callable[[DataBlock], Awaitable[None]]
    ) -> bool: ...
    async def stop_stream(self) -> bool: ...
    async def get_status(self) -> SourceStatus: ...
    async def get_series(self, station_id: int, hours: int) -> pd.DataFrame: ...
