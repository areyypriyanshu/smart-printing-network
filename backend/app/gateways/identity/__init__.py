"""The seam between the application and whoever proves who someone is."""

from app.gateways.identity.base import TokenVerifier, VerifiedIdentity
from app.gateways.identity.clerk import ClerkTokenVerifier, JwksCache
from app.gateways.identity.clerk_admin import ClerkAdminClient, ClerkAdminError, ClerkUser
from app.gateways.identity.fake import FakeIdentityReader, FakeTokenVerifier, dev_subject_for

__all__ = [
    "ClerkAdminClient",
    "ClerkAdminError",
    "ClerkTokenVerifier",
    "ClerkUser",
    "FakeIdentityReader",
    "FakeTokenVerifier",
    "dev_subject_for",
    "JwksCache",
    "TokenVerifier",
    "VerifiedIdentity",
]
