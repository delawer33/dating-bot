"""
Telegram validates X-Telegram-Bot-Api-Secret-Token on every update when
secret_token is set — always configure it in production.
"""
import asyncio
import logging

from aiohttp import web
from aiohttp.web_runner import AppRunner, TCPSite
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from bot.transport.adapter import TransportAdapter

logger = logging.getLogger(__name__)


class WebhookAdapter(TransportAdapter):
    def __init__(
        self,
        webhook_url: str,
        port: int = 8443,
        secret_token: str | None = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._port = port
        self._secret_token = secret_token
        self._runner: AppRunner | None = None

    async def start(self, bot: Bot, dispatcher: Dispatcher) -> None:
        logger.info("Registering Telegram webhook → %s", self._webhook_url)
        await bot.set_webhook(
            url=self._webhook_url,
            secret_token=self._secret_token,
            drop_pending_updates=True,
        )

        app = web.Application()
        handler = SimpleRequestHandler(
            dispatcher=dispatcher,
            bot=bot,
            secret_token=self._secret_token,
        )
        # /webhook path must match the path component of WEBHOOK_URL
        handler.register(app, path="/webhook")
        setup_application(app, dispatcher, bot=bot)

        self._runner = AppRunner(app)
        await self._runner.setup()
        site = TCPSite(self._runner, host="0.0.0.0", port=self._port)
        await site.start()
        logger.info("Webhook server listening on port %d", self._port)

        await asyncio.Event().wait()

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
        logger.info("Webhook server stopped")
