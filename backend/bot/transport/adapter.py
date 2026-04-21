from abc import ABC, abstractmethod

from aiogram import Bot, Dispatcher

from bot.transport.polling import PollingAdapter
from bot.transport.webhook import WebhookAdapter

class TransportAdapter(ABC):
    @abstractmethod
    async def start(self, bot: Bot, dispatcher: Dispatcher) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...


def build_transport(transport: str, **kwargs) -> TransportAdapter:
    match transport:
        case "polling":
            return PollingAdapter()
        case "webhook":
            return WebhookAdapter(**kwargs)
        case _:
            raise ValueError(f"Unknown transport: '{transport}'. Use 'polling' or 'webhook'.")
