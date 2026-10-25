from functools import lru_cache
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.limits import MAX_COPIES, MAX_PAGES, MAX_PRICE_PAISE, MAX_RATE_PAISE


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

    max_upload_mb: int = 50
    max_pages: int = MAX_PAGES
    # Orders are paid in cash at the counter, so no new order waits for a
    # payment. The window is kept to expire orders that were booked by an
    # earlier version of the application and are still in PENDING_PAYMENT.
    payment_timeout_min: int = 15
    accept_timeout_min: int = 15
    file_retention_hours: int = 24
    no_show_timeout_hours: int = 24

    # The limits on creating an account. Registering is the most
    # expensive thing an anonymous caller can ask for: it writes a user
    # row and has the identity provider send a verification message, and
    # the work cannot be refused once it has started.
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
    # the reason a botnet cannot make the server do that work in a loop.

    google_maps_api_key: str = ""

    # Which provider turns an address into a point.
    #
    # "nominatim" is the public instance of OpenStreetMap's geocoder:
    # free, no key and no account. It is run on donated servers and its
    # policy asks for four things, which are done here: one call a
    # second for the whole application, a user agent that says who is
    # asking, the answers cached, and the attribution shown.
    #
    # "google" is the commercial one. It matches an Indian address
    # better, and it asks for a billing account.
    #
    # "none" means there is no geocoder at all, and the features that
    # need one ask for the coordinates instead.
    geocoding_provider: str = "nominatim"

    @field_validator("geocoding_provider")
    @classmethod
    def _the_provider_is_one_we_know(cls, value: str) -> str:
        """The name is compared the same way the builder compares it.

        The builder strips the name and folds its case, so a value of
        " Nominatim " has to be the same answer here as it is there.
        """
        provider = value.strip().lower()
        if provider not in {"nominatim", "google", "none"}:
            raise ValueError(f"GEOCODING_PROVIDER must be nominatim, google or none, not {value!r}")
        return provider

    # The key the server uses to turn an address into a point, when the
    # provider is Google. It is a different key from the one the browser
    # uses for the map, because the two are restricted in different
    # ways: the map key belongs to a list of websites, and this one
    # belongs to the server's own address. A key that is given to a
    # browser is a key that anybody can lift, and this one is a secret.
    google_geocoding_api_key: str = ""

    # Who the application says it is when it asks the map provider. The
    # policy asks for a user agent that identifies the application
    # rather than the one a library sets by itself, and for a way to
    # reach the operator. The address is in the repository, which is
    # where the operator can be found.
    geocoding_user_agent: str = Field(
        default=(
            "SmartPrintingNetwork/1.0 (+https://github.com/areyypriyanshu/smart-printing-network)"
        ),
        min_length=1,
    )

    # Where the OpenStreetMap geocoder lives. The public instance is
    # the default. A deployment that wants its own instance, or a
    # different provider's, changes this one value and restarts: the
    # policy asks for the service to be swappable without a software
    # update.
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"

    @field_validator("nominatim_base_url")
    @classmethod
    def _the_instance_is_an_address_on_the_web(cls, value: str) -> str:
        """Only http and https.

        The address is fetched by the server, so a value that pointed
        somewhere else — a file on the machine, say — would be a way to
        make the server read something it should not.
        """
        if not value.startswith(("http://", "https://")):
            raise ValueError("NOMINATIM_BASE_URL must be an http or https address")
        return value

    # The shortest time between two calls to the map provider, in
    # seconds. The policy asks for no more than one a second from the
    # whole application, so this is a limit on the process and not on a
    # customer.
    geocoding_min_interval: float = Field(default=1.0, ge=1.0)

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
        if self.geocoding_provider == "google" and not self.google_geocoding_api_key:
            raise ValueError(
                "GOOGLE_GEOCODING_API_KEY is required when GEOCODING_PROVIDER=google. "
                "Use GEOCODING_PROVIDER=nominatim for the free one."
            )
        if self.max_pages * MAX_COPIES * MAX_RATE_PAISE > MAX_PRICE_PAISE:
            # The price of an order is pages x copies x rate and it is
            # held in a 32 bit integer column. A page limit this high
            # would let a shop price an order the database cannot hold,
            # and the failure would land on the customer who tried to
            # order. The application refuses to start rather than
            # discovering it later.
            raise ValueError(
                f"MAX_PAGES={self.max_pages} is too high: the largest order "
                f"would be {self.max_pages * MAX_COPIES * MAX_RATE_PAISE} paise, "
                f"and the price column holds {MAX_PRICE_PAISE}. "
                f"At most {MAX_PRICE_PAISE // (MAX_COPIES * MAX_RATE_PAISE)} pages."
            )
        if self.spn_dev_auth and self.env == "production":
            raise ValueError(
                "SPN_DEV_AUTH cannot be enabled when ENV=production. It mints "
                "a session without the identity provider, so a deployment that "
                "has it on would accept a session that was never proved."
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
