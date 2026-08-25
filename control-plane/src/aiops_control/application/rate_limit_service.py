"""公网实验入口的进程内滑动窗口限流。

单机项目不引入 Redis；控制面重启会清空窗口，这是可接受的演示降级。
"""

import time
from collections import defaultdict, deque
from threading import RLock


class SlidingWindowRateLimiter:
    """按访客键限制固定时间窗口内的请求数量。"""

    def __init__(self, limit: int, window_seconds: float) -> None:
        if limit < 1 or window_seconds <= 0:
            raise ValueError("限流数量和窗口必须为正")
        self._limit = limit
        self._window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = RLock()

    def allow(self, key: str, now: float | None = None) -> bool:
        """原子清理过期记录并判断当前请求能否进入。"""

        current = time.monotonic() if now is None else now
        boundary = current - self._window_seconds
        with self._lock:
            timestamps = self._requests[key]
            # 左侧永远是最旧请求，逐个弹出可保持每次操作摊销 O(1)。
            while timestamps and timestamps[0] <= boundary:
                timestamps.popleft()
            if len(timestamps) >= self._limit:
                return False
            timestamps.append(current)
            return True
