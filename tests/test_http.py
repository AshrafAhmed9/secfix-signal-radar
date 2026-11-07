import pytest
import requests

from radar import http
from tests.fakes import FakeResponse


def script(monkeypatch, outcomes):
    """Replace requests.request with a scripted sequence of responses/exceptions."""
    calls = []
    outcomes = iter(outcomes)

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(http.requests, "request", fake_request)
    return calls


def run(**kwargs):
    slept = []
    kwargs.setdefault("rand", lambda: 1.0)  # jitter off: delay is the ceiling
    resp = http.request("GET", "https://example.test/x", sleep=slept.append, **kwargs)
    return resp, slept


def test_success_returns_response_without_sleeping(monkeypatch):
    calls = script(monkeypatch, [FakeResponse(200)])
    resp, slept = run()
    assert resp.status_code == 200
    assert len(calls) == 1 and slept == []


def test_429_is_retried_then_succeeds(monkeypatch):
    calls = script(monkeypatch, [FakeResponse(429), FakeResponse(200)])
    resp, slept = run()
    assert resp.status_code == 200
    assert len(calls) == 2 and len(slept) == 1


def test_5xx_is_retried_until_success(monkeypatch):
    calls = script(monkeypatch, [FakeResponse(503), FakeResponse(502), FakeResponse(200)])
    resp, slept = run()
    assert resp.status_code == 200
    assert len(calls) == 3 and len(slept) == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_other_4xx_is_not_retried(monkeypatch, status):
    calls = script(monkeypatch, [FakeResponse(status), FakeResponse(200)])
    slept = []
    with pytest.raises(http.RequestFailed) as exc:
        http.request("GET", "https://example.test/x", sleep=slept.append)
    assert exc.value.status == status
    assert len(calls) == 1 and slept == []


def test_gives_up_after_max_attempts(monkeypatch):
    calls = script(monkeypatch, [FakeResponse(500)] * 3)
    slept = []
    with pytest.raises(http.RequestFailed) as exc:
        http.request("GET", "https://example.test/x", max_attempts=3, sleep=slept.append)
    assert exc.value.status == 500
    assert len(calls) == 3
    assert len(slept) == 2  # no sleep after the last attempt


def test_backoff_grows_between_attempts(monkeypatch):
    script(monkeypatch, [FakeResponse(500), FakeResponse(500), FakeResponse(200)])
    _, slept = run(base_delay=0.5, max_delay=30.0)
    assert slept == [0.5, 1.0]


def test_retry_after_header_is_honoured(monkeypatch):
    script(monkeypatch, [FakeResponse(429, headers={"Retry-After": "2"}), FakeResponse(200)])
    _, slept = run()
    assert slept == [2.0]


def test_retry_after_is_capped_by_max_delay(monkeypatch):
    script(monkeypatch, [FakeResponse(429, headers={"Retry-After": "120"}), FakeResponse(200)])
    _, slept = run(max_delay=5.0)
    assert slept == [5.0]


def test_connection_error_is_retried(monkeypatch):
    calls = script(monkeypatch, [requests.ConnectionError("boom"), FakeResponse(200)])
    resp, slept = run()
    assert resp.status_code == 200
    assert len(calls) == 2 and len(slept) == 1


def test_timeout_exhausted_raises_without_status(monkeypatch):
    script(monkeypatch, [requests.Timeout("slow")] * 2)
    with pytest.raises(http.RequestFailed) as exc:
        http.request("GET", "https://example.test/x", max_attempts=2, sleep=lambda s: None)
    assert exc.value.status is None


def test_timeout_and_kwargs_are_passed_to_requests(monkeypatch):
    calls = script(monkeypatch, [FakeResponse(200)])
    run(json={"a": 1}, timeout=7.0)
    method, url, kwargs = calls[0]
    assert (method, url) == ("GET", "https://example.test/x")
    assert kwargs["timeout"] == 7.0 and kwargs["json"] == {"a": 1}


def test_default_timeout_is_always_set(monkeypatch):
    calls = script(monkeypatch, [FakeResponse(200)])
    run()
    assert calls[0][2]["timeout"] == 10.0


@pytest.mark.parametrize("attempt,expected", [(0, 0.5), (1, 1.0), (3, 4.0), (10, 30.0)])
def test_backoff_delay_doubles_then_caps(attempt, expected):
    assert http.backoff_delay(attempt, base=0.5, cap=30.0, rand=lambda: 1.0) == expected


def test_backoff_delay_has_jitter():
    assert http.backoff_delay(3, base=0.5, cap=30.0, rand=lambda: 0.0) == 0.0
    assert http.backoff_delay(3, base=0.5, cap=30.0, rand=lambda: 0.5) == 2.0


@pytest.mark.parametrize("value,expected", [
    ("2", 2.0), ("0", 0.0), ("1.5", 1.5),
    (None, None), ("", None), ("abc", None), ("-3", None),
    ("Wed, 21 Oct 2026 07:28:00 GMT", None),
])
def test_parse_retry_after(value, expected):
    assert http.parse_retry_after(value) == expected
