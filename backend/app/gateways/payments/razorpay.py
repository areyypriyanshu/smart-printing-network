import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from app.gateways.payments.base import GatewayError, GatewayOrder, GatewayRefund

RAZORPAY_API = "https://api.razorpay.com/v1"


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    body: bytes
    headers: dict[str, str]


class RazorpayGateway:
    """Razorpay Orders and Refunds API.

    The HTTP call uses the standard library so the service keeps a small
    dependency surface; the request builders are pure and unit tested.
    """

    provider = "razorpay"

    def __init__(self, *, key_id: str, key_secret: str, webhook_secret: str) -> None:
        self._key_id = key_id
        self._key_secret = key_secret
        self._webhook_secret = webhook_secret.encode()

    @property
    def checkout_key_id(self) -> str | None:
        return self._key_id

    def build_order_request(
        self, *, amount_paise: int, receipt: str, currency: str = "INR"
    ) -> HttpRequest:
        body = json.dumps(
            {"amount": amount_paise, "currency": currency, "receipt": receipt}
        ).encode()
        return HttpRequest(
            method="POST",
            url=f"{RAZORPAY_API}/orders",
            body=body,
            headers=self._headers(body),
        )

    def build_refund_request(
        self, *, provider_payment_id: str, amount_paise: int, idempotency_note: str
    ) -> HttpRequest:
        body = json.dumps({"amount": amount_paise}).encode()
        headers = self._headers(body)
        headers["X-Razorpay-Idempotency-Key"] = idempotency_note
        return HttpRequest(
            method="POST",
            url=f"{RAZORPAY_API}/payments/{provider_payment_id}/refund",
            body=body,
            headers=headers,
        )

    def create_order(
        self, *, amount_paise: int, receipt: str, currency: str = "INR"
    ) -> GatewayOrder:
        request = self.build_order_request(
            amount_paise=amount_paise, receipt=receipt, currency=currency
        )
        payload = self._send(request)
        return GatewayOrder(
            provider=self.provider,
            provider_order_id=str(payload["id"]),
            amount_paise=int(payload.get("amount", amount_paise)),
            currency=str(payload.get("currency", currency)),
            checkout_key_id=self._key_id,
        )

    def verify_webhook_signature(self, *, raw_body: bytes, signature: str) -> bool:
        expected = hmac.new(self._webhook_secret, raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def refund(
        self, *, provider_payment_id: str, amount_paise: int, idempotency_note: str
    ) -> GatewayRefund:
        request = self.build_refund_request(
            provider_payment_id=provider_payment_id,
            amount_paise=amount_paise,
            idempotency_note=idempotency_note,
        )
        payload = self._send(request)
        return GatewayRefund(
            provider=self.provider,
            refund_id=str(payload["id"]),
            provider_payment_id=str(payload.get("payment_id", provider_payment_id)),
            amount_paise=int(payload.get("amount", amount_paise)),
        )

    def _headers(self, body: bytes) -> dict[str, str]:
        token = base64.b64encode(f"{self._key_id}:{self._key_secret}".encode()).decode()
        return {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }

    def _send(self, request: HttpRequest) -> dict[str, Any]:
        http_request = urllib.request.Request(
            request.url, data=request.body, headers=request.headers, method=request.method
        )
        try:
            with urllib.request.urlopen(http_request, timeout=15) as response:
                payload: dict[str, Any] = json.loads(response.read().decode())
                return payload
        except urllib.error.HTTPError as exc:
            raise GatewayError(f"Razorpay responded with status {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise GatewayError("Razorpay request failed") from exc
