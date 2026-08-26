"""公网访客滑动窗口限流测试。"""

from aiops_control.application.rate_limit_service import SlidingWindowRateLimiter


def test_sliding_window_releases_expired_requests() -> None:
    """窗口内超额应拒绝，时间推进后应重新允许。"""

    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=10)
    assert limiter.allow("visitor", now=0) is True
    assert limiter.allow("visitor", now=1) is True
    assert limiter.allow("visitor", now=2) is False
    assert limiter.allow("visitor", now=11) is True
