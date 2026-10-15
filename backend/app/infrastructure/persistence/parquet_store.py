"""Parquet 时序仓储：原始水位/降雨序列（按监测点一文件）。

业务写 SQLite，原始序列写 Parquet，分析查询走 DuckDB（V1.2 §3.2 约定）。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from app.core.logging import get_logger

logger = get_logger("persistence.parquet")

SERIES_COLUMNS = ["ts", "level", "rain_observed"]


class ParquetTimeSeriesRepository:
    def __init__(self, parquet_dir: Path):
        self.dir = Path(parquet_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, station_id: int) -> Path:
        return self.dir / f"station_{station_id}.parquet"

    def write_series(self, station_id: int, df: pd.DataFrame) -> None:
        df = df[SERIES_COLUMNS].copy()
        df["ts"] = pd.to_datetime(df["ts"])
        df = df.sort_values("ts").reset_index(drop=True)
        df.to_parquet(self._path(station_id), index=False)

    def read_series(
        self,
        station_id: int,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        path = self._path(station_id)
        if not path.exists():
            return pd.DataFrame(columns=SERIES_COLUMNS)
        df = pd.read_parquet(path)
        df["ts"] = pd.to_datetime(df["ts"])
        if start is not None:
            df = df[df["ts"] >= pd.Timestamp(start)]
        if end is not None:
            df = df[df["ts"] <= pd.Timestamp(end)]
        return df.sort_values("ts").reset_index(drop=True)

    def latest(self, station_id: int) -> Optional[dict]:
        df = self.read_series(station_id)
        df = df[df["level"].notna()]
        if df.empty:
            return None
        row = df.iloc[-1]
        return {
            "ts": row["ts"].to_pydatetime(),
            "level": float(row["level"]),
            "rain_observed": float(row["rain_observed"]),
        }

    def station_ids(self) -> list:
        ids = []
        for p in self.dir.glob("station_*.parquet"):
            try:
                ids.append(int(p.stem.split("_")[1]))
            except (IndexError, ValueError):
                continue
        return sorted(ids)

    def append_row(self, station_id: int, ts: datetime, level: float, rain: float) -> None:
        """追加一行（模拟源持续采集时的写入路径）。"""
        df = self.read_series(station_id)
        new = pd.DataFrame([{"ts": pd.Timestamp(ts), "level": level, "rain_observed": rain}])
        df = pd.concat([df, new], ignore_index=True)
        self.write_series(station_id, df)
