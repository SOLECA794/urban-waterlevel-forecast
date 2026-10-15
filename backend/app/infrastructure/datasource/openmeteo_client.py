"""Open-Meteo 真实气象预报客户端（去 mock）。

免费、无需 API key。拉杭州未来 48h 逐小时降水预报（mm/h），
按站点经纬度（缺省用杭州市中心 30.25N, 120.17E）。
失败时由调用方 fallback 到模拟序列——保证系统不挂。
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from app.core.logging import get_logger

logger = get_logger("datasource.openmeteo")

# 杭州市中心默认坐标（站点无独立经纬度时使用）
DEFAULT_LAT = 30.25
DEFAULT_LON = 120.17

# 缓存：同一时刻的预报只拉一次，30 分钟内复用
_CACHE: dict = {"key": None, "df": None, "ts": 0.0}
_CACHE_TTL = 1800.0  # 30min


def _fetch_hourly(lat: float, lon: float) -> pd.DataFrame:
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        + urllib.parse.urlencode({
            "latitude": lat,
            "longitude": lon,
            "hourly": "precipitation",
            "forecast_days": 2,
            "timezone": "Asia/Shanghai",
        })
    )
    req = urllib.request.Request(url, headers={"User-Agent": "waterlevel-forecast/1.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    times = pd.to_datetime(data["hourly"]["time"])
    precip = [float(x) if x is not None else 0.0 for x in data["hourly"]["precipitation"]]
    return pd.DataFrame({"ts": times, "rain_mm_h": precip})


def get_real_rain_forecast(
    station_id: int,
    t_issue: datetime,
    hours: int,
    step_minutes: int = 5,
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
) -> Optional[pd.DataFrame]:
    """返回 [t_issue, t_issue+hours] 的 5min 降雨预报（mm/step）。

    真数据失败返回 None（调用方 fallback 到模拟）。
    """
    now_key = int(time.time() // 1800)  # 每 30 分钟一个缓存 key
    if _CACHE["key"] == now_key and _CACHE["df"] is not None:
        hourly = _CACHE["df"]
    else:
        try:
            hourly = _fetch_hourly(lat, lon)
            _CACHE["key"] = now_key
            _CACHE["df"] = hourly
            _CACHE["ts"] = time.time()
            logger.info("open-meteo forecast fetched", extra={"event": "nwp_real",
                         "points": len(hourly), "rain_sum_24h": round(float(hourly["rain_mm_h"].sum()), 1)})
        except Exception as exc:
            logger.warning("open-meteo fetch failed, fallback to sim", extra={"err": str(exc)})
            return None

    future_ts = pd.date_range(t_issue, periods=int(hours * 60 / step_minutes),
                              freq=f"{step_minutes}min")
    # 逐小时 mm/h → 5min mm/step（均匀分配）
    out = []
    for ts in future_ts:
        floor_h = ts.floor("h")
        row = hourly[hourly["ts"] == floor_h]
        mm_h = float(row["rain_mm_h"].iloc[0]) if len(row) else 0.0
        out.append(round(mm_h * step_minutes / 60.0, 3))
    return pd.DataFrame({"ts": future_ts, "rain_forecast": out})
