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

    # Pay at the shop. Off by default in the code, so a deployment that
    # has never heard of it cannot create a cash order by accident. The
    # local .env turns it on.
    cash_at_store_enabled: bool = False

    max_upload_mb: int = 50
    max_pages: int = 300
    payment_timeout_min: int = 15
    accept_timeout_min: int = 15
    file_retention_hours: int = 24
    no_show_timeout_hours: int = 24

    google_maps_api_key: str = ""

    @model_validator(mode="after")
    def _validate_environment(self) -> Self:
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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
