"""The SMTP adapter, tested against a local SMTP server.

No real mail is sent. The small local server records the message handed
to it, so the test proves SMTP formatting and delivery without a new
mail dependency.
"""

import socketserver
from threading import Thread

from app.gateways.email.smtp import SmtpEmailSender


class _SMTPHandler(socketserver.StreamRequestHandler):
    messages: list[tuple[str, str, bytes]] = []

    def handle(self) -> None:
        self.wfile.write(b"220 local test server\r\n")
        sender = ""
        recipient = ""
        data = b""
        while True:
            line = self.rfile.readline()
            command = line.decode(errors="replace").rstrip("\r\n")
            upper = command.upper()
            if upper.startswith("EHLO") or upper.startswith("HELO"):
                self.wfile.write(b"250-localhost\r\n250 OK\r\n")
            elif upper.startswith("MAIL FROM:"):
                sender = command[10:].strip("<>")
                self.wfile.write(b"250 OK\r\n")
            elif upper.startswith("RCPT TO:"):
                recipient = command[8:].strip("<>")
                self.wfile.write(b"250 OK\r\n")
            elif upper == "DATA":
                self.wfile.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                chunks: list[bytes] = []
                while True:
                    part = self.rfile.readline()
                    if part == b".\r\n":
                        break
                    chunks.append(part)
                data = b"".join(chunks)
                self.wfile.write(b"250 OK\r\n")
            elif upper == "QUIT":
                self.wfile.write(b"221 Bye\r\n")
                break
            else:
                self.wfile.write(b"250 OK\r\n")
        self.messages.append((sender, recipient, data))


class _SMTPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def test_smtp_sender_delivers_a_plain_text_message() -> None:
    server = _SMTPServer(("127.0.0.1", 0), _SMTPHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        sender = SmtpEmailSender(
            host="127.0.0.1",
            port=port,
            username="",
            password="",
            sender="no-reply@example.com",
        )
        sender.send(to="customer@example.com", subject="Confirm", body="the link")
        assert len(_SMTPHandler.messages) == 1
        from_address, recipient, body = _SMTPHandler.messages[0]
        assert from_address == "no-reply@example.com"
        assert recipient == "customer@example.com"
        assert b"Subject: Confirm" in body
        assert b"the link" in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
