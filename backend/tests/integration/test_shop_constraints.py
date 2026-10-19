"""The rules the database holds, even when the application is wrong.

A check constraint is the last line of defence. These tests write rows
that break the rules and show that the database refuses them.
"""

import uuid

import pytest
from app.models import Shop, Upload
from geoalchemy2.elements import WKTElement
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests.factories import create_user


def _shop(session: Session, phone: str | None) -> Shop:
    owner = create_user(session, email=f"owner-{uuid.uuid4().hex}@example.com", role="vendor")
    shop = Shop(
        owner_id=owner.id,
        name="Constraint Shop",
        address="1 Test Street",
        location=WKTElement("POINT(88.3639 22.5726)", srid=4326),
        phone=phone,
        min_order_paise=0,
        is_verified=True,
        accepting_orders=True,
    )
    session.add(shop)
    return shop


def _upload(session: Session, source_format: str | None) -> Upload:
    customer = create_user(session, email=f"user-{uuid.uuid4().hex}@example.com")
    upload = Upload(
        customer_id=customer.id,
        file_key=f"uploads/{uuid.uuid4().hex}.pdf",
        original_filename="file.pdf",
        size_bytes=10,
        sha256="0" * 64,
        page_count=1,
        source_format=source_format,
    )
    session.add(upload)
    return upload


def test_a_shop_phone_may_be_absent(db_session: Session) -> None:
    _shop(db_session, None)
    db_session.commit()

    assert db_session.query(Shop).one().phone is None


def test_a_shop_phone_may_have_spaces_and_a_plus(db_session: Session) -> None:
    _shop(db_session, "+91 98300 00000")
    db_session.commit()

    assert db_session.query(Shop).one().phone == "+91 98300 00000"


def test_a_shop_phone_with_too_few_digits_is_refused(db_session: Session) -> None:
    _shop(db_session, "12345")

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_a_shop_phone_with_too_many_digits_is_refused(db_session: Session) -> None:
    _shop(db_session, "1234567890123456")

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_a_shop_phone_with_letters_is_refused(db_session: Session) -> None:
    _shop(db_session, "call the shop")

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
