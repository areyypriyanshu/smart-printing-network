from app.config import Settings
from app.gateways.payments.base import (
    GatewayError,
    GatewayOrder,
    GatewayRefund,
    PaymentGateway,
)
from app.gateways.payments.fake import FakeGateway
from app.gateways.payments.razorpay import RazorpayGateway

__all__ = [
    "FakeGateway",
    "GatewayError",
    "GatewayOrder",
    "GatewayRefund",
    "PaymentGateway",
    "RazorpayGateway",
    "build_payment_gateway",
]


def build_payment_gateway(settings: Settings) -> PaymentGateway:
    if settings.payment_provider == "razorpay":
        return RazorpayGateway(
            key_id=settings.razorpay_key_id,
            key_secret=settings.razorpay_key_secret,
            webhook_secret=settings.razorpay_webhook_secret,
        )
    return FakeGateway()
