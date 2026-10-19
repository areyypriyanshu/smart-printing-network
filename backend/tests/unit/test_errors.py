from app.errors import error_body
from app.logging import request_id_var


def test_error_body_has_code_message_details_and_request_id() -> None:
    # The request id lives in a context variable. Set it and put it back,
    # or every later test in this process sees this request id.
    token = request_id_var.set("req-1")
    try:
        body = error_body("NOT_FOUND", "Order not found", {"order_id": "abc"})
    finally:
        request_id_var.reset(token)

    assert body == {
        "error": {
            "code": "NOT_FOUND",
            "message": "Order not found",
            "details": {"order_id": "abc"},
            "request_id": "req-1",
        }
    }
