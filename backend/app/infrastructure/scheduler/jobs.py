"""APScheduler 进程内调度：滚动预测 + 实况回填（FR-3.2 / FR-2.5 闭环）。

CPU 密集计算投放到线程池执行，避免阻塞 FastAPI 事件循环（04 §3.3）。
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.logging import get_logger

logger = get_logger("scheduler.jobs")


class SchedulerService:
    def __init__(self, container):
        self._container = container
        self._scheduler = BackgroundScheduler(
            executors={"default": {"type": "threadpool", "max_workers": 2}}
        )

    def start(self) -> None:
        cfg = self._container.settings
        minutes = max(1, int(cfg.forecast.schedule_minutes))
        self._scheduler.add_job(
            self._rolling_forecast_job, "interval", minutes=minutes,
            id="rolling_forecast", max_instances=1, coalesce=True,
        )
        self._scheduler.add_job(
            self._backfill_job, "interval", minutes=minutes,
            id="backfill_actuals", max_instances=1, coalesce=True,
        )
        # 评审 R1：滚动观测数据生成器——每分钟检查一次是否到达采样点，
        # 到点即以相对时间追加样本（采样步长 5min，data_age_min 始终 < 10）
        self._scheduler.add_job(
            self._generator_tick_job, "interval", seconds=60,
            id="generator_tick", max_instances=1, coalesce=True,
        )
        self._scheduler.start()
        logger.info("scheduler started", extra={"event": "scheduler_start"})

    def run_startup_round(self) -> None:
        """启动后立即执行一轮滚动预测（演示数据就绪）。"""
        import threading

        threading.Thread(target=self._rolling_forecast_job, daemon=True).start()

    def shutdown(self) -> None:
        try:
            self._scheduler.shutdown(wait=False)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _rolling_forecast_job(self) -> None:
        try:
            out = self._container.forecast_service.rolling_round()
            logger.info("rolling forecast round done: %s stations", out.get("stations", 0))
        except Exception:
            logger.exception("rolling forecast job failed")
        # Agent 主动巡检：每轮预测后自动生成汛情摘要（值班台/态势横幅读）
        try:
            p = self._container.agent_service.patrol()
            if p.get("ok"):
                logger.info("agent patrol done: %s active alerts", p.get("active_alerts", 0))
        except Exception:
            logger.exception("agent patrol job failed")

    def _backfill_job(self) -> None:
        try:
            n = self._container.forecast_service.backfill_actuals()
            if n:
                logger.info("actual backfilled: %s points", n)
        except Exception:
            logger.exception("backfill job failed")

    def _generator_tick_job(self) -> None:
        """滚动观测数据生成器 tick（R1）：样本时间戳以当前时刻为基准。"""
        try:
            n = self._container.generator.tick()
            if n:
                logger.info("rolling generator tick: %s samples", n)
        except Exception:
            logger.exception("generator tick job failed")
