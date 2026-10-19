"""The gateway the application talks to: one online provider and one cash.

The service layer should not have to know which provider is configured, or
whether the customer is paying online or in cash. It says which method it
wants and gets back a gateway order from the right implementation.

Two rules the router enforces, and they are the reason it exists rather
than a `if method == ...` in the service:

- Only the online provider sends webhooks and only the online provider can
  refund. A cash payment must never reach the online refund path, so both
  of those calls go to the online gateway and nowhere else.
- The checkout key belongs to the online provider. A cash order never gets
  one, because there is no checkout to open.
"""

from app.gateways.payments.base import GatewayError, GatewayOrder, GatewayRefund, PaymentGateway
from app.gateways.payments.cash import CashGateway

ONLINE = "online"
AT_STORE = "at_store"
METHODS = (ONLINE, AT_STORE)


class PaymentGatewayRouter:
    """Dispatches to the online gateway or the cash gateway by method."""

    def __init__(self, *, online: PaymentGateway, cash: CashGateway | None = None) -> None:
        self._online = online
        self._cash = cash if cash is not None else CashGateway()
        # The online provider's name. The webhook handler records it on
        # `webhook_events.provider`, and only the online provider ever
        # sends a webhook, so it is the online provider's name even when
        # the application also handles cash orders. It is not a bug that
        # a cash order does not change it.
        self.provider = online.provider

    @property
    def checkout_key_id(self) -> str | None:
        """The online provider's checkout key, for opening its checkout."""
        return self._online.checkout_key_id

    def create_order(
        self,
        *,
        amount_paise: int,
        receipt: str,
        currency: str = "INR",
        method: str = ONLINE,
    ) -> GatewayOrder:
        if method == AT_STORE:
            return self._cash.create_order(
                amount_paise=amount_paise, receipt=receipt, currency=currency
            )
        if method != ONLINE:
            raise GatewayError(f"Unknown payment method: {method}")
        return self._online.create_order(
            amount_paise=amount_paise, receipt=receipt, currency=currency
        )

    def verify_webhook_signature(self, *, raw_body: bytes, signature: str) -> bool:
        """Only the online provider can have signed this."""
        return self._online.verify_webhook_signature(raw_body=raw_body, signature=signature)

    def sign(self, raw_body: bytes) -> str:
        """Sign a body the way the online provider would.

        Only the fake gateway can do this, and only the local
        simulate-payment endpoint needs it: it fabricates the webhook the
        provider would have sent, so the webhook handler can be exercised
        without a provider account.
        """
        signer = getattr(self._online, "sign", None)
        if signer is None:
            raise GatewayError("The configured provider cannot sign a body")
        return str(signer(raw_body))

    def refund(
        self, *, provider_payment_id: str, amount_paise: int, idempotency_note: str
    ) -> GatewayRefund:
        """Refunds go through the online provider.

        A cash payment is never queued for a refund, because no money was
        taken when it was booked. If one ever reached here, the online
        provider would refuse it, which is the safe outcome.
        """
        return self._online.refund(
            provider_payment_id=provider_payment_id,
            amount_paise=amount_paise,
            idempotency_note=idempotency_note,
        )
