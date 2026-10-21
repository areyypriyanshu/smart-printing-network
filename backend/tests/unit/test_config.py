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


def test_clerk_is_off_until_it_is_switched_on() -> None:
    """A deployment that has not heard of Clerk cannot reach it.

    The migration is a configuration change rather than a code change,
    and the switch defaults to off so that a deployment which was never
    configured cannot end up talking to an identity provider it did not
    choose.
    """
    settings = _settings()

    assert settings.clerk_enabled is False
    assert settings.clerk_fapi_url == ""
    assert settings.clerk_allowed_origins == ""


def test_clerk_needs_an_instance_when_it_is_switched_on() -> None:
    """The instance's host is where the key set is published.

    Without it there is no key set to fetch and no issuer to check the
    token against, so a token from anywhere would be refused, which is
    safe but is not a working deployment.
    """
    with pytest.raises(ValidationError, match="CLERK_FAPI_URL is required"):
        _settings(
            clerk_enabled=True, clerk_fapi_url="", clerk_allowed_origins="http://localhost:5173"
        )


def test_clerk_needs_the_origins_whose_tokens_are_accepted() -> None:
    """A token carries the origin that asked for it.

    An instance can hold more than one application, so a token minted
    for a different one on the same instance is not a token for this
    one. Without the list, every token would be accepted, which is the
    thing the check exists to prevent.
    """
    with pytest.raises(ValidationError, match="CLERK_ALLOWED_ORIGINS is required"):
        _settings(
            clerk_enabled=True, clerk_fapi_url="https://app.accounts.dev", clerk_allowed_origins=""
        )


def test_clerk_with_an_instance_and_the_origins_is_valid() -> None:
    settings = _settings(
        clerk_enabled=True,
        clerk_fapi_url="https://app.accounts.dev",
        clerk_allowed_origins="http://localhost:5173,https://spn.example.com",
    )

    assert settings.clerk_enabled is True


def test_the_key_set_is_published_at_the_instance_host() -> None:
    """The key set is public, so the backend needs no secret to verify.

    Clerk serves the instance's public signing keys from the Frontend
    API host with a fixed path appended. Reading it from the same
    setting as the issuer means the two cannot disagree about which
    instance they are talking about.
    """
    settings = _settings(
        clerk_enabled=True,
        clerk_fapi_url="https://app.accounts.dev",
        clerk_allowed_origins="http://localhost:5173",
    )

    assert settings.clerk_jwks_url == "https://app.accounts.dev/.well-known/jwks.json"


def test_a_trailing_slash_does_not_double_up_in_the_key_set_address() -> None:
    settings = _settings(
        clerk_enabled=True,
        clerk_fapi_url="https://app.accounts.dev/",
        clerk_allowed_origins="http://localhost:5173",
    )

    assert settings.clerk_jwks_url == "https://app.accounts.dev/.well-known/jwks.json"


def test_the_origins_are_read_as_a_list() -> None:
    """A deployment has more than one origin, and spaces are not origins."""
    settings = _settings(
        clerk_enabled=True,
        clerk_fapi_url="https://app.accounts.dev",
        clerk_allowed_origins="http://localhost:5173, https://spn.example.com ,",
    )

    assert settings.clerk_origin_list == ["http://localhost:5173", "https://spn.example.com"]


def test_the_local_bypass_cannot_be_on_in_production() -> None:
    """The local bypass mints a session nobody proved.

    A deployment with it on would accept a session that was never
    proved, which is the whole thing the identity provider is for. The
    check is refused in production the way the testing surface is.
    """
    with pytest.raises(ValidationError, match="SPN_DEV_AUTH cannot be enabled"):
        _settings(
            env="production",
            jwt_secret="a-real-secret-that-is-not-the-placeholder",
            payment_provider="razorpay",
            razorpay_key_id="rzp_test_placeholder",
            razorpay_key_secret="placeholder",
            razorpay_webhook_secret="placeholder",
            spn_dev_auth=True,
        )


def test_the_local_bypass_is_allowed_outside_production() -> None:
    """The end to end suite needs a session without a network.

    It runs against the local stack, where the identity provider is not
    reachable, so the bypass has to be usable outside production.
    """
    settings = _settings(spn_dev_auth=True)

    assert settings.spn_dev_auth is True
