"""仓储抽象（ADR-2）：时序读写收敛到 TimeSeriesRepository，业务层不写具体引擎 SQL。

将来换 TimescaleDB / IoTDB 只改实现类，业务层不动。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class TimeSeriesRepository(Protocol):
    """原始水位/降雨序列读写（Parquet 实现，分析查询走 DuckDB）。"""

    def write_series(self, station_id: int, df: pd.DataFrame) -> None: ...
    def read_series(
        self,
        station_id: int,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame: ...
    def latest(self, station_id: int) -> Optional[dict]: ...
    def station_ids(self) -> list: ...


@runtime_checkable
class AnalyticsRepository(Protocol):
    """分析查询（DuckDB 直接读 Parquet，零服务）。"""

    def query(self, sql: str) -> pd.DataFrame: ...
    def hourly_summary(self, station_id: int, hours: int) -> pd.DataFrame: ...
