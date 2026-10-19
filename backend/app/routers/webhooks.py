import json

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_payment_gateway
from app.errors import Conflict, NotFound, ValidationError
from app.gateways.payments import PaymentGateway, PaymentGatewayRouter
from app.models import Order, Payment
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
    event_id: str = Header(default="", alias="X-Razorpay-Event-Id"),
    session: Session = Depends(get_db),
    gateway: PaymentGateway = Depends(get_payment_gateway),
) -> dict[str, str]:
    if event_id == "":
        raise ValidationError("Missing X-Razorpay-Event-Id header")
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
) -> dict[str, str]:
    if get_settings().env == "production":
        raise NotFound("Not found")
    if gateway.provider != "fake":
        raise Conflict("The configured payment provider is not the fake gateway")

    order = session.get(Order, body.order_id)
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
