from dataclasses import dataclass
from typing import Protocol


class GatewayError(RuntimeError):
    """Raised when the payment provider cannot complete a request."""


@dataclass(frozen=True)
class GatewayOrder:
    provider: str
    provider_order_id: str
    amount_paise: int
    currency: str
    checkout_key_id: str | None = None


@dataclass(frozen=True)
class GatewayRefund:
    provider: str
    refund_id: str
    provider_payment_id: str
    amount_paise: int


class PaymentGateway(Protocol):
    provider: str

    @property
    def checkout_key_id(self) -> str | None: ...

    def create_order(
        self, *, amount_paise: int, receipt: str, currency: str = "INR"
    ) -> GatewayOrder: ...

    def verify_webhook_signature(self, *, raw_body: bytes, signature: str) -> bool: ...

    def refund(
        self, *, provider_payment_id: str, amount_paise: int, idempotency_note: str
    ) -> GatewayRefund: ...
