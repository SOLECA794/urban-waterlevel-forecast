"""真实数据源 Adapter（🔶 占位留白）。

占位 ≠ 缺失：完整接口签名 + 合规返回 + EXT-POINT 标注。
将来填充：实现本类并通过配置 datasource.type: real 切换，业务层零改动。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from app.domain.ports.data_source import DataBlock, SourceInfo, SourceStatus


class RealSourceAdapter:
    """真实气象/水位数据源适配器（本期占位）。

    # EXT-POINT(DATASOURCE): 接入真实遥测水位计 / 气象局降雨实况与 NWP 预报。
    # 预期对接方式：
    #   1. 实现 connect() —— 建立与遥测平台（如水文遥测平台/气象数据接口）的会话；
    #   2. 实现 start_stream() —— 按采样间隔拉取或接收推送，写入 DataBlock；
    #   3. 实现 get_rain_forecast() —— 对接数值天气预报（NWP）接口，替换模拟预报；
    #   4. 异常与断流遵循 DataSource 状态机（连续 3 周期无数据 → ERROR）。
    # 实现后仅需将 config/default.yaml 的 datasource.type 改为 real。
    """

    name = "real"

    def __init__(self, config: Optional[dict] = None):
        self._config = config or {}
        self._status = SourceStatus.DISCONNECTED
        self._last_error = "RealSourceAdapter 为占位实现，尚未接入真实数据源"

    async def connect(self, config: dict) -> SourceInfo:
        # EXT-POINT(DATASOURCE): 建立真实数据源连接，返回站点清单
        self._status = SourceStatus.ERROR
        raise NotImplementedError(
            "RealSourceAdapter 为占位实现：请按 EXT-POINT(DATASOURCE) 说明接入真实数据源"
        )

    async def disconnect(self) -> bool:
        self._status = SourceStatus.DISCONNECTED
        return True

    async def start_stream(self, sink) -> bool:
        # EXT-POINT(DATASOURCE): 启动持续采集（推模式或拉模式）
        return False

    async def stop_stream(self) -> bool:
        return True

    async def get_status(self) -> SourceStatus:
        return self._status

    async def get_series(self, station_id: int, hours: int) -> pd.DataFrame:
        # EXT-POINT(DATASOURCE): 读取真实水位/降雨序列
        return pd.DataFrame(columns=["ts", "level", "rain_observed"])

    def get_rain_forecast(
        self, station_id: int, t_issue: datetime, hours: int, step_minutes: int = 5
    ) -> pd.DataFrame:
        # EXT-POINT(DATASOURCE): 对接 NWP 降雨预报（替换模拟预报的取数实现）
        return pd.DataFrame(columns=["ts", "rain_forecast"])

    def source_status_payload(self) -> dict:
        return {
            "type": "real",
            "status": self._status.value,
            "detail": self._last_error,
        }
