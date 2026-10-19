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
    """
    if settings.payment_provider == "razorpay":
        online: PaymentGateway = RazorpayGateway(
            key_id=settings.razorpay_key_id,
            key_secret=settings.razorpay_key_secret,
            webhook_secret=settings.razorpay_webhook_secret,
        )
    else:
        online = FakeGateway()
    return PaymentGatewayRouter(online=online)
