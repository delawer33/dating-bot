import logging

from aiogram import Bot, Dispatcher

from bot.transport.adapter import TransportAdapter

logger = logging.getLogger(__name__)


class PollingAdapter(TransportAdapter):
    async def start(self, bot: Bot, dispatcher: Dispatcher) -> None:
        logger.info("Starting bot in POLLING mode")
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot, handle_signals=False)

    async def stop(self) -> None:
        pass
