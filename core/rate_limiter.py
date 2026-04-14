"""
core/rate_limiter.py — Thread-safe token-bucket rate limiter.

Prevents runaway order submission. Configured via OperationalConfig.

Usage:
    from core.rate_limiter import RateLimiter

    limiter = RateLimiter(max_per_hour=10)

    if limiter.acquire():
        # submit order
    else:
        # rate limit hit — skip this iteration
"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """
    Token-bucket rate limiter.

    Tokens refill continuously at `max_per_hour / 3600` tokens/second.
    A single `acquire()` call consumes one token.

    Args:
        max_per_hour: Maximum number of acquisitions allowed per hour.
        burst: Maximum tokens that can accumulate (defaults to max_per_hour).
            Allows short bursts up to this limit even after an idle period.
    """

    def __init__(self, max_per_hour: int, burst: int | None = None) -> None:
        if max_per_hour <= 0:
            raise ValueError("max_per_hour must be positive")
        self._rate = max_per_hour / 3600.0  # tokens per second
        self._burst = float(burst if burst is not None else max_per_hour)
        self._tokens = self._burst
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        """Add tokens based on elapsed time. Called under lock."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def acquire(self) -> bool:
        """
        Attempt to consume one token.

        Returns:
            True if a token was available and consumed.
            False if rate limit is exceeded (caller should back off).
        """
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False

    def acquire_or_raise(self) -> None:
        """
        Consume one token or raise RuntimeError if rate limit exceeded.

        Raises:
            RuntimeError: Rate limit exceeded.
        """
        if not self.acquire():
            raise RuntimeError(
                f"Rate limit exceeded ({self._rate * 3600:.0f} requests/hour). "
                "Back off before submitting more orders."
            )

    @property
    def available_tokens(self) -> float:
        """Current number of available tokens (informational, not thread-safe for decisions)."""
        with self._lock:
            self._refill()
            return self._tokens

    @property
    def max_per_hour(self) -> int:
        """Configured maximum requests per hour."""
        return int(self._rate * 3600)


# ---------------------------------------------------------------------------
# Module-level default limiter (configurable at startup)
# ---------------------------------------------------------------------------

_default_limiter: RateLimiter | None = None


def get_default_limiter(max_per_hour: int = 10) -> RateLimiter:
    """
    Return (and lazily create) the module-level default limiter.

    Call this at application startup with the configured max_per_hour:
        from core.rate_limiter import get_default_limiter
        limiter = get_default_limiter(operational.polymarket_max_orders_per_hour)
    """
    global _default_limiter
    if _default_limiter is None:
        _default_limiter = RateLimiter(max_per_hour=max_per_hour)
    return _default_limiter
