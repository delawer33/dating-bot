"""Unit tests for the transport adapter factory."""
import pytest

from bot.transport.adapter import build_transport
from bot.transport.polling import PollingAdapter
from bot.transport.webhook import WebhookAdapter


def test_build_polling_adapter() -> None:
    adapter = build_transport("polling")
    assert isinstance(adapter, PollingAdapter)


def test_build_webhook_adapter() -> None:
    adapter = build_transport(
        "webhook",
        webhook_url="https://example.com/webhook",
        port=8443,
        secret_token="secret",
    )
    assert isinstance(adapter, WebhookAdapter)
    assert adapter._webhook_url == "https://example.com/webhook"
    assert adapter._port == 8443


def test_build_unknown_transport_raises() -> None:
    with pytest.raises(ValueError, match="Unknown transport"):
        build_transport("grpc")
