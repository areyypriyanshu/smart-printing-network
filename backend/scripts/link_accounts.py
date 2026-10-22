"""Give the local accounts an identity in the provider, and link them.

The local authentication is gone. An account that existed before the
provider did has no identity in it, and a person with no identity
cannot sign in: the provider does not know them, and the application
has no password to check.

This creates the missing identity for each of those accounts and
records the provider's identifier on the local row. The address stays
the one the account already had, so the orders and the shops that
belong to it stay theirs.

The password for each account is made here and printed once. It is not
stored anywhere: the provider holds it, and the person changes it.

Usage:
    python scripts/link_accounts.py            # report what would happen
    python scripts/link_accounts.py --apply    # do it
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.error
import urllib.request

from app.db import SessionLocal
from app.models import User
from sqlalchemy import select

CLERK_API = "https://api.clerk.com/v1"
# The provider's API is behind a bot protection that refuses a request
# with no user agent of its own, and the one the standard library sends
# by default is refused.
USER_AGENT = "SmartPrintingNetwork/0.1"


def call(secret_key: str, path: str, body: dict | None = None) -> dict:
    """Ask the provider something."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{CLERK_API}{path}",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {secret_key}",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def find_by_email(secret_key: str, email: str) -> dict | None:
    """The provider's record for an address, if it has one."""
    users = call(secret_key, f"/users?email_address={email}")
    for user in users:
        for address in user.get("email_addresses", []):
            if address.get("email_address", "").lower() == email.lower():
                return user
    return None


def create(secret_key: str, email: str, name: str, password: str) -> dict:
    """Make the provider's record for an address."""
    return call(
        secret_key,
        "/users",
        {
            "email_address": [email],
            "password": password,
            "first_name": name.split(" ")[0],
            "last_name": " ".join(name.split(" ")[1:]) or name,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="do it, rather than only reporting what would be done",
    )
    parser.add_argument(
        "--test-addresses",
        action="store_true",
        help=(
            "make the provider's address a test one, with clerk_test in it. "
            "A test address never receives mail and its code is always the "
            "same, so an account whose address is not a real inbox can be "
            "signed in to. The local account keeps the address it had."
        ),
    )
    arguments = parser.parse_args()

    secret_key = os.environ.get("CLERK_SECRET_KEY", "")
    if not secret_key:
        print("CLERK_SECRET_KEY is not set", file=sys.stderr)
        return 1

    made: list[tuple[str, str, str, str]] = []
    with SessionLocal() as session:
        accounts = session.scalars(select(User).where(User.clerk_user_id.is_(None)))
        for account in list(accounts):
            existing = find_by_email(secret_key, account.email)
            if existing is not None:
                # The provider already knows this address, so the
                # identity exists and only the link is missing.
                print(f"would link {account.email} to {existing['id']} (it already existed)")
                if not arguments.apply:
                    continue
                account.clerk_user_id = existing["id"]
                session.commit()
                print("  linked")
                continue
            if not arguments.apply:
                print(f"would create an identity for {account.email}")
                continue
            password = f"SPN-{secrets.token_urlsafe(18)}"
            address = account.email
            if arguments.test_addresses:
                local, _, domain = address.partition("@")
                address = f"{local}+clerk_test@{domain}"
            person = create(secret_key, address, account.full_name, password)
            account.clerk_user_id = person["id"]
            session.commit()
            made.append((account.email, address, password, person["id"]))
            print(f"  created {person['id']} for {address}")

    if made:
        print("\nthe passwords, once:")
        for email, address, password, identifier in made:
            print(f"  {email}")
            print(f"    sign in as: {address}")
            print(f"    password: {password}")
            print(f"    identifier: {identifier}")
        if not arguments.apply:
            print("\nnothing was changed: run it again with --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
