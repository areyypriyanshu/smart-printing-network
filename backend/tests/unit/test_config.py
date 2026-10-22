import pytest
from app.config import Settings
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
    # The identity provider. There is one way to sign in, so these are
    # always needed. They are here so that a deployment which has them
    # configured cannot change what these tests mean: the values below
    # win over the environment.
    "clerk_fapi_url": "https://app.accounts.dev",
    "clerk_allowed_origins": "http://localhost:5173",
    "clerk_secret_key": "a-secret-the-operator-chose",
    "clerk_webhook_signing_secret": "whsec_another-secret-the-operator-chose",
    "spn_dev_auth": False,
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


def test_production_rejects_the_fake_payment_provider() -> None:
    """The fake provider's webhook key is a key somebody could read.

    The webhook route is public, so a deployment that is in production mode
    must not be running the fake gateway, whatever else it is configured
    with.
    """
    with pytest.raises(ValidationError, match="PAYMENT_PROVIDER must be razorpay"):
        _settings(env="production")


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


def test_the_identity_provider_is_always_configured() -> None:
    """There is one way to sign in, so a deployment cannot start without it.

    A deployment that has not been told about the identity provider
    cannot sign anybody in, and a deployment that starts anyway is a
    deployment with a front door and nothing behind it.
    """
    defaults = Settings.model_fields

    assert defaults["clerk_fapi_url"].default == ""
    assert defaults["clerk_allowed_origins"].default == ""
    assert defaults["clerk_secret_key"].default == ""
    assert defaults["clerk_webhook_signing_secret"].default == ""


def test_the_instance_is_required() -> None:
    """The instance's host is where the key set is published.

    Without it there is no key set to fetch and no issuer to check the
    token against, so a token from anywhere would be refused, which is
    safe but is not a working deployment.
    """
    with pytest.raises(ValidationError, match="CLERK_FAPI_URL is required"):
        _settings(clerk_fapi_url="")


def test_the_origins_whose_tokens_are_accepted_are_required() -> None:
    """A token carries the origin that asked for it.

    A token minted for another application on the same instance is not
    a token for this one, and the only way to tell them apart is the
    origin.
    """
    with pytest.raises(ValidationError, match="CLERK_ALLOWED_ORIGINS is required"):
        _settings(clerk_allowed_origins="")


def test_the_secret_key_is_required() -> None:
    """It is used to read one person from the provider."""
    with pytest.raises(ValidationError, match="CLERK_SECRET_KEY is required"):
        _settings(clerk_secret_key="")


def test_the_webhook_signing_secret_is_required() -> None:
    """The webhook route is public, so the key that signs it is the only proof."""
    with pytest.raises(ValidationError, match="CLERK_WEBHOOK_SIGNING_SECRET is required"):
        _settings(clerk_webhook_signing_secret="")


def test_a_configured_instance_is_valid() -> None:
    settings = _settings(
        clerk_fapi_url="https://app.accounts.dev",
        clerk_allowed_origins="http://localhost:5173,https://spn.example.com",
    )

    assert settings.clerk_fapi_url == "https://app.accounts.dev"
    assert settings.clerk_origin_list == ["http://localhost:5173", "https://spn.example.com"]


def test_the_key_set_is_published_at_the_instance_host() -> None:
    settings = _settings(
        clerk_fapi_url="https://app.accounts.dev",
        clerk_allowed_origins="http://localhost:5173",
    )

    assert settings.clerk_jwks_url == "https://app.accounts.dev/.well-known/jwks.json"


def test_the_key_set_host_does_not_carry_a_trailing_slash() -> None:
    settings = _settings(
        clerk_fapi_url="https://app.accounts.dev/",
        clerk_allowed_origins="http://localhost:5173",
    )

    assert settings.clerk_jwks_url == "https://app.accounts.dev/.well-known/jwks.json"


def test_the_geocoding_provider_has_to_be_one_we_know() -> None:
    with pytest.raises(ValidationError, match="GEOCODING_PROVIDER"):
        _settings(geocoding_provider="carrier-pigeon")


def test_the_geocoding_provider_is_read_the_same_way_everywhere() -> None:
    """The name is stripped and folded, so a deployment that writes
    " Nominatim " is not refused at startup and then accepted by the
    builder."""
    assert _settings(geocoding_provider=" Nominatim ").geocoding_provider == "nominatim"


def test_the_commercial_geocoder_needs_its_key() -> None:
    with pytest.raises(ValidationError, match="GOOGLE_GEOCODING_API_KEY"):
        _settings(geocoding_provider="google")


def test_a_deployment_can_have_no_geocoder_at_all() -> None:
    assert _settings(geocoding_provider="none").geocoding_provider == "none"


def test_the_map_provider_is_not_asked_more_than_once_a_second() -> None:
    """The policy asks for no more than one call a second, so a
    smaller interval is refused rather than obeyed."""
    with pytest.raises(ValidationError):
        _settings(geocoding_min_interval=0.5)


def test_the_user_agent_cannot_be_empty() -> None:
    """The policy asks for a user agent that identifies the
    application, and an empty one does not."""
    with pytest.raises(ValidationError):
        _settings(geocoding_user_agent="")


def test_the_map_provider_has_to_be_on_the_web() -> None:
    """The address is fetched by the server, so a value that pointed
    somewhere else would be a way to make it read a local file."""
    with pytest.raises(ValidationError, match="NOMINATIM_BASE_URL"):
        _settings(nominatim_base_url="file:///etc/passwd")


def test_the_page_limit_cannot_be_raised_past_the_price_the_column_holds() -> None:
    """The price of an order is pages x copies x rate and it is held in
    a 32 bit integer column. A page limit this high would let a shop
    price an order the database cannot hold."""
    with pytest.raises(ValidationError, match="MAX_PAGES"):
        _settings(max_pages=500)
