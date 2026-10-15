"""pytest 全局夹具：测试数据目录隔离 + 演示数据生成。

环境变量必须在 app.core.config.get_settings() 首次调用前设置
（避免污染开发数据目录 data/）。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(BACKEND_ROOT / "scripts"))

_TMP = tempfile.mkdtemp(prefix="wl_test_")
os.environ.setdefault("WL_SQLITE_PATH", os.path.join(_TMP, "test.db"))
os.environ.setdefault("WL_PARQUET_DIR", os.path.join(_TMP, "parquet"))
os.environ.setdefault("WL_AUTO_FORECAST", "0")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def demo_data():
    """生成小体量模拟数据（12h 历史 + 未来真值）。"""
    from app.core.config import get_settings
    from app.infrastructure.persistence.database import (
        create_engine_for, init_db, make_session_factory,
    )
    from app.infrastructure.persistence.parquet_store import ParquetTimeSeriesRepository
    from app.infrastructure.persistence.sqlite_repo import StationRepository
    from scripts.generate_demo_data import gen_station_series

    settings = get_settings()
    settings.datasource.history_hours = 12
    engine = create_engine_for(settings)
    init_db(engine, settings, seed=True)
    ts_repo = ParquetTimeSeriesRepository(settings.parquet_dir)
    stations = StationRepository(make_session_factory(engine))
    cfg = {"S001": ("heavy", 1.2, 0.008), "S002": ("heavy", 1.0, 0.008),
           "S003": ("moderate", 1.6, 0.012), "S004": ("light", 1.3, 0.010),
           "S005": ("light", 1.4, 0.014), "S006": ("moderate", 1.5, 0.012)}
    for idx, st in enumerate(stations.list()):
        kind, base, k = cfg.get(st.station_code, ("light", 1.0, 0.01))
        obs, fut = gen_station_series(
            kind=kind, base_level=base, response_k=k,
            cfg_params=settings.forecast.linear_response,
            hist_steps=12 * 12, future_steps=12 * 12, seed=100 + idx,
        )
        ts_repo.write_series(st.station_id, obs)
        fut.to_parquet(settings.parquet_dir / f"station_{st.station_id}_future.parquet",
                       index=False)
    yield


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c
