import hashlib
import hmac
import uuid

from app.gateways.payments.base import GatewayOrder, GatewayRefund


class FakeGateway:
    """Local gateway used in development, tests and the simulate-payment endpoint."""

    provider = "fake"

    @property
    def checkout_key_id(self) -> str | None:
        return None

    def __init__(self, *, webhook_secret: str) -> None:
        """The fake gateway is keyed by a secret the operator chose.

        There is deliberately no default. The webhook route is public, so a
        key that is written in the repository is a key that anybody who has
        read the repository can use to mark an order paid. The caller has to
        supply the secret, so it cannot come from the source tree.
        """
        if not webhook_secret:
            raise ValueError("the fake gateway needs an explicit webhook secret")
        self._secret = webhook_secret.encode()

    def create_order(
        self,
        *,
        amount_paise: int,
        receipt: str,
        currency: str = "INR",
        method: str = "online",
    ) -> GatewayOrder:
        """Start a fake order.

        This gateway is the ONLINE fake. It stands in for Razorpay, so it
        always behaves like the online path whatever `method` says. The
        cash path has its own gateway and must not be served by this one.
        """
        return GatewayOrder(
            provider=self.provider,
            provider_order_id=f"fake_order_{receipt}",
            amount_paise=amount_paise,
            currency=currency,
        )

    def sign(self, raw_body: bytes) -> str:
        return hmac.new(self._secret, raw_body, hashlib.sha256).hexdigest()

    def verify_webhook_signature(self, *, raw_body: bytes, signature: str) -> bool:
        return hmac.compare_digest(self.sign(raw_body), signature)

    def refund(
        self, *, provider_payment_id: str, amount_paise: int, idempotency_note: str
    ) -> GatewayRefund:
        return GatewayRefund(
            provider=self.provider,
            refund_id=f"fake_refund_{uuid.uuid5(uuid.NAMESPACE_URL, idempotency_note).hex[:12]}",
            provider_payment_id=provider_payment_id,
            amount_paise=amount_paise,
        )
