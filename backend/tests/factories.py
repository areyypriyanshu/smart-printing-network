import uuid
from datetime import UTC, datetime, timedelta

from app.gateways.identity.fake import dev_subject_for
from app.gateways.payments import CashGateway, FakeGateway, GatewayOrder, GatewayRefund
from app.models import Order, Shop, ShopRate, Upload, User
from app.schemas.order import OrderCreateRequest
from app.services import order_service
from fastapi.testclient import TestClient
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.orm import Session

# The key the fake gateway signs its webhooks with in the test suite.
# The fake gateway takes no default on purpose: a key that lives in the
# application package is a key that ships in the repository. The test
# secret lives here, with the other test-only values.
FAKE_WEBHOOK_SECRET = "test-only-fake-webhook-secret"


class RecordingGateway:
    """A payment gateway double that records what it was asked to do.

    `refund_error` makes the refund call fail, which is how the retry and
    backoff behaviour is tested.
    """

    provider = "fake"
    checkout_key_id: str | None = None

    def __init__(self, *, refund_error: Exception | None = None) -> None:
        self.refund_error = refund_error
        self.refund_calls: list[dict[str, object]] = []

    def create_order(
        self, *, amount_paise: int, receipt: str, currency: str = "INR"
    ) -> GatewayOrder:
        return GatewayOrder(
            provider=self.provider,
            provider_order_id=f"fake_order_{receipt}",
            amount_paise=amount_paise,
            currency=currency,
        )

    def verify_webhook_signature(self, *, raw_body: bytes, signature: str) -> bool:
        return True

    def refund(
        self, *, provider_payment_id: str, amount_paise: int, idempotency_note: str
    ) -> GatewayRefund:
        self.refund_calls.append(
            {
                "provider_payment_id": provider_payment_id,
                "amount_paise": amount_paise,
                "idempotency_note": idempotency_note,
            }
        )
        if self.refund_error is not None:
            raise self.refund_error
        return GatewayRefund(
            provider=self.provider,
            refund_id=f"refund_{idempotency_note}",
            provider_payment_id=provider_payment_id,
            amount_paise=amount_paise,
        )


def create_user(
    session: Session,
    *,
    email: str = "user@example.com",
    role: str = "customer",
    full_name: str = "Test User",
    is_active: bool = True,
) -> User:
    """An account to test with.

    The account carries the identifier the identity provider would
    give the person, so that the tests find it by the same route the
    application does. The identifier is a local one, because the test
    suite does not talk to a provider.
    """
    user = User(
        email=email,
        clerk_user_id=dev_subject_for(email),
        full_name=full_name,
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.commit()
    return user


def identity_headers(client: TestClient, subject: str) -> dict[str, str]:
    """The headers for a caller who has signed in but has no account yet.

    The identity provider knows the person, and the application has not
    made an account for them, which is the state a person is in between
    signing in and saying what they are here for.
    """
    verifier = client.app.state.token_verifier
    return {"Authorization": f"Bearer {verifier.issue(subject)}"}


def create_shop(
    session: Session,
    *,
    owner: User,
    name: str = "Test Shop",
    address: str = "1 Test Street",
    latitude: float = 22.5726,
    longitude: float = 88.3639,
    min_order_paise: int = 0,
    is_verified: bool = True,
    accepting_orders: bool = True,
) -> Shop:
    shop = Shop(
        owner_id=owner.id,
        name=name,
        address=address,
        location=WKTElement(f"POINT({longitude} {latitude})", srid=4326),
        min_order_paise=min_order_paise,
        is_verified=is_verified,
        accepting_orders=accepting_orders,
    )
    session.add(shop)
    session.commit()
    return shop


def create_full_rate_table(
    session: Session, shop: Shop, *, base_paise: int = 200
) -> list[ShopRate]:
    prices = {
        ("A4", False, False): base_paise,
        ("A4", False, True): base_paise + 100,
        ("A4", True, False): base_paise * 4,
        ("A4", True, True): base_paise * 4 + 200,
        ("A3", False, False): base_paise + 100,
        ("A3", False, True): base_paise + 200,
        ("A3", True, False): base_paise * 6,
        ("A3", True, True): base_paise * 6 + 300,
    }
    rates = [
        ShopRate(
            shop_id=shop.id,
            paper_size=paper_size,
            color=color,
            duplex=duplex,
            rate_paise=rate_paise,
        )
        for (paper_size, color, duplex), rate_paise in prices.items()
    ]
    session.add_all(rates)
    session.commit()
    return rates


def create_upload_row(
    session: Session,
    *,
    customer: User,
    page_count: int = 1,
    size_bytes: int = 1024,
) -> Upload:
    upload = Upload(
        customer_id=customer.id,
        file_key=f"uploads/{uuid.uuid4().hex}.pdf",
        original_filename="fixture.pdf",
        size_bytes=size_bytes,
        sha256="0" * 64,
        page_count=page_count,
        delete_after=datetime.now(UTC) + timedelta(hours=24),
    )
    session.add(upload)
    session.commit()
    return upload


def login_headers(client: TestClient, email: str, password: str | None = None) -> dict[str, str]:
    """The headers that sign a caller in as the account with this address.

    The password is accepted and ignored. There is no password any
    more: the identity provider holds it, and the application never
    sees it. The argument is still here because the callers have it,
    and removing it would be a change to every test that signs in
    rather than to the thing being tested.
    """
    session: Session = client.app.state.db_session
    user = session.scalar(select(User).where(User.email == email))
    assert user is not None, f"there is no account with the address {email}"
    assert user.clerk_user_id is not None
    verifier = client.app.state.token_verifier
    return {"Authorization": f"Bearer {verifier.issue(user.clerk_user_id)}"}


def create_unpaid_order(
    session: Session,
    *,
    customer: User,
    shop: Shop,
    page_count: int = 1,
    copies: int = 1,
) -> Order:
    """An order that is created but not paid, waiting for its payment window."""
    upload = create_upload_row(session, customer=customer, page_count=page_count)
    order, _payment = order_service.create_order(
        session,
        customer_id=customer.id,
        request=OrderCreateRequest(
            upload_id=upload.id,
            shop_id=shop.id,
            paper_size="A4",
            color=False,
            duplex=False,
            copies=copies,
        ),
        idempotency_key=uuid.uuid4().hex,
        gateway=FakeGateway(webhook_secret=FAKE_WEBHOOK_SECRET),
    )
    return order


def create_paid_order(
    session: Session,
    *,
    customer: User,
    shop: Shop,
    page_count: int = 1,
    copies: int = 1,
    paper_size: str = "A4",
    color: bool = False,
    duplex: bool = False,
) -> Order:
    """An order that a shop can see: created, then paid through the webhook path.

    Goes through the real service so the order, its payment, its pickup code
    and its event history look exactly like a paid order in production.
    """
    upload = create_upload_row(session, customer=customer, page_count=page_count)
    order, payment = order_service.create_order(
        session,
        customer_id=customer.id,
        request=OrderCreateRequest(
            upload_id=upload.id,
            shop_id=shop.id,
            paper_size=paper_size,
            color=color,
            duplex=duplex,
            copies=copies,
        ),
        idempotency_key=uuid.uuid4().hex,
        gateway=FakeGateway(webhook_secret=FAKE_WEBHOOK_SECRET),
    )
    order_service.transition(session, order_id=order.id, to_status="PAID", actor_type="webhook")
    # The webhook is what captures the payment, so the factory does too.
    # Without this the order would be paid but hold no money, and a refund
    # would have nothing to refund.
    payment.status = "CAPTURED"
    payment.provider_payment_id = f"pay_test_{payment.id}"
    session.commit()
    session.refresh(order)
    return order


def create_reserved_order(
    session: Session,
    *,
    customer: User,
    shop: Shop,
    reserved_at: datetime | None = None,
    page_count: int = 1,
    copies: int = 1,
) -> Order:
    """A cash order: booked, waiting for the shop, money due at the counter.

    Goes through the real service, so the order, its payment, its pickup
    code and its event history look exactly like a cash order in
    production.
    """
    upload = create_upload_row(session, customer=customer, page_count=page_count)
    order, _payment = order_service.create_order(
        session,
        customer_id=customer.id,
        request=OrderCreateRequest(
            upload_id=upload.id,
            shop_id=shop.id,
            paper_size="A4",
            color=False,
            duplex=False,
            copies=copies,
            payment_method="at_store",
        ),
        idempotency_key=uuid.uuid4().hex,
        gateway=CashGateway(),
        now=reserved_at,
    )
    session.refresh(order)
    return order
