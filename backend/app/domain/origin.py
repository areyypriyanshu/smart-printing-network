"""Small, shared origin parser for browser-facing authentication checks."""

from urllib.parse import urlsplit


def normalize_origin(value: str) -> str | None:
    """Return a canonical HTTP(S) origin, or None for an invalid origin.

    Only an origin (scheme, host and effective port) is accepted; paths,
    credentials, query strings and lookalike suffixes are not. Raw non-ASCII
    values are rejected rather than normalized through a library-specific
    IDNA policy. ASCII/punycode is the canonical deployment form.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        value.strip().encode("ascii")
        parts = urlsplit(value.strip())
        scheme = parts.scheme.lower()
        if scheme not in {"http", "https"} or not parts.hostname:
            return None
        if parts.username is not None or parts.password is not None:
            return None
        if parts.path not in {"", "/"} or parts.query or parts.fragment:
            return None
        host = parts.hostname.lower().rstrip(".")
        if not host or "%" in host:
            return None
        port = parts.port
        default_port = 443 if scheme == "https" else 80
        port = default_port if port is None else port
        if not 1 <= port <= 65535:
            return None
        rendered_host = f"[{host}]" if ":" in host else host
        suffix = "" if port == default_port else f":{port}"
        return f"{scheme}://{rendered_host}{suffix}"
    except (ValueError, UnicodeError):
        return None


def origin_allowed(origin: str, allowed_origins: object) -> bool:
    """Compare exact normalized origins, never host or suffix patterns."""
    if not isinstance(allowed_origins, (list, tuple, set, frozenset)):
        return False
    allowed = {
        normalized
        for item in allowed_origins
        if isinstance(item, str) and (normalized := normalize_origin(item)) is not None
    }
    normalized_origin = normalize_origin(origin)
    return normalized_origin is not None and normalized_origin in allowed
