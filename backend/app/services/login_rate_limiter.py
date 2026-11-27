from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import status

from app.errors import AppError


class LoginRateLimiter:
    """In-memory limit of failed logins per account and per client address (one process only)."""

    def __init__(self, name: str, *, window_seconds: int = 15 * 60, account_limit: int = 5, ip_limit: int = 20):
        # The name appears in the security log when the limiter blocks someone
        self.name = name
        self.window_seconds = window_seconds
        self.account_limit = account_limit
        self.ip_limit = ip_limit
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, username: str, ip_address: str) -> None:
        now = monotonic()
        with self._lock:
            account_attempts = self._active(f"account:{username.lower()}", now)
            ip_attempts = self._active(f"ip:{ip_address}", now)
            if len(account_attempts) >= self.account_limit or len(ip_attempts) >= self.ip_limit:
                raise AppError(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "too_many_attempts",
                    "Too many failed attempts, please try again later",
                    headers={"Retry-After": str(self.window_seconds)},
                    retry_after_seconds=self.window_seconds,
                )

    def record_failure(self, username: str, ip_address: str) -> bool:
        """Count a failure; True exactly when it reaches a limit, so a block is reported once."""
        now = monotonic()
        with self._lock:
            account_attempts = self._active(f"account:{username.lower()}", now)
            ip_attempts = self._active(f"ip:{ip_address}", now)
            account_attempts.append(now)
            ip_attempts.append(now)
            return len(account_attempts) == self.account_limit or len(ip_attempts) == self.ip_limit

    def record_success(self, username: str) -> None:
        with self._lock:
            self._attempts.pop(f"account:{username.lower()}", None)

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()

    def _active(self, key: str, now: float) -> deque[float]:
        attempts = self._attempts[key]
        cutoff = now - self.window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        return attempts


login_rate_limiter = LoginRateLimiter("login")
