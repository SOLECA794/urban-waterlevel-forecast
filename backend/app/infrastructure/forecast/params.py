"""占位模型共享参数。

与模拟数据生成器共用同一套响应参数（ADR-3），保证预测曲线形态可信。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


def build_kernel(kernel_len: int, tau: float) -> np.ndarray:
    """汇流滞后核：Gamma 形响应，ΣW=1。i=1..kernel_len。"""
    i = np.arange(1, kernel_len + 1, dtype=float)
    w = i * np.exp(-i / tau)
    return w / w.sum()


@dataclass
class ModelParams:
    """模型运行参数（站点可覆盖 response_k / base_level；标定可覆盖全部）。"""

    base_level: float = 1.0
    response_k: float = 0.010          # 每步退水系数
    gain: float = 0.004                # 有效降雨(mm)→水位(m) 增益
    kernel_len: int = 12
    kernel_tau: float = 5.0
    decay: float = 0.08                # NaiveModel 回落速率（/h）
    ci_base: float = 0.02              # 置信区间基础半宽（m）
    ci_sqrt_factor: float = 0.06       # 区间宽度 ∝ 近期RMSE × √h 的比例因子
    station_overrides: dict = field(default_factory=dict)

    def kernel(self) -> np.ndarray:
        return build_kernel(self.kernel_len, self.kernel_tau)


def effective_ci(half_width_base: float, rmse: Optional[float], h_hours: float,
                 ci_sqrt_factor: float) -> float:
    """D4 置信区间自适应：宽度 ∝ 近期RMSE × √h（无误差记录时用基础宽度）。"""
    if rmse and rmse > 0:
        return max(0.01, rmse * np.sqrt(max(h_hours, 0.25)) * ci_sqrt_factor * 6.0)
    return half_width_base * (1.0 + 0.9 * np.sqrt(max(h_hours, 0.25)))
