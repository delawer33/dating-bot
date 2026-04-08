import logging
from datetime import date

import httpx
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from dateutil import parser as dateutil_parser

from bot import api_client
from bot.keyboards import GENDER_KEYBOARD, LOCATION_KEYBOARD
from bot.resilience import ApiUnavailableError
from bot.states import RegistrationStates

logger = logging.getLogger(__name__)
router = Router()

_STEP_MESSAGES = {
    "display_name": "Как вас зовут? (имя, которое увидят другие пользователи)",
    "birth_date": "Введите дату рождения в формате ГГГГ-ММ-ДД (например, 1990-01-15).",
    "gender": "Укажите ваш пол:",
    "location": "Поделитесь геолокацией, чтобы мы могли находить людей рядом с вами.",
}

# Maps API step name → aiogram FSM state
_STEP_TO_STATE = {
    "display_name": RegistrationStates.waiting_display_name,
    "birth_date": RegistrationStates.waiting_birth_date,
    "gender": RegistrationStates.waiting_gender,
    "location": RegistrationStates.waiting_location,
}


async def prompt_for_step(message: Message, state: FSMContext, step: str) -> None:
    if step == "complete":
        await state.clear()
        await message.answer(
            "Регистрация завершена! Добро пожаловать в dating-бот. 🎉",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    fsm_state = _STEP_TO_STATE.get(step)
    if fsm_state is None:
        logger.error("Unknown registration step: %s", step)
        return

    await state.set_state(fsm_state)

    if step == "gender":
        await message.answer(_STEP_MESSAGES[step], reply_markup=GENDER_KEYBOARD)
    elif step == "location":
        await message.answer(_STEP_MESSAGES[step], reply_markup=LOCATION_KEYBOARD)
    else:
        await message.answer(_STEP_MESSAGES[step], reply_markup=ReplyKeyboardRemove())


@router.message(RegistrationStates.waiting_display_name, F.text)
async def handle_display_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Имя не может быть пустым. Попробуйте ещё раз.")
        return

    try:
        result = await api_client.set_display_name(message.from_user.id, name)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _handle_api_error(message, exc)
        return

    await prompt_for_step(message, state, result["registration_step"])


@router.message(RegistrationStates.waiting_birth_date, F.text)
async def handle_birth_date(message: Message, state: FSMContext) -> None:
    parsed = _parse_date((message.text or "").strip())
    if parsed is None:
        await message.answer(
            "Неверный формат даты. Используйте ГГГГ-ММ-ДД (например, 1990-01-15)."
        )
        return

    try:
        result = await api_client.set_birth_date(message.from_user.id, parsed)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _handle_api_error(message, exc)
        return

    await prompt_for_step(message, state, result["registration_step"])


@router.callback_query(RegistrationStates.waiting_gender, F.data.startswith("gender:"))
async def handle_gender(callback: CallbackQuery, state: FSMContext) -> None:
    gender = callback.data.split(":", 1)[1]
    await callback.answer()

    try:
        result = await api_client.set_gender(callback.from_user.id, gender)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        if callback.message:
            await _handle_api_error(callback.message, exc)
        return

    if callback.message:
        await prompt_for_step(callback.message, state, result["registration_step"])


@router.message(RegistrationStates.waiting_location, F.location)
async def handle_location(message: Message, state: FSMContext) -> None:
    loc = message.location
    if loc is None:
        await message.answer("Пожалуйста, используйте кнопку для отправки геолокации.")
        return

    await message.answer("Получили координаты, определяем город…", reply_markup=ReplyKeyboardRemove())

    try:
        result = await api_client.set_location(
            message.from_user.id, loc.latitude, loc.longitude
        )
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _handle_api_error(message, exc)
        return

    if result["registration_step"] == "complete":
        try:
            result = await api_client.complete_registration(message.from_user.id)
        except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
            await _handle_api_error(message, exc)
            return

    await prompt_for_step(message, state, result["registration_step"])


@router.message(RegistrationStates.waiting_location)
async def handle_location_wrong_type(message: Message) -> None:
    await message.answer("Пожалуйста, используйте кнопку «Поделиться геолокацией».")


def _parse_date(raw: str) -> date | None:
    try:
        return dateutil_parser.parse(raw, dayfirst=False).date()
    except (ValueError, OverflowError):
        return None


async def _handle_api_error(
    message: Message, exc: ApiUnavailableError | httpx.HTTPStatusError
) -> None:
    if isinstance(exc, ApiUnavailableError):
        await message.answer(
            "Сервис временно недоступен. Попробуйте через несколько секунд."
        )
        return

    try:
        detail = exc.response.json().get("detail", str(exc))
    except Exception:
        detail = str(exc)
    await message.answer(f"Ошибка: {detail}")
