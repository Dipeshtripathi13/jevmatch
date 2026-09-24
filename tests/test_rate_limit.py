import pytest

from core.rate_limit import SlidingWindowRateLimiter


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter_returns_retry_and_recovers():
    limiter = SlidingWindowRateLimiter()

    first = await limiter.check("client:match", limit=2, window_seconds=60, now=0)
    second = await limiter.check("client:match", limit=2, window_seconds=60, now=1)
    blocked = await limiter.check("client:match", limit=2, window_seconds=60, now=2)
    recovered = await limiter.check("client:match", limit=2, window_seconds=60, now=61)

    assert first.allowed is True
    assert first.remaining == 1
    assert second.allowed is True
    assert second.remaining == 0
    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 58
    assert recovered.allowed is True
