"""The admin panel: the verification queue, the moderation actions and the log.

The admin is the person who decides which shops are allowed to take
orders. The tests here cover three things: that only an admin can reach
these endpoints, that an approval or a suspension changes the shop the
way it should, and that every decision leaves a record.
"""

import uuid

from app.models import AdminAction
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import (
    create_full_rate_table,
    create_paid_order,
    create_shop,
    create_user,
    login_headers,
)


def _admin(session: Session) -> object:
    return create_user(session, email="admin@example.com", role="admin")


def _admin_headers(client: TestClient, session: Session) -> dict[str, str]:
    _admin(session)
    return login_headers(client, "admin@example.com")


def test_an_admin_sees_the_shops_waiting_for_a_decision(
    client: TestClient, db_session: Session
) -> None:
    owner = create_user(db_session, email="shop@example.com", role="vendor")
    create_shop(db_session, owner=owner, name="Pending Shop", is_verified=False)
    headers = _admin_headers(client, db_session)

    response = client.get("/api/v1/admin/shops?status=pending", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["name"] for item in body["items"]] == ["Pending Shop"]
    assert body["items"][0]["owner_email"] == "shop@example.com"
    assert body["items"][0]["is_verified"] is False


def test_a_verified_shop_is_not_in_the_pending_list(
    client: TestClient, db_session: Session
) -> None:
    owner = create_user(db_session, email="shop@example.com", role="vendor")
    create_shop(db_session, owner=owner, name="Live Shop", is_verified=True)
    headers = _admin_headers(client, db_session)

    response = client.get("/api/v1/admin/shops?status=pending", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["items"] == []


def test_a_customer_cannot_reach_the_admin_endpoints(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="customer@example.com", role="customer")
    headers = login_headers(client, "customer@example.com")

    response = client.get("/api/v1/admin/shops", headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_a_vendor_cannot_reach_the_admin_endpoints(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="vendor@example.com", role="vendor")
    headers = login_headers(client, "vendor@example.com")

    response = client.get("/api/v1/admin/shops", headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_an_anonymous_caller_is_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/admin/shops")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_an_admin_approves_a_shop(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="shop@example.com", role="vendor")
    shop = create_shop(db_session, owner=owner, name="Pending Shop", is_verified=False)
    headers = _admin_headers(client, db_session)

    response = client.post(f"/api/v1/admin/shops/{shop.id}/approve", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_verified"] is True
    assert body["accepting_orders"] is True
    db_session.refresh(shop)
    assert shop.is_verified is True
    assert shop.accepting_orders is True


def test_approving_a_shop_writes_an_admin_action(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="shop@example.com", role="vendor")
    shop = create_shop(db_session, owner=owner, is_verified=False)
    headers = _admin_headers(client, db_session)

    client.post(f"/api/v1/admin/shops/{shop.id}/approve", headers=headers)

    action = db_session.scalar(select(AdminAction))
    assert action is not None
    assert action.action == "shop_approved"
    assert action.shop_id == shop.id
    assert action.admin_id is not None


def test_a_customer_cannot_approve_a_shop(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="shop@example.com", role="vendor")
    shop = create_shop(db_session, owner=owner, is_verified=False)
    create_user(db_session, email="customer@example.com", role="customer")
    headers = login_headers(client, "customer@example.com")

    response = client.post(f"/api/v1/admin/shops/{shop.id}/approve", headers=headers)

    assert response.status_code == 403
    db_session.refresh(shop)
    assert shop.is_verified is False


def test_a_vendor_cannot_approve_a_shop(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="shop@example.com", role="vendor")
    shop = create_shop(db_session, owner=owner, is_verified=False)
    headers = login_headers(client, "shop@example.com")

    response = client.post(f"/api/v1/admin/shops/{shop.id}/approve", headers=headers)

    assert response.status_code == 403
    db_session.refresh(shop)
    assert shop.is_verified is False


def test_approving_an_unknown_shop_is_not_found(client: TestClient, db_session: Session) -> None:
    headers = _admin_headers(client, db_session)

    response = client.post(f"/api/v1/admin/shops/{uuid.uuid4()}/approve", headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_approving_a_shop_that_is_already_approved_is_a_conflict(
    client: TestClient, db_session: Session
) -> None:
    owner = create_user(db_session, email="shop@example.com", role="vendor")
    shop = create_shop(db_session, owner=owner, is_verified=True)
    headers = _admin_headers(client, db_session)

    response = client.post(f"/api/v1/admin/shops/{shop.id}/approve", headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SHOP_ALREADY_VERIFIED"


def test_an_admin_suspends_a_shop(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="shop@example.com", role="vendor")
    shop = create_shop(db_session, owner=owner, is_verified=True)
    headers = _admin_headers(client, db_session)

    response = client.post(
        f"/api/v1/admin/shops/{shop.id}/suspend",
        json={"reason": "The owner could not be reached at the address."},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_verified"] is False
    assert body["accepting_orders"] is False


def test_suspending_a_shop_records_the_reason(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="shop@example.com", role="vendor")
    shop = create_shop(db_session, owner=owner, is_verified=True)
    headers = _admin_headers(client, db_session)

    client.post(
        f"/api/v1/admin/shops/{shop.id}/suspend",
        json={"reason": "Repeated no-shows on confirmed orders."},
        headers=headers,
    )

    action = db_session.scalar(select(AdminAction))
    assert action is not None
    assert action.action == "shop_suspended"
    assert action.reason == "Repeated no-shows on confirmed orders."


def test_suspending_a_shop_needs_a_reason(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="shop@example.com", role="vendor")
    shop = create_shop(db_session, owner=owner, is_verified=True)
    headers = _admin_headers(client, db_session)

    response = client.post(f"/api/v1/admin/shops/{shop.id}/suspend", json={}, headers=headers)

    assert response.status_code == 422


def test_suspending_a_shop_that_is_not_verified_is_a_conflict(
    client: TestClient, db_session: Session
) -> None:
    owner = create_user(db_session, email="shop@example.com", role="vendor")
    shop = create_shop(db_session, owner=owner, is_verified=False)
    headers = _admin_headers(client, db_session)

    response = client.post(
        f"/api/v1/admin/shops/{shop.id}/suspend",
        json={"reason": "Not needed."},
        headers=headers,
    )

    assert response.status_code == 409


def test_suspending_a_shop_leaves_its_orders_alone(client: TestClient, db_session: Session) -> None:
    """A customer who already paid is owed a printout.

    Taking the shop off the market must not strand that customer. The
    shop stops getting new orders; the order it already accepted stays
    exactly where it is.
    """
    owner = create_user(db_session, email="shop@example.com", role="vendor")
    shop = create_shop(db_session, owner=owner, is_verified=True)
    create_full_rate_table(db_session, shop)
    customer = create_user(db_session, email="customer@example.com", role="customer")
    order = create_paid_order(db_session, customer=customer, shop=shop)
    headers = _admin_headers(client, db_session)

    response = client.post(
        f"/api/v1/admin/shops/{shop.id}/suspend",
        json={"reason": "Under review."},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    db_session.refresh(order)
    assert order.status == "PAID"
    assert order.pickup_code is not None


def test_a_suspended_shop_disappears_from_the_customer_shop_list(
    client: TestClient, db_session: Session
) -> None:
    owner = create_user(db_session, email="shop@example.com", role="vendor")
    shop = create_shop(db_session, owner=owner, name="Live Shop", is_verified=True)
    create_user(db_session, email="customer@example.com", role="customer")
    headers = login_headers(client, "customer@example.com")
    assert shop.id is not None

    client.post(
        f"/api/v1/admin/shops/{shop.id}/suspend",
        json={"reason": "Under review."},
        headers=_admin_headers(client, db_session),
    )

    response = client.get("/api/v1/shops", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["items"] == []


def test_the_action_log_lists_the_decisions_newest_first(
    client: TestClient, db_session: Session
) -> None:
    owner = create_user(db_session, email="shop@example.com", role="vendor")
    shop = create_shop(db_session, owner=owner, is_verified=False)
    headers = _admin_headers(client, db_session)

    client.post(f"/api/v1/admin/shops/{shop.id}/approve", headers=headers)
    client.post(
        f"/api/v1/admin/shops/{shop.id}/suspend",
        json={"reason": "Under review."},
        headers=headers,
    )

    response = client.get("/api/v1/admin/actions", headers=headers)

    assert response.status_code == 200, response.text
    actions = response.json()["items"]
    assert [item["action"] for item in actions] == ["shop_suspended", "shop_approved"]
    assert actions[0]["shop_name"] == "Test Shop"
    assert actions[0]["admin_email"] == "admin@example.com"


def test_a_customer_cannot_read_the_action_log(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="customer@example.com", role="customer")
    headers = login_headers(client, "customer@example.com")

    response = client.get("/api/v1/admin/actions", headers=headers)

    assert response.status_code == 403


def test_an_unknown_status_filter_is_rejected(client: TestClient, db_session: Session) -> None:
    headers = _admin_headers(client, db_session)

    response = client.get("/api/v1/admin/shops?status=nonsense", headers=headers)

    assert response.status_code == 422
