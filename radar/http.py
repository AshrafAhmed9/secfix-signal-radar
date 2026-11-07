"""Shared outbound HTTP helper. Every external call in the project goes through request()."""
import random
import time
from urllib.parse import urlparse

import requests


class RequestFailed(Exception):
    """A request ended in a non-success state.

    status is the last HTTP status, or None for a network error/timeout.
    """

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def parse_retry_after(value: str | None) -> float | None:
    """Seconds from a Retry-After header. Only the numeric form; the HTTP-date form is ignored."""
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def backoff_delay(attempt: int, base: float, cap: float, rand=random.random) -> float:
    """Exponential backoff with full jitter (attempt is 0-based).

    Jitter spreads retries out so many clients don't hammer a recovering server at once.
    """
    return rand() * min(cap, base * 2 ** attempt)


def request(method: str, url: str, *, max_attempts: int = 5, timeout: float = 10.0,
            base_delay: float = 0.5, max_delay: float = 30.0,
            sleep=time.sleep, rand=random.random, **kwargs) -> requests.Response:
    """Send one HTTP request, retrying 429, 5xx and network errors.

    Other 4xx fail immediately: retrying a bad request or a bad token never helps.
    Errors name the host but never the full URL, because query strings can hold API keys.
    """
    host = urlparse(url).netloc
    last_status = None
    for attempt in range(max_attempts):
        resp = None
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)
        except (requests.ConnectionError, requests.Timeout):
            last_status = None
        else:
            if resp.status_code < 400:
                return resp
            last_status = resp.status_code
            if resp.status_code != 429 and resp.status_code < 500:
                raise RequestFailed(f"{method} {host}: HTTP {resp.status_code}", resp.status_code)

        if attempt == max_attempts - 1:
            break  # no point sleeping before giving up
        wait = parse_retry_after(resp.headers.get("Retry-After")) if resp is not None else None
        if wait is not None:
            wait = min(wait, max_delay)  # honour the server, but never stall a daily run for minutes
        else:
            wait = backoff_delay(attempt, base_delay, max_delay, rand)
        sleep(wait)

    raise RequestFailed(f"{method} {host}: gave up after {max_attempts} attempts", last_status)
