"""实验 API 的限时故障状态与受控 CPU 负载。

输入：已通过控制令牌认证的场景名称和持续时间。
处理：在线程锁内记录单调时钟截止点；CPU 场景启动单个低占空比后台线程。
输出：业务请求可查询场景是否仍有效。
副作用：CPU 场景最多使用单核约 25% 的时间片，截止后线程自动退出。
并发：所有截止时间读写都受锁保护，同一 CPU 场景不会启动多个压力线程。
"""

from collections.abc import Callable
from threading import Lock, Thread
from time import monotonic, sleep

SUPPORTED_APPLICATION_FAULTS = frozenset(
    {"container_cpu_spike", "request_latency", "http_5xx"}
)


class FaultState:
    """保存进程内故障截止时间，并保证故障一定自动过期。"""

    def __init__(self, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._deadlines: dict[str, float] = {}
        self._cpu_worker_running = False
        self._lock = Lock()

    def activate(self, scenario: str, duration_seconds: int) -> float:
        """启用注册场景并返回单调时钟截止点。"""

        if scenario not in SUPPORTED_APPLICATION_FAULTS:
            raise ValueError("应用故障场景未注册")
        if duration_seconds < 1 or duration_seconds > 120:
            raise ValueError("故障持续时间必须在 1 到 120 秒之间")

        with self._lock:
            deadline = self._clock() + duration_seconds
            self._deadlines[scenario] = deadline
            should_start_cpu = (
                scenario == "container_cpu_spike" and not self._cpu_worker_running
            )
            if should_start_cpu:
                self._cpu_worker_running = True
        if should_start_cpu:
            Thread(target=self._run_cpu_load, daemon=True, name="lab-cpu-fault").start()
        return deadline

    def clear(self, scenario: str) -> None:
        """幂等清除一个场景；不存在或已经过期时不报错。"""

        with self._lock:
            self._deadlines.pop(scenario, None)

    def active(self, scenario: str) -> bool:
        """检查场景是否仍有效，并顺手移除已经过期的记录。"""

        with self._lock:
            deadline = self._deadlines.get(scenario)
            if deadline is None:
                return False
            if deadline <= self._clock():
                self._deadlines.pop(scenario, None)
                return False
            return True

    def _run_cpu_load(self) -> None:
        """以 50ms 计算、150ms 休眠产生有界负载，过期后退出。"""

        while self.active("container_cpu_spike"):
            busy_until = monotonic() + 0.05
            value = 1
            # 简单整数运算避免分配大对象，故障只影响 CPU 而不制造内存压力。
            while monotonic() < busy_until:
                value = (value * 1_103_515_245 + 12_345) & 0x7FFFFFFF
            # 显式休眠形成约 25% 占空比，避免 4GB 演示机被单场景占满一核。
            sleep(0.15)
        with self._lock:
            self._cpu_worker_running = False
