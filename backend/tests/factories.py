import uuid
from datetime import UTC, datetime, timedelta

from app import security
from app.gateways.payments import FakeGateway
from app.models import Order, Shop, ShopRate, Upload, User
from app.schemas.order import OrderCreateRequest
from app.services import order_service
from fastapi.testclient import TestClient
from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session

DEFAULT_PASSWORD = "password-123"


def create_user(
    session: Session,
    *,
    email: str = "user@example.com",
    password: str = DEFAULT_PASSWORD,
    role: str = "customer",
    full_name: str = "Test User",
    is_active: bool = True,
) -> User:
    user = User(
        email=email,
        password_hash=security.hash_password(password),
        full_name=full_name,
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.commit()
    return user


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


def login_headers(
    client: TestClient, email: str, password: str = DEFAULT_PASSWORD
) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


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
        gateway=FakeGateway(),
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
