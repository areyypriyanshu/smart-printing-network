"""The cash gateway and the router that dispatches to it.

The two properties that matter here are safety properties: a cash
payment must never be able to look like an online one, and it must never
reach the online refund path. They are tested here rather than left to
the integration tests, because they are properties of the gateway itself.
"""

import pytest
from app.gateways.payments import (
    AT_STORE,
    ONLINE,
    CashGateway,
    FakeGateway,
    GatewayError,
    PaymentGatewayRouter,
)


def test_cash_orders_are_recorded_but_not_captured() -> None:
    """The amount is recorded. Nothing is taken."""
    gateway = CashGateway()

    order = gateway.create_order(amount_paise=2000, receipt="order-1")

    assert order.provider == "cash"
    assert order.provider_order_id == "cash_order_order-1"
    assert order.amount_paise == 2000
    assert order.currency == "INR"


def test_cash_has_no_checkout_key() -> None:
    """There is no checkout to open, so there is no key."""
    assert CashGateway().checkout_key_id is None


def test_cash_never_accepts_a_webhook_signature() -> None:
    """A signature check that could pass would be a hole in the payment path."""
    gateway = CashGateway()

    assert gateway.verify_webhook_signature(raw_body=b"{}", signature="anything") is False
    assert gateway.verify_webhook_signature(raw_body=b"{}", signature="") is False


def test_cash_never_refunds() -> None:
    """Cash is given back at the counter, not through a provider."""
    with pytest.raises(GatewayError):
        CashGateway().refund(
            provider_payment_id="cash_payment_1",
            amount_paise=2000,
            idempotency_note="note-1",
        )


def test_the_router_sends_a_cash_order_to_the_cash_gateway() -> None:
    online = FakeGateway()
    router = PaymentGatewayRouter(online=online)

    order = router.create_order(amount_paise=2000, receipt="order-1", method=AT_STORE)

    assert order.provider == "cash"


def test_the_router_sends_an_online_order_to_the_online_gateway() -> None:
    online = FakeGateway()
    router = PaymentGatewayRouter(online=online)

    order = router.create_order(amount_paise=2000, receipt="order-1", method=ONLINE)

    assert order.provider == "fake"


def test_the_router_defaults_to_the_online_gateway() -> None:
    router = PaymentGatewayRouter(online=FakeGateway())

    order = router.create_order(amount_paise=2000, receipt="order-1")

    assert order.provider == "fake"


def test_the_router_refuses_an_unknown_method() -> None:
    router = PaymentGatewayRouter(online=FakeGateway())

    with pytest.raises(GatewayError):
        router.create_order(amount_paise=2000, receipt="order-1", method="cheque")


def test_the_router_names_the_online_provider() -> None:
    """The webhook handler records it, and only the online provider sends one."""
    router = PaymentGatewayRouter(online=FakeGateway())

    assert router.provider == "fake"


def test_the_router_checks_the_signature_with_the_online_gateway() -> None:
    """A cash order has no provider, so only the online one can sign."""
    router = PaymentGatewayRouter(online=FakeGateway())
    body = b'{"event":"order.paid"}'

    assert router.verify_webhook_signature(raw_body=body, signature=FakeGateway().sign(body))


def test_the_router_refunds_through_the_online_gateway() -> None:
    """A cash payment is never queued for a refund, and this is the last line
    of defence if one ever were."""
    router = PaymentGatewayRouter(online=FakeGateway())

    refund = router.refund(
        provider_payment_id="pay_1", amount_paise=2000, idempotency_note="note-1"
    )

    assert refund.provider == "fake"


def test_the_router_signs_a_body_with_the_online_gateway() -> None:
    """The local simulate-payment endpoint needs a signed body."""
    router = PaymentGatewayRouter(online=FakeGateway())
    body = b'{"event":"order.paid"}'

    assert router.sign(body) == FakeGateway().sign(body)


def test_the_router_cannot_sign_with_a_provider_that_cannot() -> None:
    class NoSigner:
        provider = "razorpay"
        checkout_key_id = "key_1"

        def create_order(self, **kwargs: object) -> object:
            raise AssertionError("not used")

        def verify_webhook_signature(self, *, raw_body: bytes, signature: str) -> bool:
            return False

        def refund(self, **kwargs: object) -> object:
            raise AssertionError("not used")

    router = PaymentGatewayRouter(online=NoSigner())  # type: ignore[arg-type]

    with pytest.raises(GatewayError):
        router.sign(b"{}")
