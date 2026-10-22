"""The script that gives the old accounts an identity in the provider.

An account that existed before the provider did has no identity in it,
and a person with no identity cannot sign in. The script makes the
missing identity and records the provider's identifier on the local
row.

The two rules it works by are here: the address it looks for is the
one the account already had, and the address it makes is the provider's
own, which is not always the same one.
"""

# The name is changed on the way in, because pytest collects anything
# whose name begins with test_.
from scripts.link_accounts import matches
from scripts.link_accounts import test_address as the_test_address


def test_an_address_is_matched_whatever_its_case() -> None:
    """The provider's list is by address, but the case is the caller's."""
    user = {
        "id": "user_1",
        "email_addresses": [{"email_address": "Vendor1@Example.com"}],
    }

    assert matches(user, "vendor1@example.com")
    assert matches(user, "VENDOR1@EXAMPLE.COM")
    assert not matches(user, "vendor2@example.com")


def test_an_account_with_no_addresses_matches_nothing() -> None:
    """The provider's record always has one, but the script is careful."""
    assert not matches({"id": "user_1", "email_addresses": []}, "a@example.com")
    assert not matches({"id": "user_1"}, "a@example.com")


def test_a_test_address_keeps_the_address_it_had() -> None:
    """The local account keeps the address it had.

    The orders and the shops belong to the local account, and the
    address on it is what they are tied to. The provider's address is
    only where the sign in happens, and a test address is the one
    whose code is always the same.
    """
    assert the_test_address("vendor1@example.com") == "vendor1+clerk_test@example.com"
    assert the_test_address("a.b+c@example.co.uk") == "a.b+c+clerk_test@example.co.uk"
