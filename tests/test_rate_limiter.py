"""Tests for core/rate_limiter.py"""

import time
import threading
import pytest


# ---------------------------------------------------------------------------
# Basic acquire
# ---------------------------------------------------------------------------


def test_acquire_returns_true_when_tokens_available():
    from core.rate_limiter import RateLimiter
    limiter = RateLimiter(max_per_hour=10)
    assert limiter.acquire() is True


def test_burst_allowed_up_to_limit():
    from core.rate_limiter import RateLimiter
    # 10/hour → burst of 10 tokens available immediately
    limiter = RateLimiter(max_per_hour=10)
    results = [limiter.acquire() for _ in range(10)]
    assert all(results)


def test_limit_enforced_after_burst():
    from core.rate_limiter import RateLimiter
    limiter = RateLimiter(max_per_hour=10)
    # Exhaust all 10 tokens
    for _ in range(10):
        limiter.acquire()
    # Next acquire should fail
    assert limiter.acquire() is False


def test_acquire_or_raise_raises_when_exhausted():
    from core.rate_limiter import RateLimiter
    limiter = RateLimiter(max_per_hour=5)
    for _ in range(5):
        limiter.acquire()
    with pytest.raises(RuntimeError, match="Rate limit exceeded"):
        limiter.acquire_or_raise()


def test_acquire_or_raise_succeeds_when_tokens_available():
    from core.rate_limiter import RateLimiter
    limiter = RateLimiter(max_per_hour=10)
    limiter.acquire_or_raise()  # should not raise


# ---------------------------------------------------------------------------
# Refill over time
# ---------------------------------------------------------------------------


def test_refill_after_wait():
    from core.rate_limiter import RateLimiter
    # 3600/hour = 1 token/second
    limiter = RateLimiter(max_per_hour=3600, burst=1)
    limiter.acquire()  # consume the single token
    assert limiter.acquire() is False

    time.sleep(1.05)  # wait for ~1 token to refill
    assert limiter.acquire() is True


def test_burst_cap_does_not_exceed_max():
    from core.rate_limiter import RateLimiter
    limiter = RateLimiter(max_per_hour=3600, burst=2)
    # Even after a long wait, available_tokens should not exceed burst=2
    time.sleep(0.1)
    assert limiter.available_tokens <= 2.0 + 0.01  # small float tolerance


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


def test_thread_safety():
    from core.rate_limiter import RateLimiter
    limiter = RateLimiter(max_per_hour=100)
    successes = []
    lock = threading.Lock()

    def worker():
        result = limiter.acquire()
        with lock:
            successes.append(result)

    threads = [threading.Thread(target=worker) for _ in range(150)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly 100 should succeed (burst = max_per_hour = 100)
    assert sum(successes) == 100


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_max_per_hour_property():
    from core.rate_limiter import RateLimiter
    limiter = RateLimiter(max_per_hour=42)
    assert limiter.max_per_hour == 42


def test_invalid_max_per_hour_raises():
    from core.rate_limiter import RateLimiter
    with pytest.raises(ValueError):
        RateLimiter(max_per_hour=0)
    with pytest.raises(ValueError):
        RateLimiter(max_per_hour=-1)


def test_available_tokens_decreases_on_acquire():
    from core.rate_limiter import RateLimiter
    limiter = RateLimiter(max_per_hour=10)
    before = limiter.available_tokens
    limiter.acquire()
    after = limiter.available_tokens
    assert after < before


# ---------------------------------------------------------------------------
# get_default_limiter
# ---------------------------------------------------------------------------


def test_get_default_limiter_returns_same_instance():
    import core.rate_limiter as rl
    rl._default_limiter = None  # reset
    from core.rate_limiter import get_default_limiter
    a = get_default_limiter(max_per_hour=20)
    b = get_default_limiter(max_per_hour=999)  # second call — same instance
    assert a is b


def test_get_default_limiter_max_per_hour():
    import core.rate_limiter as rl
    rl._default_limiter = None  # reset
    from core.rate_limiter import get_default_limiter
    limiter = get_default_limiter(max_per_hour=15)
    assert limiter.max_per_hour == 15
