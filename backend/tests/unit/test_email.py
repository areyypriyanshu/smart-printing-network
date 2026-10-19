import pytest
from app.schemas.email import Email
from pydantic import BaseModel, ValidationError


class Model(BaseModel):
    email: Email


ACCEPTED = [
    "customer@example.com",
    "vendor1@example.com",
    "someone@sub.example.co.uk",
    "a.b+c@example.test",
    "someone@foo.invalid",
    "x@y.z",
]

REJECTED = [
    "",
    "not-an-email",
    "a@b",
    "a b@example.com",
    "a@@example.com",
    "a@example..com",
    "@example.com",
    "a@.com",
    "a@example.com ",
]


@pytest.mark.parametrize("address", ACCEPTED)
def test_a_plausible_address_is_accepted(address: str) -> None:
    assert Model(email=address).email == address


@pytest.mark.parametrize("address", REJECTED)
def test_a_malformed_address_is_rejected(address: str) -> None:
    with pytest.raises(ValidationError):
        Model(email=address)


def test_an_address_longer_than_254_characters_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Model(email=f"{'a' * 250}@example.com")


def test_the_published_schema_says_email() -> None:
    schema = Model.model_json_schema()

    assert schema["properties"]["email"]["format"] == "email"
    assert schema["properties"]["email"]["type"] == "string"
