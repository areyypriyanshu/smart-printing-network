"""The constraints on orders, tested against the real database.

The two constraints that changed for this feature became conditional on
the payment method rather than being removed. A conditional constraint is
easy to get wrong in a way that quietly stops protecting anything, so
each side of each condition is tested here: what must be refused, and
what must still be allowed.

These tests insert rows directly with SQL, because the point is what the
database accepts, not what the service produces.
"""

import uuid
from datetime import UTC, datetime

import pytest
from app.models import Upload
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests.factories import create_full_rate_table, create_shop, create_user

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def ids(db_session: Session) -> dict[str, uuid.UUID]:
    """A customer, a shop and an upload to hang an order off."""
    customer = create_user(db_session, email="constraints@example.com")
    vendor = create_user(db_session, email="constraints-vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor)
    create_full_rate_table(db_session, shop)
    upload = Upload(
        customer_id=customer.id,
        file_key=f"uploads/constraints-{uuid.uuid4().hex}.pdf",
        original_filename="constraints.pdf",
        size_bytes=100,
        sha256="0" * 64,
        page_count=1,
    )
    db_session.add(upload)
    db_session.commit()
    return {
        "customer": customer.id,
        "shop": shop.id,
        "upload": upload.id,
    }


def _insert_order(
    db_session: Session,
    ids: dict[str, uuid.UUID],
    *,
    status: str,
    payment_method: str = "online",
    paid_at: str | None = None,
    pickup_code: str | None = None,
) -> uuid.UUID:
    """Insert an order that the service would not produce."""
    order_id = uuid.uuid4()
    db_session.execute(
        text(
            """
            INSERT INTO orders (
                id, customer_id, shop_id, upload_id, status, payment_method,
                paper_size, color, duplex, copies, page_count, rate_paise,
                min_order_paise, price_paise, pickup_code, idempotency_key,
                paid_at, reserved_at
            ) VALUES (
                :id, :customer_id, :shop_id, :upload_id, :status, :payment_method,
                'A4', false, false, 1, 1, 200, 0, 200, :pickup_code, :idempotency_key,
                :paid_at, :reserved_at
            )
            """
        ),
        {
            "id": order_id,
            "customer_id": ids["customer"],
            "shop_id": ids["shop"],
            "upload_id": ids["upload"],
            "status": status,
            "payment_method": payment_method,
            "pickup_code": pickup_code,
            "idempotency_key": uuid.uuid4().hex,
            "paid_at": paid_at,
            "reserved_at": NOW.isoformat(),
        },
    )
    return order_id


def test_an_online_order_that_is_paid_without_a_paid_at_is_refused(
    db_session: Session, ids: dict[str, uuid.UUID]
) -> None:
    with pytest.raises(IntegrityError):
        _insert_order(
            db_session,
            ids,
            status="PAID",
            payment_method="online",
            paid_at=None,
            pickup_code="123456",
        )
    db_session.rollback()


def test_an_online_order_that_is_paid_without_a_pickup_code_is_refused(
    db_session: Session, ids: dict[str, uuid.UUID]
) -> None:
    with pytest.raises(IntegrityError):
        _insert_order(
            db_session,
            ids,
            status="PAID",
            payment_method="online",
            paid_at=NOW.isoformat(),
            pickup_code=None,
        )
    db_session.rollback()


def test_an_online_order_that_is_rejected_without_being_paid_is_refused(
    db_session: Session, ids: dict[str, uuid.UUID]
) -> None:
    with pytest.raises(IntegrityError):
        _insert_order(
            db_session,
            ids,
            status="REJECTED",
            payment_method="online",
            paid_at=None,
            pickup_code=None,
        )
    db_session.rollback()


def test_a_cash_order_that_is_accepted_without_a_paid_at_is_allowed(
    db_session: Session, ids: dict[str, uuid.UUID]
) -> None:
    """The money has not changed hands yet, so there is no paid_at."""
    _insert_order(
        db_session,
        ids,
        status="ACCEPTED",
        payment_method="at_store",
        paid_at=None,
        pickup_code="123456",
    )
    db_session.commit()


def test_a_cash_order_that_is_collected_without_a_paid_at_is_refused(
    db_session: Session, ids: dict[str, uuid.UUID]
) -> None:
    """Collected means the money changed hands, so it has to be recorded."""
    with pytest.raises(IntegrityError):
        _insert_order(
            db_session,
            ids,
            status="COLLECTED",
            payment_method="at_store",
            paid_at=None,
            pickup_code="123456",
        )
    db_session.rollback()


def test_a_cash_order_without_a_pickup_code_is_refused(
    db_session: Session, ids: dict[str, uuid.UUID]
) -> None:
    """The code is what the customer shows, so it has to exist."""
    with pytest.raises(IntegrityError):
        _insert_order(
            db_session,
            ids,
            status="RESERVED",
            payment_method="at_store",
            paid_at=None,
            pickup_code=None,
        )
    db_session.rollback()


def test_a_cash_order_that_is_rejected_without_being_paid_is_allowed(
    db_session: Session, ids: dict[str, uuid.UUID]
) -> None:
    """A cash order can be turned down without any money being taken."""
    _insert_order(
        db_session,
        ids,
        status="REJECTED",
        payment_method="at_store",
        paid_at=None,
        pickup_code="123456",
    )
    db_session.commit()


def test_an_unknown_payment_method_is_refused(
    db_session: Session, ids: dict[str, uuid.UUID]
) -> None:
    with pytest.raises(IntegrityError):
        _insert_order(
            db_session,
            ids,
            status="PENDING_PAYMENT",
            payment_method="cheque",
            paid_at=None,
            pickup_code=None,
        )
    db_session.rollback()


def test_an_unknown_status_is_refused(db_session: Session, ids: dict[str, uuid.UUID]) -> None:
    with pytest.raises(IntegrityError):
        _insert_order(
            db_session,
            ids,
            status="MAYBE",
            payment_method="online",
            paid_at=None,
            pickup_code=None,
        )
    db_session.rollback()


def test_a_cash_payment_cannot_be_queued_for_a_refund(
    db_session: Session, ids: dict[str, uuid.UUID]
) -> None:
    """There is no money in a cash order to give back."""
    order_id = _insert_order(
        db_session,
        ids,
        status="RESERVED",
        payment_method="at_store",
        paid_at=None,
        pickup_code="123456",
    )
    db_session.commit()
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                """
                INSERT INTO payments (
                    id, order_id, provider, provider_order_id, amount_paise,
                    currency, status
                ) VALUES (
                    :id, :order_id, 'cash', :provider_order_id, 200, 'INR',
                    'REFUND_PENDING'
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "order_id": order_id,
                "provider_order_id": f"cash_order_{uuid.uuid4().hex}",
            },
        )
    db_session.rollback()


def test_a_cash_payment_may_be_captured(db_session: Session, ids: dict[str, uuid.UUID]) -> None:
    order_id = _insert_order(
        db_session,
        ids,
        status="RESERVED",
        payment_method="at_store",
        paid_at=None,
        pickup_code="123456",
    )
    db_session.commit()
    db_session.execute(
        text(
            """
            INSERT INTO payments (
                id, order_id, provider, provider_order_id, amount_paise,
                currency, status, provider_payment_id
            ) VALUES (
                :id, :order_id, 'cash', :provider_order_id, 200, 'INR',
                'CAPTURED', :provider_payment_id
            )
            """
        ),
        {
            "id": uuid.uuid4(),
            "order_id": order_id,
            "provider_order_id": f"cash_order_{uuid.uuid4().hex}",
            "provider_payment_id": f"cash_payment_{uuid.uuid4().hex}",
        },
    )
    db_session.commit()
