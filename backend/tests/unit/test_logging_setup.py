"""Tests for ``shared.logging_setup``."""

import json
import logging

import pytest

from shared.logging_setup import (
    JsonLogFormatter,
    configure_logging,
    get_request_id,
    reset_request_id,
    sanitize_incoming_request_id,
    set_request_id,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("  ", None),
        ("a" * 129, None),
        ("bad id", None),
        ("req-abc-01", "req-abc-01"),
        ("ABC_xyz-9.1", "ABC_xyz-9.1"),
    ],
)
def test_sanitize_incoming_request_id(raw: str | None, expected: str | None) -> None:
    assert sanitize_incoming_request_id(raw) == expected


def test_request_id_contextvar() -> None:
    assert get_request_id() is None
    t = set_request_id("trace-1")
    try:
        assert get_request_id() == "trace-1"
    finally:
        reset_request_id(t)
    assert get_request_id() is None


def test_configure_logging_json_line() -> None:
    try:
        configure_logging(service="test", log_level="INFO", json_logs=True)
        root = logging.getLogger()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        record.service = "test"  # type: ignore[attr-defined]
        record.request_id = "r1"  # type: ignore[attr-defined]
        line = root.handlers[0].formatter.format(record)  # type: ignore[union-attr]
        data = json.loads(line)
        assert data["service"] == "test"
        assert data["request_id"] == "r1"
        assert data["message"] == "hello"
    finally:
        configure_logging(service="test", log_level="WARNING", json_logs=False)
