import logging

import httpx
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import api_client
from bot.handlers.registration import prompt_for_step
from bot.resilience import ApiUnavailableError

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def handle_start(
    message: Message,
    state: FSMContext,
    command: CommandObject,
) -> None:
    try:
        result = await api_client.registration_start(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            referral_code=command.args,
        )
    except ApiUnavailableError:
        await message.answer("Сервис временно недоступен. Попробуйте через несколько секунд.")
        return
    except httpx.HTTPStatusError as exc:
        logger.error("API error on /start: %s", exc)
        await message.answer("Ошибка сервиса. Попробуйте позже.")
        return

    if result["is_complete"]:
        await state.clear()
        await message.answer("Вы уже зарегистрированы! Используйте /menu для навигации.")
        return

    await prompt_for_step(message, state, result["registration_step"])
