import json
import logging

from app.logging import JsonFormatter, get_request_id, request_id_var


def _record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_the_formatter_writes_the_standard_fields() -> None:
    line = JsonFormatter().format(_record())

    payload = json.loads(line)
    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test"
    assert "timestamp" in payload


def test_extra_fields_are_kept() -> None:
    line = JsonFormatter().format(_record(job="expire_orders", order_id="abc"))

    payload = json.loads(line)
    assert payload["job"] == "expire_orders"
    assert payload["order_id"] == "abc"


def test_the_request_id_is_kept_when_there_is_one() -> None:
    token = request_id_var.set("req-123")
    try:
        payload = json.loads(JsonFormatter().format(_record()))
    finally:
        request_id_var.reset(token)

    assert payload["request_id"] == "req-123"


def test_there_is_no_request_id_outside_a_request() -> None:
    assert get_request_id() == ""
    payload = json.loads(JsonFormatter().format(_record()))
    assert "request_id" not in payload


def test_a_value_that_is_not_json_is_still_written() -> None:
    line = JsonFormatter().format(_record(thing=object()))

    payload = json.loads(line)
    assert "thing" in payload
