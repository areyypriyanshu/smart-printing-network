from app.config import Settings
from app.gateways.payments.base import (
    GatewayError,
    GatewayOrder,
    GatewayRefund,
    PaymentGateway,
)
from app.gateways.payments.cash import CashGateway
from app.gateways.payments.fake import FakeGateway
from app.gateways.payments.razorpay import RazorpayGateway
from app.gateways.payments.router import AT_STORE, METHODS, ONLINE, PaymentGatewayRouter

__all__ = [
    "AT_STORE",
    "CashGateway",
    "FakeGateway",
    "GatewayError",
    "GatewayOrder",
    "GatewayRefund",
    "METHODS",
    "ONLINE",
    "PaymentGateway",
    "PaymentGatewayRouter",
    "RazorpayGateway",
    "build_payment_gateway",
]


def build_payment_gateway(settings: Settings) -> PaymentGatewayRouter:
    """The gateway the application uses.

    The online provider depends on the configuration. The cash gateway is
    always there, because paying at the counter is a property of the
    platform and not of the provider. The router hides both of them behind
    one interface.

    The provider name is matched exactly, and an unknown name is an error
    rather than a silent fallback to the fake gateway: the fallback would
    key the public webhook with a value that is in the repository.
    """
    provider = settings.payment_provider.strip().lower()
    if provider == "razorpay":
        online: PaymentGateway = RazorpayGateway(
            key_id=settings.razorpay_key_id,
            key_secret=settings.razorpay_key_secret,
            webhook_secret=settings.razorpay_webhook_secret,
        )
    elif provider == "fake":
        if settings.env == "production":
            raise ValueError("PAYMENT_PROVIDER=fake is not allowed when ENV=production")
        if not settings.fake_webhook_secret:
            raise ValueError("FAKE_WEBHOOK_SECRET must be set when PAYMENT_PROVIDER=fake")
        online = FakeGateway(webhook_secret=settings.fake_webhook_secret)
    else:
        raise ValueError(f"Unknown PAYMENT_PROVIDER: {settings.payment_provider!r}")
    return PaymentGatewayRouter(online=online)
