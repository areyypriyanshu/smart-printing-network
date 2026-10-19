import hashlib
import hmac
import json

from app.gateways.payments.razorpay import RazorpayGateway

SECRET = "whsec_test"
GATEWAY = RazorpayGateway(
    key_id="rzp_test_key", key_secret="rzp_test_secret", webhook_secret=SECRET
)


def test_order_request_carries_paise_amount_and_receipt() -> None:
    request = GATEWAY.build_order_request(amount_paise=3840, receipt="order-1")

    assert request.method == "POST"
    assert request.url == "https://api.razorpay.com/v1/orders"
    body = json.loads(request.body)
    assert body == {"amount": 3840, "currency": "INR", "receipt": "order-1"}


def test_order_request_uses_basic_auth_with_the_account_key() -> None:
    request = GATEWAY.build_order_request(amount_paise=100, receipt="order-1")

    assert request.headers["Authorization"].startswith("Basic ")
    assert request.headers["Content-Type"] == "application/json"


def test_refund_request_is_idempotent_by_note() -> None:
    request = GATEWAY.build_refund_request(
        provider_payment_id="pay_1", amount_paise=500, idempotency_note="payment-1"
    )

    assert request.url == "https://api.razorpay.com/v1/payments/pay_1/refund"
    assert request.headers["X-Razorpay-Idempotency-Key"] == "payment-1"
    assert json.loads(request.body) == {"amount": 500}


def test_webhook_signature_matches_the_hmac_of_the_raw_body() -> None:
    raw_body = b'{"event":"order.paid"}'
    signature = hmac.new(SECRET.encode(), raw_body, hashlib.sha256).hexdigest()

    assert GATEWAY.verify_webhook_signature(raw_body=raw_body, signature=signature)
    assert not GATEWAY.verify_webhook_signature(raw_body=raw_body, signature="0" * 64)


def test_webhook_signature_rejects_a_body_that_was_tampered_with() -> None:
    raw_body = b'{"event":"order.paid","amount":1}'
    signature = hmac.new(SECRET.encode(), raw_body, hashlib.sha256).hexdigest()

    assert not GATEWAY.verify_webhook_signature(
        raw_body=b'{"event":"order.paid","amount":9999}', signature=signature
    )
