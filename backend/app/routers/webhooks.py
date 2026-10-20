import json

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user, get_payment_gateway
from app.errors import Conflict, NotFound
from app.gateways.payments import PaymentGateway, PaymentGatewayRouter
from app.models import Order, Payment, User
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.payment import SimulatePaymentRequest
from app.services import payment_service

router = APIRouter(tags=["payments"], responses=ERROR_RESPONSES)


async def _raw_body(request: Request) -> bytes:
    return await request.body()


@router.post("/webhooks/razorpay")
def razorpay_webhook(
    raw_body: bytes = Depends(_raw_body),
    signature: str = Header(default="", alias="X-Razorpay-Signature"),
    event_id: str = Header(..., min_length=1, alias="X-Razorpay-Event-Id"),
    session: Session = Depends(get_db),
    gateway: PaymentGateway = Depends(get_payment_gateway),
) -> dict[str, str]:
    """Take a delivery from the payment provider.

    The event id is required and it cannot be empty, and the contract
    says so: a delivery without one cannot be deduplicated, and the
    provider always sends one. The signature is not required in the
    contract, because a delivery without one is refused with a signature
    error, which is a better answer than a validation error.
    """
    outcome = payment_service.handle_webhook(
        session,
        raw_body=raw_body,
        signature=signature,
        event_id=event_id,
        gateway=gateway,
    )
    return {"status": outcome}


@router.post("/testing/simulate-payment")
def simulate_payment(
    body: SimulatePaymentRequest,
    session: Session = Depends(get_db),
    gateway: PaymentGatewayRouter = Depends(get_payment_gateway),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Mark an order paid, for local development.

    The route is off unless a deployment turns it on, and it is bound to the
    caller and to the order that caller owns. It is the only route that can
    mark an order paid without a provider, so it must not be reachable by
    an anonymous caller or by one customer on another's order.
    """
    settings = get_settings()
    if not settings.testing_endpoints_enabled or settings.env == "production":
        raise NotFound("Not found")
    if gateway.provider != "fake":
        raise Conflict("The configured payment provider is not the fake gateway")

    order = session.scalar(
        select(Order).where(Order.id == body.order_id, Order.customer_id == user.id)
    )
    if order is None:
        raise NotFound("Order not found")
    payment = session.scalar(select(Payment).where(Payment.order_id == order.id))
    if payment is None:
        raise NotFound("Payment not found")

    payload = {
        "event": "order.paid",
        "payload": {
            "payment": {
                "id": f"pay_fake_{order.id}",
                "order_id": payment.provider_order_id,
                "amount": order.price_paise,
                "currency": "INR",
            }
        },
    }
    raw_body = json.dumps(payload).encode()
    outcome = payment_service.handle_webhook(
        session,
        raw_body=raw_body,
        signature=gateway.sign(raw_body),
        event_id=f"evt_fake_{order.id}",
        gateway=gateway,
    )
    return {"status": outcome}
