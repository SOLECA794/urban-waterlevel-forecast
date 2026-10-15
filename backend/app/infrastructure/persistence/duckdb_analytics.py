"""DuckDB 分析查询：直接读同一批 Parquet 文件，零服务、零迁移。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import duckdb
import pandas as pd

from app.core.logging import get_logger

logger = get_logger("persistence.duckdb")


class DuckDBAnalytics:
    """分析查询只读 Parquet（唯一分析数据源，SQLite 与之职责分离）。"""

    def __init__(self, parquet_dir: Path):
        self.dir = Path(parquet_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect()  # 内存连接，进程内共享

    def query(self, sql: str, params: Optional[list] = None) -> pd.DataFrame:
        return self._conn.execute(sql, params or []).fetchdf()

    def _file(self, station_id: int) -> str:
        return (self.dir / f"station_{station_id}.parquet").as_posix()

    def hourly_summary(self, station_id: int, hours: int = 24) -> pd.DataFrame:
        """按小时聚合：最高/最低/均值水位与小时雨量（Agent 聚合分析的示例路径）。"""
        f = self._file(station_id)
        sql = f"""
            SELECT date_trunc('hour', ts) AS hour,
                   max(level) AS max_level,
                   min(level) AS min_level,
                   avg(level) AS avg_level,
                   sum(rain_observed) AS rain_mm
            FROM read_parquet('{f}')
            WHERE ts >= now() - INTERVAL {int(hours)} HOUR
            GROUP BY 1 ORDER BY 1
        """
        try:
            return self.query(sql)
        except Exception as exc:  # 分析查询失败不阻断业务（NFR-8）
            logger.warning("duckdb query failed: %s", exc)
            return pd.DataFrame()

    def series_stats(self, station_id: int) -> dict:
        f = self._file(station_id)
        try:
            row = self.query(
                f"SELECT count(*) AS n, min(ts) AS t0, max(ts) AS t1 FROM read_parquet('{f}')"
            ).iloc[0]
            return {"rows": int(row["n"]), "start": str(row["t0"]), "end": str(row["t1"])}
        except Exception:
            return {"rows": 0, "start": None, "end": None}
