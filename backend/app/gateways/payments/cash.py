"""The cash gateway: money that changes hands at the counter.

There is no provider behind this. The customer books the job, walks into
the shop, and pays in cash when they collect it. The only record of that
transaction is the shop's collect action, which is why the collect step
writes the order event, the payment capture and the timestamp together.

Two things this gateway must never do, and both are deliberate:

- It never accepts a webhook. There is no provider to sign one, so a
  signature check that could pass would be a hole in the payment path.
- It never refunds. Cash cannot be refunded through an interface; the
  shop gives the money back at the counter, and the domain must make sure
  a cash order is never queued for a refund.
"""

from app.gateways.payments.base import GatewayError, GatewayOrder, GatewayRefund

PROVIDER = "cash"


class CashGateway:
    """A gateway that takes no money and promises nothing to the provider."""

    provider = PROVIDER

    @property
    def checkout_key_id(self) -> str | None:
        """There is no checkout to open, so there is no key."""
        return None

    def create_order(
        self,
        *,
        amount_paise: int,
        receipt: str,
        currency: str = "INR",
        method: str = "online",
    ) -> GatewayOrder:
        """Record what the customer owes.

        The amount is the price of the print job. Nothing is captured
        here: the money changes hands at the counter, and the order's
        payment row stays `CREATED` until the shop collects it.
        """
        return GatewayOrder(
            provider=self.provider,
            provider_order_id=f"{PROVIDER}_order_{receipt}",
            amount_paise=amount_paise,
            currency=currency,
        )

    def verify_webhook_signature(self, *, raw_body: bytes, signature: str) -> bool:
        """Always false. Cash has no webhook, so no signature can be valid."""
        return False

    def refund(
        self, *, provider_payment_id: str, amount_paise: int, idempotency_note: str
    ) -> GatewayRefund:
        """Never. Cash is given back at the counter, not through a provider."""
        raise GatewayError("Cash payments cannot be refunded through a payment provider")
