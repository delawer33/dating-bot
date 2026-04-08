import asyncio
import logging
import signal

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage

from bot.config import settings
from bot.handlers import registration, start
from bot.transport.adapter import build_transport

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    storage = RedisStorage.from_url(settings.redis_url)
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=storage)

    dp.include_router(start.router)
    dp.include_router(registration.router)

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
