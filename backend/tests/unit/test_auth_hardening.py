"""The things an attacker learns from a login attempt.

A login says three things that a stranger can measure: how long it
took, which account it counted against, and how strong the password has
to be. Each of them has been a way in, so each of them is a rule with a
test.

The rules that need a database are tested in the integration suite; the
ones here are the pure ones.
"""

import pytest
from app import security
from app.rate_limit import RateLimiter
from app.services import auth_service


def test_an_unknown_address_is_checked_against_a_hash_too() -> None:
    """The check for an address that does not exist still does the work.

    The hash is of a value nobody knows, so the check always fails, and
    it fails the same way it fails for a real account with a wrong
    password.
    """
    assert auth_service._UNKNOWN_ACCOUNT_HASH
    assert not security.verify_password("any-password", auth_service._UNKNOWN_ACCOUNT_HASH)


def test_the_rate_limiter_counts_the_key_it_is_given() -> None:
    limiter = RateLimiter()

    for _ in range(3):
        assert limiter.check("one-account", 3, 60) is None
    assert limiter.check("one-account", 3, 60) is not None
    assert limiter.check("another-account", 3, 60) is None


def test_the_password_policy_is_one_policy() -> None:
    """Every path that creates an account holds the same rule."""
    assert security.validate_password_strength("longenoughpassword") == "longenoughpassword"
    with pytest.raises(ValueError, match="at least"):
        security.validate_password_strength("short")
    with pytest.raises(ValueError, match="at most"):
        security.validate_password_strength("x" * (security.MAX_PASSWORD_LENGTH + 1))
