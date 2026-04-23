import logging

import httpx
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import api_client
from bot.handlers.registration import prompt_for_step
from bot.keyboards import MAIN_MENU_KEYBOARD
from bot.resilience import ApiUnavailableError

logger = logging.getLogger(__name__)
router = Router()

HELP_TEXT = (
    "📖 <b>Команды</b>\n\n"
    "/browse — лента анкет (❤️ лайк, ⏭ пропуск)\n"
    "/likes — кто вас лайкнул (ответьте тем же)\n"
    "/likes_history — полный список лайков текстом\n"
    "/profile — мой профиль и фото\n"
    "/referral — ваш код приглашения для друзей\n"
    "/menu — кнопки главного меню\n\n"
    "Удобнее пользоваться кнопками внизу экрана после /start."
)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")


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
        await message.answer(
            "✨ С возвращением! Меню ниже — или /browse для ленты, /likes для входящих. "
            "Справка: /help",
            reply_markup=MAIN_MENU_KEYBOARD,
        )
        return

    await prompt_for_step(message, state, result["registration_step"])
