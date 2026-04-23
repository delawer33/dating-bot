from bot.transport.base import TransportAdapter
from bot.transport.polling import PollingAdapter
from bot.transport.webhook import WebhookAdapter


def build_transport(transport: str, **kwargs) -> TransportAdapter:
    match transport:
        case "polling":
            return PollingAdapter()
        case "webhook":
            return WebhookAdapter(**kwargs)
        case _:
            raise ValueError(
                f"Unknown transport: '{transport}'. Use 'polling' or 'webhook'."
            )
