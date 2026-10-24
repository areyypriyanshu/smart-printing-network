import pytest
from app.domain.origin import normalize_origin, origin_allowed


def test_origin_normalizes_scheme_host_and_default_port() -> None:
    assert normalize_origin("HTTPS://Example.COM:443") == "https://example.com"
    assert normalize_origin("http://example.com:80") == "http://example.com"
    assert normalize_origin("https://example.com:444") == "https://example.com:444"
    assert normalize_origin("https://example.com/") == "https://example.com"


def test_punycode_origin_is_accepted_but_raw_unicode_is_rejected() -> None:
    punycode = "https://xn--bcher-kva.example"
    assert origin_allowed(punycode, [punycode])
    assert not origin_allowed("https://bücher.example", [punycode])
    assert not origin_allowed(punycode, ["https://bücher.example"])


@pytest.mark.parametrize(
    "origin",
    [
        "https://example.com.evil.test",
        "https://example.com/path",
        "https://user:password@example.com",
        "https://example.com:bad",
        "https://example.com:444",
        "null",
        "not-a-url",
        "https://exa mple.com",
        "https://example.com%2Fevil.test",
        "https://example.com?x=1",
        "https://example.com#fragment",
    ],
)
def test_lookalike_and_malformed_origins_are_refused(origin: str) -> None:
    assert not origin_allowed(origin, ["https://example.com"])


def test_origin_allowlist_uses_exact_normalized_origins() -> None:
    assert origin_allowed("HTTPS://EXAMPLE.COM:443", ["https://example.com"])
    assert not origin_allowed("https://example.com", ["http://example.com"])
    assert not origin_allowed("https://example.com", [])
    assert not origin_allowed("https://example.com", "not-a-list")
