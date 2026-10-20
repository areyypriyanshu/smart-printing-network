from functools import lru_cache
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_JWT_SECRET = "local-dev-placeholder-change-me-0123456789abcdef"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://spn:spn@localhost:5432/spn"

    jwt_secret: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 7

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
    register_address_per_minute: int = 5
    register_address_per_day: int = 100
    # The limit on one email address. This is what stops many machines
    # claiming the same address, which is how somebody else's address
    # gets taken.
    register_account_per_hour: int = 5
    # The total the whole deployment will create in a minute. This is
    # the limit that bounds the work rather than the attacker, and it is
    # the reason a botnet cannot spend the server's CPU on password
    # hashes.
    register_global_per_minute: int = 60

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
        if self.env == "production" and (
            not self.jwt_secret or self.jwt_secret == PLACEHOLDER_JWT_SECRET
        ):
            raise ValueError("JWT_SECRET must be set to a real secret in production")
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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
