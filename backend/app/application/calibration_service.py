"""模型校准服务（V1.3 校准三项）：
- 参数校准 ✅ 做实：网格搜索标定 LinearResponseModel 的 gain / response_k；
- 重训 🔶 占位：/calibrations 返回 pending（EXT-POINT(MODEL)）；
- 在线学习：模型级明确不做；预测级由 ForecastRevisionService 承担。
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from app.core.errors import BizError
from app.core.logging import get_logger
from app.infrastructure.forecast.params import build_kernel
from app.infrastructure.persistence.sqlite_repo import ModelRepository, TaskRepository

logger = get_logger("application.calibration")


class CalibrationService:
    def __init__(self, model_repo: ModelRepository, task_repo: TaskRepository, ts_repo, cfg):
        self._models = model_repo
        self._tasks = task_repo
        self._ts_repo = ts_repo
        self._cfg = cfg  # ForecastConfig

    # ------------------------------------------------------------------
    # 参数校准（做实）：网格搜索最小化「模拟递推 vs 实况」RMSE
    # ------------------------------------------------------------------
    def calibrate_params(self, model_id: int, station_id: int, hours: int = 24) -> dict:
        row = self._models.get(model_id)
        if row is None:
            raise BizError(1201, f"模型 {model_id} 不存在（MODEL_NOT_READY）")
        if row.model_type != "linear_response":
            raise BizError(
                1202, f"参数校准仅支持 linear_response 模型，当前 {row.model_type}"
                "（MODEL_INPUT_MISMATCH）"
            )

        hist = self._ts_repo.read_series(
            station_id, start=datetime.now() - timedelta(hours=hours)
        )
        if len(hist) < 36:
            raise BizError(1301, "历史数据不足 3 小时，无法参数校准（DATA_NOT_ENOUGH）")

        from app.infrastructure.forecast.registry import build_params

        params0 = build_params(self._cfg, None, row.algorithm_config, station_id)
        # 缺失值处理：按有效水位对齐（FR-2.3），避免 NaN 污染 RMSE
        valid = hist[hist["level"].notna()]
        level = valid["level"].to_numpy(dtype=float)
        rain = valid["rain_observed"].fillna(0.0).to_numpy(dtype=float)
        base = float(level[0])
        kernel = build_kernel(params0.kernel_len, params0.kernel_tau)

        def simulate(gain: float, k_rec: float) -> np.ndarray:
            sim = np.zeros_like(level)
            lvl = base
            kernel_len = len(kernel)
            for i in range(len(level)):
                lo = max(0, i - kernel_len + 1)
                seg = rain[lo:i + 1]
                if len(seg) < kernel_len:
                    seg = np.pad(seg, (kernel_len - len(seg), 0))
                inflow = gain * float(np.dot(kernel, seg))
                lvl = lvl + inflow - k_rec * (lvl - base)
                sim[i] = lvl
            return sim

        def rmse_of(gain: float, k_rec: float) -> float:
            sim = simulate(gain, k_rec)
            return float(math.sqrt(np.mean((sim - level) ** 2)))

        rmse_before = rmse_of(params0.gain, params0.response_k)
        mae_before = float(np.mean(np.abs(simulate(params0.gain, params0.response_k) - level)))

        best = (params0.gain, params0.response_k, rmse_before)
        for gain in np.arange(0.001, 0.0101, 0.001):
            for k_rec in np.arange(0.004, 0.0201, 0.002):
                r = rmse_of(float(gain), float(k_rec))
                if r < best[2]:
                    best = (round(float(gain), 4), round(float(k_rec), 4), r)
        gain_best, k_best, rmse_after = best
        mae_after = float(np.mean(np.abs(simulate(gain_best, k_best) - level)))

        self._models.save_calibration(
            model_id, station_id,
            params={"gain": gain_best, "response_k": k_best,
                    "kernel_len": params0.kernel_len, "kernel_tau": params0.kernel_tau},
            rmse_before=round(rmse_before, 4), rmse_after=round(rmse_after, 4),
            mae_before=round(mae_before, 4), mae_after=round(mae_after, 4),
        )
        logger.info("params calibrated",
                    extra={"station_id": station_id, "event": "calibrate"})
        return {
            "model_id": model_id,
            "station_id": station_id,
            "method": "grid_search(gain × response_k)",
            "params_before": {"gain": params0.gain, "response_k": params0.response_k},
            "params_after": {"gain": gain_best, "response_k": k_best},
            "rmse_before": round(rmse_before, 4),
            "rmse_after": round(rmse_after, 4),
            "mae_before": round(mae_before, 4),
            "mae_after": round(mae_after, 4),
            "improved_pct": round((1 - rmse_after / rmse_before) * 100, 2) if rmse_before else 0.0,
        }

    # ------------------------------------------------------------------
    # 重训占位（🔶）：返回受理回执，不执行训练
    # ------------------------------------------------------------------
    def create_retrain_task(self, station_id: Optional[int], base_model_id: Optional[int]) -> dict:
        # EXT-POINT(MODEL): 模型重训流水线——特征窗口构建 → lgb/prophet 训练 →
        # 新版本写 model 表（active=false）→ 人工确认激活（FR-6.3）→ 支持回滚（FR-6.4）。
        task = self._tasks.create(
            task_type="model_retrain",
            request={"station_id": station_id, "base_model_id": base_model_id},
            status="pending",
        )
        return {
            "calibration_id": task.task_id,
            "task_type": task.task_type,
            "status": task.status,
            "station_id": station_id,
            "base_model_id": base_model_id,
            "created_at": task.create_time,
            "note": "模型重训为占位功能：已受理并记录任务，训练执行位待填充（EXT-POINT(MODEL)）",
        }

    def get_task(self, calibration_id: int) -> dict:
        task = self._tasks.get(calibration_id)
        if task is None:
            raise BizError(1404, f"校准任务 {calibration_id} 不存在（RESOURCE_NOT_FOUND）")
        return {
            "calibration_id": task.task_id,
            "task_type": task.task_type,
            "status": task.status,
            "created_at": task.create_time,
            "finish_time": task.finish_time,
            "error_message": task.error_message,
            "note": "重训占位：任务状态持久为 pending（EXT-POINT(MODEL)）",
        }
