import pytest
from app.config import PLACEHOLDER_JWT_SECRET, Settings
from pydantic import ValidationError


def test_razorpay_provider_requires_all_three_credentials() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, payment_provider="razorpay")


def test_razorpay_provider_with_credentials_is_valid() -> None:
    settings = Settings(
        _env_file=None,
        payment_provider="razorpay",
        razorpay_key_id="rzp_test_placeholder",
        razorpay_key_secret="placeholder",
        razorpay_webhook_secret="placeholder",
    )

    assert settings.payment_provider == "razorpay"


def test_production_rejects_placeholder_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, env="production", jwt_secret=PLACEHOLDER_JWT_SECRET)


def test_local_defaults_are_valid() -> None:
    settings = Settings(_env_file=None)

    assert settings.env == "local"
    assert settings.payment_provider == "fake"
    assert settings.max_upload_mb == 50
