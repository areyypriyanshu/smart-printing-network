"""The rules the payment gateway is built by.

The webhook route is public: anybody who can reach it can try to mark an
order paid. The only thing standing between them and a free print job is
the key the webhook is signed with, and a key that is written in the
repository is a key that everybody who has read the repository knows.

These are the rules that keep a published key out of the running
application, and they are properties of the gateway itself, so they are
tested here rather than through an endpoint.
"""

from types import SimpleNamespace

import pytest
from app.config import Settings
from app.gateways.payments import FakeGateway, build_payment_gateway


def _settings(**overrides: object) -> Settings:
    """A settings object with no environment behind it."""
    values: dict[str, object] = {
        "payment_provider": "fake",
        "fake_webhook_secret": "a-key-the-operator-chose",
        "env": "local",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def _raw_settings(**overrides: object) -> SimpleNamespace:
    """Settings that have not been through the validator.

    The configuration refuses an unusable combination before the gateway
    is ever built, and that refusal is tested in test_config.py. What is
    tested here is the gateway's own refusal, so that a settings object
    from somewhere else cannot get past it.
    """
    values: dict[str, object] = {
        "payment_provider": "fake",
        "fake_webhook_secret": "a-key-the-operator-chose",
        "env": "local",
        "razorpay_key_id": "",
        "razorpay_key_secret": "",
        "razorpay_webhook_secret": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_the_fake_gateway_has_no_default_key() -> None:
    """The fake gateway takes a key, or it does not exist.

    A default would be a key in the source tree, and a key in the source
    tree is a key that anybody who has read the repository can use.
    """
    with pytest.raises(TypeError):
        FakeGateway()  # type: ignore[call-arg]


def test_the_fake_gateway_refuses_an_empty_key() -> None:
    with pytest.raises(ValueError, match="explicit webhook secret"):
        FakeGateway(webhook_secret="")


def test_the_fake_gateway_signs_with_the_key_it_was_given() -> None:
    gateway = FakeGateway(webhook_secret="a-key-the-operator-chose")

    assert gateway.verify_webhook_signature(raw_body=b"{}", signature=gateway.sign(b"{}"))


def test_a_different_key_does_not_verify() -> None:
    gateway = FakeGateway(webhook_secret="a-key-the-operator-chose")
    other = FakeGateway(webhook_secret="a-different-key")

    assert not gateway.verify_webhook_signature(raw_body=b"{}", signature=other.sign(b"{}"))


def test_an_unknown_provider_is_an_error() -> None:
    """A misspelled provider name must not fall back to the fake gateway.

    The fallback would key the public webhook with a value that is in the
    repository, and it would do it silently.
    """
    with pytest.raises(ValueError, match="Unknown PAYMENT_PROVIDER"):
        build_payment_gateway(_raw_settings(payment_provider="razorpayy"))


def test_the_fake_provider_is_refused_in_production() -> None:
    with pytest.raises(ValueError, match="not allowed when ENV=production"):
        build_payment_gateway(_raw_settings(env="production"))


def test_the_fake_provider_needs_a_key() -> None:
    with pytest.raises(ValueError, match="FAKE_WEBHOOK_SECRET must be set"):
        build_payment_gateway(_raw_settings(fake_webhook_secret=""))


def test_the_fake_provider_is_built_with_the_operators_key() -> None:
    router = build_payment_gateway(_settings())

    assert router.provider == "fake"
    assert router.verify_webhook_signature(
        raw_body=b"{}",
        signature=FakeGateway(webhook_secret="a-key-the-operator-chose").sign(b"{}"),
    )


def test_the_configuration_also_refuses_an_unusable_combination() -> None:
    """The refusal happens before the application starts serving.

    A deployment that is misconfigured should find out at startup, not
    when the first payment arrives.
    """
    with pytest.raises(ValueError, match="FAKE_WEBHOOK_SECRET is required"):
        _settings(fake_webhook_secret="")
