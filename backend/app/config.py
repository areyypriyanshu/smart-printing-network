from functools import lru_cache
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://spn:spn@localhost:5432/spn"

    # Clerk, the identity provider. It proves who someone is; this
    # application decides what they may do. See ADR 029.
    #
    # There is one path. The provider signs every session token, the
    # application checks the signature, and there is no second way in,
    # so a deployment that has not been configured for the provider
    # cannot start rather than running with the front door open.
    #
    # The Frontend API URL is the instance's own host, and it is two
    # things: it is the issuer the token claims, and the key set is
    # published at that host with /.well-known/jwks.json appended. The
    # key set is public, so the backend does not need a secret to
    # verify a token, and it does not need to know the instance id.
    clerk_fapi_url: str = ""
    # The origins whose tokens are accepted. The token carries the
    # origin that asked for it, and a token minted for a different
    # application on the same instance is not a token for this one.
    # Comma separated, because a deployment has more than one origin:
    # the local front end and the deployed one.
    clerk_allowed_origins: str = ""
    # The provider's own secret key. It is used to read one person from
    # the provider when a local account is created, and it never reaches
    # the browser.
    clerk_secret_key: str = ""
    # The key the provider signs its webhooks with. The webhook route is
    # public, so a key that is written in the repository is a key that
    # anybody who has read the repository can use.
    clerk_webhook_signing_secret: str = ""
    # A local bypass that mints a token without the provider, for the
    # end to end suite. It is refused in production, and it is never a
    # way to skip a check: the role still comes from the database.
    spn_dev_auth: bool = False

    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket: str = "spn-files"
    s3_access_key: str = "spn"
    s3_secret_key: str = "spn-local-secret"

    payment_provider: str = "fake"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    # The key the fake gateway signs its webhooks with. There is no default:
    # the webhook route is public, so a key that is written in the repository
    # is a key that anybody who has read the repository can use. The local
    # .env sets one; a deployment sets its own.
    fake_webhook_secret: str = ""

    # Pay at the shop. Off by default in the code, so a deployment that
    # has never heard of it cannot create a cash order by accident. The
    # local .env turns it on.
    cash_at_store_enabled: bool = False

    # The testing surface (POST /testing/simulate-payment). Off by default in
    # the code, so a deployment that has not heard of it cannot expose it by
    # accident. The local .env turns it on; a production deployment must not.
    testing_endpoints_enabled: bool = False

    max_upload_mb: int = 50
    max_pages: int = 300
    payment_timeout_min: int = 15
    accept_timeout_min: int = 15
    file_retention_hours: int = 24
    no_show_timeout_hours: int = 24

    # The limits on creating an account. Registering is the most
    # expensive thing an anonymous caller can ask for, because the
    # password is hashed with argon2id, and the work cannot be refused
    # once it has started.
    #
    # The per address limits are generous on purpose: a campus puts
    # every student behind one address, so a limit that rations signups
    # would lock out the people it is meant to serve. They are here to
    # stop a machine, not to ration people.
    # The limit on one email address. This is what stops many machines
    # claiming the same address, which is how somebody else's address
    # gets taken.
    # The total the whole deployment will create in a minute. This is
    # the limit that bounds the work rather than the attacker, and it is
    # the reason a botnet cannot spend the server's CPU on password
    # hashes.

    google_maps_api_key: str = ""

    # Email. The console sender writes the message to the log, which is
    # what a local development machine uses and what a deployment must
    # not use: a verification message carries a link that proves an
    # address, and that link is a secret.
    email_provider: str = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@spn.local"
    # Whether the SMTP connection is encrypted from the first byte, which
    # is the usual arrangement on port 465. The usual arrangement on port
    # 587 is to start in the clear and upgrade with STARTTLS, and that
    # is what happens when this is off.
    smtp_use_tls: bool = False
    # Where the link in a verification message points. It is the address
    # a person opens in a browser, so it is the front end and not the
    # API.
    app_base_url: str = "http://localhost:5173"
    # How long a verification link is good for.
    email_verification_ttl_minutes: int = 1440

    @model_validator(mode="after")
    def _validate_environment(self) -> Self:
        if self.env not in {"local", "test", "production"}:
            raise ValueError(f"ENV must be local, test or production, not {self.env!r}")
        if self.testing_endpoints_enabled and self.env == "production":
            raise ValueError("the testing endpoints cannot be enabled when ENV=production")
        if self.spn_dev_auth and self.env == "production":
            raise ValueError(
                "SPN_DEV_AUTH cannot be enabled when ENV=production. It mints "
                "a session without the identity provider, so a deployment that "
                "has it on would accept a session that was never proved."
            )
        if self.payment_provider == "razorpay" and not (
            self.razorpay_key_id and self.razorpay_key_secret and self.razorpay_webhook_secret
        ):
            raise ValueError(
                "RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET and RAZORPAY_WEBHOOK_SECRET "
                "are required when PAYMENT_PROVIDER=razorpay"
            )
        if self.env == "production" and self.payment_provider != "razorpay":
            raise ValueError("PAYMENT_PROVIDER must be razorpay when ENV=production")
        if self.payment_provider == "fake" and not self.fake_webhook_secret:
            raise ValueError(
                "FAKE_WEBHOOK_SECRET is required when PAYMENT_PROVIDER=fake. "
                "The webhook route is public, so the key that signs its "
                "deliveries has to be one the operator chose. Set it in .env, "
                "or run `make up`, which generates one."
            )
        if self.email_provider == "smtp" and not self.smtp_host:
            raise ValueError("SMTP_HOST is required when EMAIL_PROVIDER=smtp")
        if self.env == "production" and self.email_provider == "console":
            raise ValueError(
                "EMAIL_PROVIDER=console is not allowed when ENV=production. "
                "It writes the verification link to the log, and that link is "
                "a secret. Use SMTP."
            )
        if not self.clerk_fapi_url:
            raise ValueError(
                "CLERK_FAPI_URL is required. It is the instance's own host, "
                "and the key set is published there. There is one way to "
                "sign in, so a deployment that has not been configured for "
                "it cannot start."
            )
        if not self.clerk_allowed_origins:
            raise ValueError(
                "CLERK_ALLOWED_ORIGINS is required. A token carries the "
                "origin that asked for it, and a token minted for another "
                "application on the same instance is not a token for this "
                "one."
            )
        if not self.clerk_secret_key:
            raise ValueError(
                "CLERK_SECRET_KEY is required. It is used to read one person "
                "from the identity provider when a local account is created."
            )
        if not self.clerk_webhook_signing_secret:
            raise ValueError(
                "CLERK_WEBHOOK_SIGNING_SECRET is required. The webhook route "
                "is public, so the key that signs its deliveries has to be "
                "one the operator chose."
            )
        return self

    @property
    def clerk_jwks_url(self) -> str:
        """Where the instance's public signing keys are published.

        Clerk serves them from the Frontend API host with a fixed path
        appended, so the key set needs no secret and no instance id to
        be fetched.
        """
        return f"{self.clerk_fapi_url.rstrip('/')}/.well-known/jwks.json"

    @property
    def clerk_origin_list(self) -> list[str]:
        """The origins whose tokens are accepted, as a list."""
        return [
            origin.strip() for origin in self.clerk_allowed_origins.split(",") if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
