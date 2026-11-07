"""Shared outbound HTTP helper. Every external call in the project goes through request().

Ashraf implements this file. Tests in tests/test_http.py define the behaviour.
"""
import random
import time

import requests

RETRY_STATUSES = {429}  # plus every 5xx, see request()


class RequestFailed(Exception):
    """Raised when a request ends in a non-success state.

    status is the last HTTP status, or None when the failure was a network error/timeout.
    """

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def parse_retry_after(value: str | None) -> float | None:
    """Seconds to wait from a Retry-After header value.

    "2" -> 2.0, "0" -> 0.0. None, empty, negative or non-numeric (including the
    HTTP-date form, which we deliberately ignore) -> None.
    """
    raise NotImplementedError  # Ashraf implements


def backoff_delay(attempt: int, base: float, cap: float, rand=random.random) -> float:
    """Exponential backoff with full jitter.

    attempt is 0-based. The ceiling is min(cap, base * 2**attempt); the result is
    rand() * ceiling, so rand=lambda: 1.0 gives the ceiling and lambda: 0.0 gives 0.
    """
    raise NotImplementedError  # Ashraf implements


def request(method: str, url: str, *, max_attempts: int = 5, timeout: float = 10.0,
            base_delay: float = 0.5, max_delay: float = 30.0,
            sleep=time.sleep, rand=random.random, **kwargs) -> requests.Response:
    """Send one HTTP request with retries.

    - Calls requests.request(method, url, timeout=timeout, **kwargs). Always pass a timeout.
    - Status < 400: return the response.
    - 429 or any 5xx: retry. Wait Retry-After seconds if the header parses, capped at
      max_delay; otherwise backoff_delay(attempt, base_delay, max_delay, rand).
    - Any other 4xx: no retry. Raise RequestFailed(status=...) immediately, no sleep.
    - requests.ConnectionError / requests.Timeout: retry like a 5xx.
    - At most max_attempts calls in total. After the last attempt fails, raise
      RequestFailed with the last status (None for network errors).
    - Never sleep after the final attempt.
    """
    raise NotImplementedError  # Ashraf implements
