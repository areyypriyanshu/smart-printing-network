import pytest
from app.config import PLACEHOLDER_JWT_SECRET, Settings
from pydantic import ValidationError

#: The settings a test starts from. Every value is passed in, so the
#: test says what it means and the environment it runs in cannot change
#: the answer. `_env_file=None` stops the file being read; the
#: environment variables are overridden by the values below.
BASE: dict[str, object] = {
    "env": "local",
    "payment_provider": "fake",
    "fake_webhook_secret": "a-key-the-operator-chose",
    "testing_endpoints_enabled": False,
}


def _settings(**overrides: object) -> Settings:
    values = {**BASE, **overrides}
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_razorpay_provider_requires_all_three_credentials() -> None:
    with pytest.raises(ValidationError):
        _settings(payment_provider="razorpay", fake_webhook_secret="")


def test_razorpay_provider_with_credentials_is_valid() -> None:
    settings = _settings(
        payment_provider="razorpay",
        razorpay_key_id="rzp_test_placeholder",
        razorpay_key_secret="placeholder",
        razorpay_webhook_secret="placeholder",
    )

    assert settings.payment_provider == "razorpay"


def test_production_rejects_placeholder_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET must be set to a real secret"):
        _settings(
            env="production",
            jwt_secret=PLACEHOLDER_JWT_SECRET,
            payment_provider="razorpay",
            razorpay_key_id="rzp_test_placeholder",
            razorpay_key_secret="placeholder",
            razorpay_webhook_secret="placeholder",
        )


def test_production_rejects_the_fake_payment_provider() -> None:
    """The fake provider's webhook key is a key somebody could read.

    The webhook route is public, so a deployment that is in production mode
    must not be running the fake gateway, whatever else it is configured
    with.
    """
    with pytest.raises(ValidationError, match="PAYMENT_PROVIDER must be razorpay"):
        _settings(env="production", jwt_secret="a-real-secret-that-is-not-the-placeholder")


def test_the_fake_provider_needs_a_key_of_its_own() -> None:
    """The fake gateway has no default key.

    A key that is written in the repository is a key that anybody who has
    read the repository can use to mark an order paid, so the setting has
    to be supplied.
    """
    with pytest.raises(ValidationError, match="FAKE_WEBHOOK_SECRET is required"):
        _settings(fake_webhook_secret="")


def test_the_fake_provider_with_a_key_is_valid() -> None:
    settings = _settings(fake_webhook_secret="a-key-the-operator-chose")

    assert settings.payment_provider == "fake"
    assert settings.fake_webhook_secret == "a-key-the-operator-chose"


def test_the_environment_is_an_allow_list() -> None:
    """A mode string that is not exactly one of the three is a mistake.

    Every production-only check is keyed on the exact string 'production',
    so a spelling that is nearly right has to be refused rather than
    quietly running the checks in the wrong mode.
    """
    with pytest.raises(ValidationError, match="ENV must be local, test or production"):
        _settings(env="prod")


def test_the_testing_surface_cannot_be_on_in_production() -> None:
    with pytest.raises(ValidationError, match="testing endpoints cannot be enabled"):
        _settings(
            env="production",
            jwt_secret="a-real-secret-that-is-not-the-placeholder",
            payment_provider="razorpay",
            razorpay_key_id="rzp_test_placeholder",
            razorpay_key_secret="placeholder",
            razorpay_webhook_secret="placeholder",
            testing_endpoints_enabled=True,
        )


def test_local_defaults_are_valid_once_the_fake_key_is_set() -> None:
    settings = _settings()

    assert settings.env == "local"
    assert settings.payment_provider == "fake"
    assert settings.max_upload_mb == 50
