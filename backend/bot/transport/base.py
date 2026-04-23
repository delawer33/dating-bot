from abc import ABC, abstractmethod

from aiogram import Bot, Dispatcher


class TransportAdapter(ABC):
    @abstractmethod
    async def start(self, bot: Bot, dispatcher: Dispatcher) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...
