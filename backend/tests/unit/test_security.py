import uuid

import pytest
from app import security
from app.errors import Unauthenticated


def test_password_hash_is_argon2id_and_verifies() -> None:
    hashed = security.hash_password("correct horse battery staple")

    assert hashed.startswith("$argon2id$")
    assert security.verify_password("correct horse battery staple", hashed) is True
    assert security.verify_password("wrong password", hashed) is False


def test_verify_password_rejects_garbage_hash() -> None:
    assert security.verify_password("anything", "not-a-real-hash") is False


def test_access_token_roundtrip() -> None:
    user_id = uuid.uuid4()

    token = security.create_access_token(user_id, "customer")

    assert security.decode_access_token(token) == (user_id, "customer")


def test_tampered_access_token_is_rejected() -> None:
    token = security.create_access_token(uuid.uuid4(), "vendor")

    with pytest.raises(Unauthenticated):
        security.decode_access_token(token + "tampered")
