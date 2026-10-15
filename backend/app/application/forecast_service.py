"""预测用例编排（应用层）：数据治理 → Agent-A 决策 → 模型推理 → 协同修正 → 落库 → 研判。

只依赖 Port 与仓储实现，不 import 具体 Adapter（模块化单体铁律）。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

import numpy as np
import pandas as pd

from app.core.config import Settings
from app.core.errors import BizError
from app.core.logging import get_logger, new_trace_id
from app.domain.models import Forecast, Model, Station
from app.domain.ports.orchestrator import ForecastContext, ForecastDecision, SourceQuality
from app.infrastructure.forecast.registry import ModelRegistry
from app.infrastructure.persistence.sqlite_repo import (
    AlertRepository,
    ForecastRepository,
    ModelRepository,
    StationRepository,
)
from .alert_service import AlertService
from .orchestrator import RuleBasedOrchestrator
from .revision_service import ForecastRevisionService

logger = get_logger("application.forecast")


class ForecastService:
    def __init__(
        self,
        settings: Settings,
        station_repo: StationRepository,
        model_repo: ModelRepository,
        forecast_repo: ForecastRepository,
        alert_repo: AlertRepository,
        alert_service: AlertService,
        orchestrator: RuleBasedOrchestrator,
        revision_service: ForecastRevisionService,
        registry: ModelRegistry,
        datasource,  # DataSource Port 实现（容器注入，不 import 具体类）
        ts_repo,
    ):
        self._settings = settings
        self._stations = station_repo
        self._models = model_repo
        self._forecasts = forecast_repo
        self._alerts = alert_repo
        self._alert_service = alert_service
        self._orchestrator = orchestrator
        self._revision = revision_service
        self._registry = registry
        self._datasource = datasource
        self._ts_repo = ts_repo
        from app.infrastructure.forecast.preprocessor import DataPreprocessor
        self._pre = DataPreprocessor(step_minutes=settings.forecast.step_minutes)
        self._last_prep_report: dict = {}
        # 上一版预报总量缓存（e_fcst 新息的近似来源）
        self._last_rain_total: dict = {}

    # ------------------------------------------------------------------
    def _step_minutes(self) -> int:
        return self._settings.forecast.step_minutes

    def _history_window(self, station_id: int, need_rows: int) -> pd.DataFrame:
        hours = max(
            self._settings.forecast.min_history_hours * 2,
            int(need_rows * self._step_minutes() / 60) + 2,
        )
        df = self._ts_repo.read_series(station_id, start=datetime.now() - timedelta(hours=hours))
        return df

    def _quality(self, hist: pd.DataFrame, recent_rmse: Optional[float]) -> SourceQuality:
        status = getattr(self._datasource, "status_value", "STREAMING")
        step = self._step_minutes()
        if hist.empty:
            return SourceQuality(status=status, missing_rate=1.0,
                                 last_sample_age_min=9999, recent_rmse=recent_rmse)
        last_ts = pd.Timestamp(hist.iloc[-1]["ts"]).to_pydatetime()
        age = max(0.0, (datetime.now() - last_ts).total_seconds() / 60.0)
        window = hist[hist["ts"] >= pd.Timestamp(datetime.now() - timedelta(hours=3))]
        expected = int(3 * 60 / step) + 1
        missing = max(0, expected - len(window)) / expected
        return SourceQuality(
            status=status,
            missing_rate=round(min(1.0, missing), 3),
            last_sample_age_min=round(age, 2),
            recent_rmse=recent_rmse,
        )

    def _innovation(self, station_id: int) -> float:
        """近 90 分钟已落地时段的新息：actual − predicted 的均值（m）。

        评审 P1-6 口径修正：新息必须反映「预报偏差随预见期的累积」。
        若锚定最新一版预测自己的已过点，那些点全部位于近端（预报≈真值），
        新息恒为 0、协同修正永不生效（α>0 但 e≈0，双曲线重合）。
        故改为取约 90 分钟前签发的一版预测，用它在 [now−90min, now] 内
        已落地的目标点做均值差——暴雨期预报误差（峰值低估/雨强偏差）
        在该窗口内已实际兑现，修正因此能把预测拉向实测。
        """
        now = datetime.now()
        window_min = 90
        rows, _ = self._forecasts.list_for_station(station_id, page=1, page_size=40)
        anchor = None
        for f in rows:  # rows 按 forecast_id 倒序（最新在前）
            if f.predict_time <= now - timedelta(minutes=window_min - 15):
                anchor = f
                break
        if anchor is None:
            anchor = rows[-1] if rows else None
        if anchor is None:
            return 0.0
        past = [
            p for p in self._forecasts.get_points(anchor.forecast_id)
            if now - timedelta(minutes=window_min) <= p.target_time <= now
        ]
        if not past:
            return 0.0
        actual_df = self._ts_repo.read_series(
            station_id,
            start=past[0].target_time - timedelta(minutes=self._step_minutes()),
            end=now,
        )
        if actual_df.empty:
            return 0.0
        obs = [
            (pd.Timestamp(r["ts"]).to_pydatetime(), float(r["level"]))
            for _, r in actual_df.iterrows()
            if r["level"] is not None and r["level"] == r["level"]
        ]
        if not obs:
            return 0.0
        tol_sec = self._step_minutes() * 60
        gaps = []
        for p in past:
            cand = min(obs, key=lambda x: abs((x[0] - p.target_time).total_seconds()))
            if abs((cand[0] - p.target_time).total_seconds()) <= tol_sec:
                gaps.append(cand[1] - float(p.pred_level))
        if not gaps:
            return 0.0
        return round(sum(gaps) / len(gaps), 4)

    def _build_window(
        self, hist: pd.DataFrame, station: Station, lead_hours: int, need_rows: int
    ) -> pd.DataFrame:
        """构造模型输入窗口：历史行（level 有值）+ 未来行（rain_forecast 有值）。"""
        step = self._step_minutes()
        win = hist.tail(max(need_rows, 24)).copy()
        win["rain_forecast"] = np.nan

        now_floor = pd.Timestamp(hist.iloc[-1]["ts"]).to_pydatetime()
        fc = self._datasource.get_rain_forecast(
            station.station_id, now_floor, lead_hours + 1, step
        )
        fc = fc[fc["ts"] > pd.Timestamp(now_floor)]
        fc = fc[fc["ts"] <= pd.Timestamp(now_floor + timedelta(minutes=lead_hours * 60))]

        future = pd.DataFrame({
            "ts": fc["ts"].values,
            "level": np.nan,
            "rain_observed": np.nan,
            "rain_forecast": fc["rain_forecast"].values,
        })
        window = pd.concat([win, future], ignore_index=True)
        window["ts"] = pd.to_datetime(window["ts"])
        return window.sort_values("ts").reset_index(drop=True)

    # ------------------------------------------------------------------
    def run_prediction(
        self,
        station_id: int,
        lead_hours: int,
        model_id: Optional[int] = None,
    ) -> dict:
        trace = new_trace_id()
        station = self._stations.get(station_id)
        if station is None:
            raise BizError(1102, f"监测点 {station_id} 不存在（STATION_NOT_FOUND）")
        if not station.enabled:
            raise BizError(1101, f"监测点 {station.station_code} 已停用（STATION_STATE_INVALID）")
        if lead_hours not in self._settings.forecast.lead_hours:
            raise BizError(
                400,
                f"不支持的预见期 {lead_hours}h，可选 {self._settings.forecast.lead_hours}（PARAM_INVALID）",
            )

        step = self._step_minutes()
        min_rows = int(self._settings.forecast.min_history_hours * 60 / step)
        hist = self._history_window(station_id, need_rows=min_rows + 48)
        # FR一.2/分析模式1：显式数据预处理（对齐+清洗+填补+特征工程）
        try:
            hist, prep_rep = self._pre.process(hist)
            self._last_prep_report[station_id] = prep_rep.as_dict()
        except Exception:
            self._last_prep_report[station_id] = {"note": "preprocess_failed_fallback_raw"}
        hist = hist[hist["level"].notna()]  # 预处理后仍缺的点剔除
        if hist.empty:
            raise BizError(1301, f"监测点 {station.station_code} 无有效历史数据，拒绝预测（DATA_NOT_ENOUGH）")
        recent_rmse = self._forecasts.recent_rmse_for_station(station_id)
        quality = self._quality(hist, recent_rmse)

        # ---- Agent-A 决策（D1–D5） ----
        model_row: Optional[Model] = None
        if model_id is not None:
            model_row = self._models.get(model_id)
            if model_row is None:
                raise BizError(1201, f"模型 {model_id} 不存在（MODEL_NOT_READY）")
            if not model_row.model_file:
                raise BizError(1201, f"模型 {model_row.model_name} 为占位版本（MODEL_NOT_READY）")
            active_type = model_row.model_type
        else:
            active = self._models.get_active()
            active_type = active.model_type if active else self._settings.forecast.model_type

        ctx = ForecastContext(
            station_id=station_id,
            station_code=station.station_code,
            lead_hours=lead_hours,
            history_rows=len(hist),
            min_rows=min_rows,
            innovation=self._innovation(station_id),
            quality=quality,
            active_model_type=active_type,
        )
        decision: ForecastDecision = self._orchestrator.decide(ctx)
        if model_row is not None:
            if decision.degraded:
                # P1-5（评审）：降级态下追溯面板不能自相矛盾——忽略人工指定模型，
                # D1 必须显示实际执行模型（naive），人工覆盖理由保留在决策理由中
                decision.reason += "；降级态下忽略人工指定模型，按 D5 实际执行 naive（D1 未被覆盖）"
                model_row = None
            else:
                decision.selected_model = model_row.model_type
                decision.reason += "（应请求指定模型，D1 被人工覆盖）"

        # ---- 模型推理 ----
        chosen_row = model_row
        builtin_types = ("naive", "linear_response", "nonlinear")
        if chosen_row is None:
            chosen_row = next(
                (m for m in self._models.list()
                 if m.model_type == decision.selected_model and m.model_file),
                None,
            )
        if chosen_row is not None:
            model = self._registry.create_from_row(chosen_row, station)
        elif decision.selected_model in builtin_types:
            # 内置模型（nonlinear/linear_response/naive）无需 DB row，直接构造
            from app.infrastructure.forecast.params import ModelParams
            from app.infrastructure.forecast.registry import build_params
            params = build_params(self._settings.forecast, station)
            model = self._registry.create(decision.selected_model, params)
            # pseudo row 供落库 model_id/model_type
            class _PseudoRow:
                model_id = 1  # FK 占位：引用已存在的 model 行，model_type 真实值为 selected_model
                model_type = decision.selected_model
            chosen_row = _PseudoRow()
        else:
            raise BizError(1201, "没有可用的模型版本（MODEL_NOT_READY）")
        model.set_recent_rmse(recent_rmse)
        window = self._build_window(hist, station, lead_hours, need_rows=min_rows + 48)
        # 参数自学习：用历史窗口拟合非线性模型参数（FR 模型校准优化）
        if hasattr(model, "fit"):
            try:
                model.fit(window[window["level"].notna()])
            except Exception:
                pass  # 拟合失败用默认参数，不阻断预测
        result = model.predict(window, horizon_min=lead_hours * 60)

        # ---- 协同修正（V1.3 多源加权新息 + 时间衰减 + 已发生事件） ----
        rain_innov_mm = self._rain_innovation(station_id, window)
        # FR二.3：近24h有生效预警 → 该站已证模型易低估，叠加事件修正
        event_bonus = 0.0
        try:
            recent_alerts = self._alerts.active_for_station(station_id)
            cutoff = datetime.now() - timedelta(hours=24)
            if any(a.alert_time >= cutoff for a in recent_alerts):
                event_bonus = 0.05
        except Exception:
            pass
        revisions = self._revision.apply(
            result.points, decision,
            innovation=ctx.innovation,
            rain_innovation_mm=rain_innov_mm,
            event_bonus=event_bonus,
            step_minutes=step,
        )

        # ---- 落库：forecast 主记录 + 逐点明细 + 决策 ----
        predict_time = datetime.now()
        corrected_levels = [c for _, _, c in revisions]
        peak_idx = int(np.argmax(corrected_levels))
        forecast = self._forecasts.create(
            station_id=station_id,
            model_id=chosen_row.model_id,
            model_type=chosen_row.model_type,
            lead_hours=lead_hours,
            predict_time=predict_time,
            horizon_end_time=predict_time + timedelta(hours=lead_hours),
            peak_level=float(corrected_levels[peak_idx]),
            peak_time=result.points[peak_idx].t,
            degraded=decision.degraded,
            remark="；".join(result.notes) if result.notes else None,
        )
        points_payload = []
        db_points = []
        t_now = predict_time
        for raw_p, (t, revision, corrected) in zip(result.points, revisions):
            half_raw = (raw_p.upper - raw_p.lower) / 2.0
            half = self._revision.widen_ci(half_raw, t, t_now)
            points_payload.append({
                "t": t,
                "level_raw": raw_p.level_raw,
                "level": corrected,
                "revision": revision,
                "lower": round(corrected - half, 4),
                "upper": round(corrected + half, 4),
            })
            db_points.append({
                "lead_minutes": int((t - t_now).total_seconds() // 60),
                "target_time": t,
                "pred_level_raw": raw_p.level_raw,
                "revision": revision,
                "pred_level": corrected,
                "lower_bound": round(corrected - half, 4),
                "upper_bound": round(corrected + half, 4),
            })
        self._forecasts.add_points(forecast.forecast_id, db_points)
        import json as _json

        self._forecasts.add_decision(
            forecast_id=forecast.forecast_id,
            selected_model=decision.selected_model,
            fusion_weights=_json.dumps(decision.fusion_weights, ensure_ascii=False),
            revision_alpha=decision.revision_alpha,
            ci_scale=decision.ci_scale,
            degraded=decision.degraded,
            reason=decision.reason,
        )
        logger.info(
            "forecast done",
            extra={"station_id": station_id, "forecast_id": forecast.forecast_id,
                   "lead_hours": lead_hours, "model": decision.selected_model},
        )

        # ---- 研判预警（基于修正后曲线） ----
        class _P:  # noqa: N801（本地轻量视图，避免额外数据类）
            def __init__(self, t, level):
                self.t = t
                self.level = level
        alert = self._alert_service.evaluate_after_forecast(
            station, self._forecasts.get(forecast.forecast_id) or forecast,
            [_P(p["t"], p["level"]) for p in points_payload], lead_hours,
        )

        return {
            "forecast_id": forecast.forecast_id,
            "station_id": station_id,
            "station_code": station.station_code,
            "model_id": chosen_row.model_id,
            "model_type": chosen_row.model_type,
            "lead_hours": lead_hours,
            "predict_time": predict_time,
            "horizon_end_time": forecast.horizon_end_time,
            "points": points_payload,
            "peak_level": forecast.peak_level,
            "peak_time": forecast.peak_time,
            "confidence_interval": result.confidence_interval,
            "degraded": decision.degraded,
            "decision": {
                "selected_model": decision.selected_model,
                "fusion_weights": decision.fusion_weights,
                "revision_alpha": decision.revision_alpha,
                "ci_scale": decision.ci_scale,
                "degraded": decision.degraded,
                "reason": decision.reason,
            },
            "alert": self._alert_payload(alert) if alert else None,
        }

    def _rain_innovation(self, station_id: int, window: pd.DataFrame) -> float:
        """最新预报量 − 上一版预报量（近 1h 总量，mm）。"""
        fc = window[window["rain_forecast"].notna()]
        if fc.empty:
            return 0.0
        horizon = pd.Timestamp(fc.iloc[0]["ts"]) + pd.Timedelta(hours=1)
        total = float(fc[fc["ts"] <= horizon]["rain_forecast"].sum())
        prev = self._last_rain_total.get(station_id)
        self._last_rain_total[station_id] = total
        if prev is None:
            return 0.0
        return round(total - prev, 3)

    @staticmethod
    def _alert_payload(alert) -> dict:
        return {
            "alert_id": alert.alert_id,
            "level": alert.level,
            "reason": alert.reason,
            "is_reference": bool(alert.is_reference),
            "lead_minutes_advantage": alert.lead_minutes_advantage,
            "status": alert.status,
        }

    # ------------------------------------------------------------------
    def backfill_actuals(self) -> int:
        """回填已到期逐点的实况水位（精度闭环：forecast_point.actual_level）。"""
        pending = self._forecasts.pending_actual_points()
        if not pending:
            return 0
        updates = []
        for p in pending:
            df = self._ts_repo.read_series(
                self._station_of(p.forecast_id),
                start=p.target_time - timedelta(minutes=self._step_minutes()),
                end=p.target_time + timedelta(minutes=self._step_minutes()),
            )
            if not df.empty:
                updates.append((p.forecast_id, p.lead_minutes, float(df.iloc[-1]["level"])))
        return self._forecasts.backfill_actual(updates)

    def _station_of(self, forecast_id: int) -> int:
        f = self._forecasts.get(forecast_id)
        return f.station_id if f else 0

    def rolling_round(self) -> dict:
        """对所有启用监测点执行一轮滚动预测（调度器调用）。"""
        done = []
        try:
            self.backfill_actuals()
        except Exception:
            logger.warning("actual backfill failed", exc_info=True)
        for st in self._stations.list(enabled_only=True):
            for lead in self._settings.forecast.lead_hours:
                try:
                    self.run_prediction(st.station_id, lead)
                    done.append((st.station_code, lead))
                except BizError as exc:
                    logger.warning(
                        "rolling predict skipped: station=%s lead=%s code=%s",
                        st.station_code, lead, exc.code,
                    )
                except Exception:
                    logger.exception("rolling predict failed: %s", st.station_code)
        return {"stations": len(done)}
