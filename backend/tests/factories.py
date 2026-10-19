from app import security
from app.models import Shop, ShopRate, User
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


def login_headers(
    client: TestClient, email: str, password: str = DEFAULT_PASSWORD
) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
