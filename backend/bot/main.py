import asyncio
import logging
import signal

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand

from bot import api_client
from bot.config import settings
from bot.handlers import discovery, menu, registration, start
from bot.handlers import settings as settings_handlers
from bot.transport.adapter import build_transport

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


async def _configure_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Запуск и главное меню"),
            BotCommand(command="help", description="Справка по командам"),
            BotCommand(command="browse", description="Лента анкет — лайк / пропуск"),
            BotCommand(command="likes", description="Входящие лайки (до 10)"),
            BotCommand(command="likes_history", description="История входящих лайков"),
            BotCommand(command="menu", description="Открыть меню кнопок"),
            BotCommand(command="profile", description="Мой профиль и фото"),
            BotCommand(command="referral", description="Реферальный код и ссылка"),
        ]
    )


async def main() -> None:
    await api_client.init_api_http()
    storage = RedisStorage.from_url(settings.redis_url)
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=storage)
    await _configure_bot_commands(bot)

    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(settings_handlers.router)
    dp.include_router(registration.router)
    dp.include_router(discovery.router)

    transport = build_transport(
        settings.bot_transport,
        webhook_url=settings.webhook_url,
        port=settings.webhook_port,
        secret_token=settings.webhook_secret_token,
    )
    loop = asyncio.get_running_loop()

    async def shutdown() -> None:
        logger.info("Shutting down bot…")
        await transport.stop()
        await bot.session.close()
        await api_client.close_api_http()
        await storage.close()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))

    try:
        await transport.start(bot, dp)
    except asyncio.CancelledError:
        pass
    finally:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())
