"""The limits on creating an account.

Registering is the most expensive thing an anonymous caller can ask for,
so the limits are checked in one place, and this is where a caller can
be told which one it hit.
"""

import json
from types import SimpleNamespace
from typing import Any

import pytest
from app.config import get_settings
from app.errors import RateLimited
from app.rate_limit import RateLimiter, registration_limit
from starlette.requests import Request


def _request(host: str, email: str, limiter: RateLimiter) -> Request:
    """A request as the limiter sees it: who it came from, and what it says."""
    scope: dict[str, Any] = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/auth/register",
        "raw_path": b"/api/v1/auth/register",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": (host, 40000),
        "server": ("testserver", 80),
        "app": SimpleNamespace(state=SimpleNamespace(rate_limiter=limiter)),
    }
    request = Request(scope)
    request._body = json.dumps(  # noqa: SLF001
        {"email": email, "password": "abcd1234", "full_name": "Test User"}
    ).encode()
    return request


def _limit(account: str = "account:test") -> Any:
    """The registration limit, with the account key fixed.

    The real key comes from the database, and the key itself is
    covered by the API tests. What is tested here is the shape of the
    four limits: which one fires, and when.
    """
    return registration_limit(lambda request: account)


def test_one_machine_cannot_ask_for_too_many_accounts_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "register_address_per_minute", 3)
    monkeypatch.setattr(settings, "register_global_per_minute", 100)
    limit = _limit()
    limiter = RateLimiter()

    for _ in range(3):
        limit(_request("10.0.0.1", "one@example.com", limiter))

    with pytest.raises(RateLimited) as blocked:
        limit(_request("10.0.0.1", "two@example.com", limiter))

    assert "this address" in blocked.value.message


def test_a_slow_drip_from_one_machine_is_stopped_by_the_daily_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The minute limit does not see a machine that waits between accounts."""
    settings = get_settings()
    monkeypatch.setattr(settings, "register_address_per_minute", 100)
    monkeypatch.setattr(settings, "register_address_per_day", 2)
    monkeypatch.setattr(settings, "register_global_per_minute", 100)
    limit = _limit()
    limiter = RateLimiter()

    for index in range(2):
        limit(_request("10.0.0.1", f"drip{index}@example.com", limiter))

    with pytest.raises(RateLimited) as blocked:
        limit(_request("10.0.0.1", "drip3@example.com", limiter))

    assert "today" in blocked.value.message


def test_many_machines_cannot_claim_the_same_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The address limits are all keyed on the machine, so this one is not."""
    settings = get_settings()
    monkeypatch.setattr(settings, "register_address_per_minute", 100)
    monkeypatch.setattr(settings, "register_address_per_day", 100)
    monkeypatch.setattr(settings, "register_account_per_hour", 2)
    monkeypatch.setattr(settings, "register_global_per_minute", 100)
    limit = _limit(account="account:victim")
    limiter = RateLimiter()

    for index in range(2):
        limit(_request(f"10.0.0.{index}", "victim@example.com", limiter))

    with pytest.raises(RateLimited) as blocked:
        limit(_request("10.0.0.9", "victim@example.com", limiter))

    assert "email address" in blocked.value.message


def test_the_whole_deployment_cannot_create_more_accounts_than_it_can_afford(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The limit that bounds the work rather than the attacker."""
    settings = get_settings()
    monkeypatch.setattr(settings, "register_address_per_minute", 100)
    monkeypatch.setattr(settings, "register_address_per_day", 100)
    monkeypatch.setattr(settings, "register_account_per_hour", 100)
    monkeypatch.setattr(settings, "register_global_per_minute", 2)
    limit = _limit(account="account:one")
    limiter = RateLimiter()

    for index in range(2):
        limit(_request(f"10.0.0.{index}", f"user{index}@example.com", limiter))

    with pytest.raises(RateLimited) as blocked:
        limit(_request("10.0.0.9", "user9@example.com", limiter))

    assert "busy" in blocked.value.message


def test_the_answer_says_how_long_to_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "register_address_per_minute", 1)
    monkeypatch.setattr(settings, "register_global_per_minute", 100)
    limit = _limit()
    limiter = RateLimiter()

    limit(_request("10.0.0.1", "one@example.com", limiter))

    with pytest.raises(RateLimited) as blocked:
        limit(_request("10.0.0.1", "two@example.com", limiter))

    assert blocked.value.headers["Retry-After"].isdigit()
