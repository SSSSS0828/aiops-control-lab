"""真实监测后台调度器。

每个控制面进程都会启动循环，但仓储的非阻塞租约确保同一分钟只有一个实例执行规则。
异常会记录后继续下一周期，不使用无边界即时重试，避免数据库故障时放大压力。
"""

import asyncio
import logging

from aiops_control.application.monitoring_service import MonitoringService
from aiops_control.ports.monitoring_repository import MonitoringRepository

logger = logging.getLogger(__name__)


class MonitoringScheduler:
    """按固定秒数驱动真实规则评估。"""

    def __init__(
        self,
        repository: MonitoringRepository,
        service: MonitoringService,
        interval_seconds: int = 60,
    ) -> None:
        self._repository = repository
        self._service = service
        self._interval_seconds = max(interval_seconds, 10)

    async def run(self) -> None:
        """先建立默认规则，再循环执行带数据库锁的评估。"""

        await asyncio.to_thread(self._service.ensure_default_rules)
        while True:
            try:
                await asyncio.to_thread(
                    self._repository.run_monitoring_cycle_once,
                    self._evaluate_cycle,
                )
            except Exception:
                logger.exception("真实监测评估周期失败")
            await asyncio.sleep(self._interval_seconds)

    def _evaluate_cycle(self) -> None:
        """丢弃返回列表，调度器只关心本轮是否完整执行。"""

        self._service.evaluate_all()
