"""DataPreprocessor —— 多源数据预处理与特征工程统一模块。

对应需求书【模型软件】一.2：数据清洗、时序对齐、缺失值填补与特征提取。
以及【分析模式】1：为模型训练和在线预测提供统一数据集，构建统一特征工程体系。

处理流程（对每个站点的原始时序）：
  1. 时序对齐：重采样到固定 step_min 网格（5min）
  2. 数据清洗：异常值裁剪（水位物理范围、负值剔除）
  3. 缺失值填补：level/rain 前向填充 ≤3 步，再线性插值
  4. 特征提取：多窗口累计降雨、雨强峰值、水位差分、变化率
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class PreprocessReport:
    raw_rows: int = 0
    cleaned_rows: int = 0
    filled_points: int = 0
    clipped_outliers: int = 0
    windows: tuple = (1, 3, 6)  # 小时

    def as_dict(self) -> dict:
        return {
            "raw_rows": self.raw_rows,
            "cleaned_rows": self.cleaned_rows,
            "filled_points": self.filled_points,
            "clipped_outliers": self.clipped_outliers,
            "windows_h": list(self.windows),
        }


class DataPreprocessor:
    """多源数据预处理与特征工程管线。"""

    def __init__(self, step_minutes: int = 5,
                 level_min: float = -0.5, level_max: float = 20.0,
                 max_fill_steps: int = 3,
                 windows_h: tuple = (1, 3, 6)):
        self.step = step_minutes
        self.lo = level_min
        self.hi = level_max
        self.max_fill = max_fill_steps
        self.windows = windows_h

    def process(self, df: pd.DataFrame) -> tuple[pd.DataFrame, PreprocessReport]:
        """输入列：ts, level, rain_observed（rain_forecast 由调用方拼在 future 段）。
        返回：对齐+清洗+填补+特征列后的 DataFrame。
        """
        rep = PreprocessReport()
        if df is None or df.empty:
            return df, rep
        rep.raw_rows = len(df)
        out = df.copy()
        out["ts"] = pd.to_datetime(out["ts"])
        out = out.set_index("ts").sort_index()

        # 1. 时序对齐：重采样到固定网格
        out = out.resample(f"{self.step}min").mean(numeric_only=True)

        # 2. 数据清洗：物理范围裁剪
        if "level" in out.columns:
            before = out["level"]
            out["level"] = out["level"].where(
                (out["level"] >= self.lo) & (out["level"] <= self.hi), np.nan
            )
            rep.clipped_outliers += int(before.notna().sum() - out["level"].notna().sum())

        # 3. 缺失值填补：前向填充 ≤max_fill 步，再对短缺口线性插值
        for col in ("level", "rain_observed"):
            if col in out.columns:
                n_missing = int(out[col].isna().sum())
                out[col] = out[col].ffill(limit=self.max_fill)
                out[col] = out[col].interpolate(method="linear", limit=self.max_fill)
                rep.filled_points += n_missing - int(out[col].isna().sum())

        # 4. 特征工程：多窗口累计降雨 + 雨强峰值 + 水位差分
        if "rain_observed" in out.columns:
            rain = out["rain_observed"].fillna(0.0)
            for h in self.windows:
                win_steps = int(h * 60 / self.step)
                out[f"rain_sum_{h}h"] = rain.rolling(win_steps, min_periods=1).sum()
                out[f"rain_max_{h}h"] = rain.rolling(win_steps, min_periods=1).max()
        if "level" in out.columns:
            out["level_diff"] = out["level"].diff()
            out["level_rate"] = out["level"].diff() / self.step * 60.0  # m/h

        out = out.reset_index().rename(columns={"index": "ts"})
        if "ts" not in out.columns:
            out = out.rename(columns={"index": "ts"})
        rep.cleaned_rows = len(out)
        return out, rep
