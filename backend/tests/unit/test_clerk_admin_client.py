"""Reading a person from the identity provider's own API.

The application needs the address and the name, and the provider is
where they are. These tests are about the request that reads them and
about what the provider's answer is turned into.
"""

from app.gateways.identity.clerk_admin import (
    USER_AGENT,
    build_get_user_request,
    parse_user,
)


def test_the_request_names_the_application() -> None:
    """The provider's API refuses a request with no agent of its own.

    The one the standard library sends by default is refused, and the
    refusal is a bot protection rather than a rule, so the answer is
    to say who is asking.
    """
    request = build_get_user_request(secret_key="sk_test_a_key", user_id="user_abc")

    assert request.headers["User-Agent"] == USER_AGENT
    assert request.headers["Authorization"] == "Bearer sk_test_a_key"
    assert request.url.endswith("/users/user_abc")


def test_the_secret_is_not_in_the_body() -> None:
    """A body can be logged. A header is not in the body."""
    request = build_get_user_request(secret_key="sk_test_a_key", user_id="user_abc")

    assert b"sk_test_a_key" not in request.body


def test_the_person_is_read_from_the_answer() -> None:
    document = {
        "id": "user_abc",
        "first_name": "SPN",
        "last_name": "Check",
        "primary_email_address_id": "idn_2",
        "email_addresses": [
            {
                "id": "idn_1",
                "email_address": "other@example.com",
                "verification": {"status": "unverified"},
            },
            {
                "id": "idn_2",
                "email_address": "primary@example.com",
                "verification": {"status": "verified"},
            },
        ],
    }

    person = parse_user(document)

    assert person.id == "user_abc"
    assert person.email == "primary@example.com"
    assert person.full_name == "SPN Check"
    assert person.email_verified is True


def test_a_person_with_no_name_gets_the_address_as_the_name() -> None:
    document = {
        "id": "user_abc",
        "primary_email_address_id": "idn_1",
        "email_addresses": [
            {
                "id": "idn_1",
                "email_address": "primary@example.com",
                "verification": {"status": "verified"},
            }
        ],
    }

    person = parse_user(document)

    assert person.full_name == "primary@example.com"


def test_a_provider_that_does_not_know_the_person_is_its_own_error() -> None:
    """A person who is not there is not the provider being down.

    The two are different answers and the caller is told different
    things: one says the account was removed, and the other says to try
    again in a moment.
    """
    import urllib.error

    from app.gateways.identity.clerk_admin import (
        ClerkAdminClient,
        ClerkAdminError,
        ClerkUserNotFound,
    )

    def not_found(*args: object, **kwargs: object) -> None:
        raise urllib.error.HTTPError(
            "https://api.clerk.com/v1/users/user_x", 404, "Not Found", {}, None
        )

    client = ClerkAdminClient(secret_key="sk_test_a_key")
    original = urllib.request.urlopen
    urllib.request.urlopen = not_found  # type: ignore[assignment]
    try:
        try:
            client.get_user("user_x")
        except ClerkUserNotFound:
            return
        raise AssertionError("a person the provider does not know should be an error")
    finally:
        urllib.request.urlopen = original  # type: ignore[assignment]
    assert ClerkAdminError is not None


def test_a_person_with_no_address_is_an_error() -> None:
    """The address is what the order is tied to, so there has to be one."""
    from app.gateways.identity.clerk_admin import ClerkAdminError

    try:
        parse_user({"id": "user_abc", "email_addresses": []})
    except ClerkAdminError:
        return
    raise AssertionError("a person with no address should not be read")
