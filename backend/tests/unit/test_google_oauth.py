"""The real Google adapter, tested against a local HTTP server.

The URL builder is pure and the fake provider covers the application
flow. These tests cover the adapter's network contract without using
Google, credentials or the public internet.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.parse import parse_qs

from app.gateways.oauth.google import GoogleOAuthProvider


class _Handler(BaseHTTPRequestHandler):
    token_body: dict[str, list[str]] = {}
    profile = {"sub": "google-1", "email": "person@example.com", "email_verified": True}

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers["Content-Length"])
        _Handler.token_body = parse_qs(self.rfile.read(length).decode())
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"access_token": "access-token"}).encode())

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(self.profile).encode())

    def log_message(self, format: str, *args: object) -> None:
        return


def test_google_adapter_exchanges_code_and_reads_profile(monkeypatch) -> None:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        import app.gateways.oauth.google as module

        monkeypatch.setattr(
            module, "TOKEN_ENDPOINT", f"http://127.0.0.1:{server.server_port}/token"
        )
        monkeypatch.setattr(
            module, "USERINFO_ENDPOINT", f"http://127.0.0.1:{server.server_port}/userinfo"
        )
        provider = GoogleOAuthProvider(client_id="client", client_secret="secret")

        profile = provider.exchange(
            code="code", code_verifier="verifier", redirect_uri="http://localhost/callback"
        )

        assert profile.subject == "google-1"
        assert profile.email == "person@example.com"
        assert profile.email_verified is True
        assert _Handler.token_body["code"] == ["code"]
        assert _Handler.token_body["code_verifier"] == ["verifier"]
        assert _Handler.token_body["client_secret"] == ["secret"]
    finally:
        server.shutdown()
        thread.join(timeout=2)
