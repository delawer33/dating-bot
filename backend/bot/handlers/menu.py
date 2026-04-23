"""Main reply-keyboard menu: browse, own profile, search preferences."""

from __future__ import annotations

import html
import logging

import httpx
from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import api_client
from bot.handlers.discovery import answer_incoming_likes, send_next_discovery_card
from bot.handlers.registration import prompt_for_step
from bot.keyboards import (
    BTN_BROWSE,
    BTN_INCOMING_LIKES,
    BTN_MY_PROFILE,
    BTN_REFERRAL,
    BTN_SEARCH_PREFS,
    MAIN_MENU_KEYBOARD,
    PROFILE_MENU_KEYBOARD,
    SEARCH_PREFS_MENU_KEYBOARD,
)
from bot.resilience import ApiUnavailableError
from bot.states import RegistrationStates, SettingsStates

logger = logging.getLogger(__name__)
router = Router()


async def answer_referral_card(message: Message) -> None:
    try:
        data = await api_client.registration_referral(message.from_user.id)
    except ApiUnavailableError:
        await message.answer("Сервис временно недоступен. Попробуйте через несколько секунд.")
        return
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            await message.answer("Сначала нажмите /start.")
        else:
            logger.error("registration/referral failed: %s", exc)
            await message.answer("Не удалось получить код. Попробуйте позже.")
        return

    code = str(data.get("referral_code") or "")
    if not code:
        await message.answer("Код временно недоступен. Попробуйте позже.")
        return
    code_e = html.escape(code, quote=False)
    link = data.get("invite_link")
    if isinstance(link, str) and link.strip():
        link_e = html.escape(link.strip(), quote=True)
        text = (
            "🎁 <b>Ваш код приглашения</b>\n\n"
            f"<code>{code_e}</code>\n\n"
            f'<a href="{link_e}">Открыть бота с вашим кодом</a>\n\n'
            "<i>Когда друг завершит регистрацию, вам начисляется бонус к рейтингу.</i>"
        )
        await message.answer(text, parse_mode="HTML")
        return

    text = (
        "🎁 <b>Ваш код приглашения</b>\n\n"
        f"<code>{code_e}</code>\n\n"
        "Пусть друг откроет бота и отправит одним сообщением:\n"
        f"<code>/start {code_e}</code>"
    )
    await message.answer(text, parse_mode="HTML")


def _format_preferences_text(prefs: dict | None) -> str:
    if not prefs:
        return "Параметры поиска ещё не заданы. Завершите регистрацию."
    lines: list[str] = ["Параметры поиска:"]
    if prefs.get("age_min") is not None and prefs.get("age_max") is not None:
        lines.append(f"Возраст: {prefs['age_min']}–{prefs['age_max']} лет")
    gp = prefs.get("gender_preferences")
    if gp:
        lines.append("Пол в анкетах: " + ", ".join(gp))
    else:
        lines.append("Пол в анкетах: не ограничен")
    md = prefs.get("max_distance_km")
    if md is not None:
        lines.append(f"Макс. расстояние: {md} км")
    else:
        lines.append("Макс. расстояние: не задано")
    return "\n".join(lines)


async def _fetch_profile_me(telegram_id: int) -> dict:
    return await api_client.profile_me(telegram_id)


async def _ensure_complete_or_prompt(
    message: Message, state: FSMContext, data: dict
) -> bool:
    if data.get("is_complete"):
        return True
    step = data.get("registration_step", "display_name")
    await prompt_for_step(message, state, step)
    return False


@router.message(Command("referral"))
async def cmd_referral(message: Message) -> None:
    await answer_referral_card(message)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await message.answer(
        "👋 Выберите действие в меню ниже.",
        reply_markup=MAIN_MENU_KEYBOARD,
    )


@router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except ApiUnavailableError:
        await message.answer("Сервис временно недоступен. Попробуйте через несколько секунд.")
        return
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            await message.answer("Сначала нажмите /start.")
        else:
            logger.error("profile/me failed: %s", exc)
            await message.answer("Ошибка сервиса. Попробуйте позже.")
        return

    if not await _ensure_complete_or_prompt(message, state, data):
        return

    await message.answer(
        "Раздел «Мой профиль». Выберите действие:",
        reply_markup=PROFILE_MENU_KEYBOARD,
    )


@router.message(
    F.text == BTN_BROWSE,
    ~StateFilter(RegistrationStates),
    ~StateFilter(SettingsStates),
)
async def menu_browse(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except ApiUnavailableError:
        await message.answer("Сервис временно недоступен. Попробуйте через несколько секунд.")
        return
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            await message.answer("Сначала нажмите /start.")
        else:
            logger.error("profile/me failed: %s", exc)
            await message.answer("Ошибка сервиса. Попробуйте позже.")
        return

    if not await _ensure_complete_or_prompt(message, state, data):
        return

    await message.answer("🔍 Ищем для вас следующую анкету…")
    await send_next_discovery_card(message)


@router.message(
    F.text == BTN_INCOMING_LIKES,
    ~StateFilter(RegistrationStates),
    ~StateFilter(SettingsStates),
)
async def menu_incoming_likes(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except ApiUnavailableError:
        await message.answer("Сервис временно недоступен. Попробуйте через несколько секунд.")
        return
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            await message.answer("Сначала нажмите /start.")
        else:
            logger.error("profile/me failed: %s", exc)
            await message.answer("Ошибка сервиса. Попробуйте позже.")
        return

    if not await _ensure_complete_or_prompt(message, state, data):
        return

    await answer_incoming_likes(message)


@router.message(
    F.text == BTN_REFERRAL,
    ~StateFilter(RegistrationStates),
    ~StateFilter(SettingsStates),
)
async def menu_referral(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except ApiUnavailableError:
        await message.answer("Сервис временно недоступен. Попробуйте через несколько секунд.")
        return
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            await message.answer("Сначала нажмите /start.")
        else:
            logger.error("profile/me failed: %s", exc)
            await message.answer("Ошибка сервиса. Попробуйте позже.")
        return

    if not await _ensure_complete_or_prompt(message, state, data):
        return

    await answer_referral_card(message)


@router.message(F.text == BTN_MY_PROFILE, ~StateFilter(RegistrationStates))
async def menu_my_profile(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except ApiUnavailableError:
        await message.answer("Сервис временно недоступен. Попробуйте через несколько секунд.")
        return
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            await message.answer("Сначала нажмите /start.")
        else:
            logger.error("profile/me failed: %s", exc)
            await message.answer("Ошибка сервиса. Попробуйте позже.")
        return

    if not await _ensure_complete_or_prompt(message, state, data):
        return

    await message.answer(
        "Раздел «Мой профиль». Выберите действие:",
        reply_markup=PROFILE_MENU_KEYBOARD,
    )


@router.message(F.text == BTN_SEARCH_PREFS, ~StateFilter(RegistrationStates))
async def menu_search_prefs(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except ApiUnavailableError:
        await message.answer("Сервис временно недоступен. Попробуйте через несколько секунд.")
        return
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            await message.answer("Сначала нажмите /start.")
        else:
            logger.error("profile/me failed: %s", exc)
            await message.answer("Ошибка сервиса. Попробуйте позже.")
        return

    if not await _ensure_complete_or_prompt(message, state, data):
        return

    await message.answer(_format_preferences_text(data.get("preferences")))
    await message.answer(
        "Изменить параметры поиска:",
        reply_markup=SEARCH_PREFS_MENU_KEYBOARD,
    )
