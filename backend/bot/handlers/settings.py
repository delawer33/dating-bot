"""Reply-keyboard settings: profile blocks and search preferences (post-registration)."""

from __future__ import annotations

import logging
import re
import uuid

import httpx
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove
from dateutil import parser as dateutil_parser

from bot import api_client
from bot.config import settings
from bot.handlers.discovery import send_profile_card_media
from bot.handlers.menu import _ensure_complete_or_prompt, _fetch_profile_me, _format_preferences_text
from bot.handlers.registration import _handle_api_error
from bot.keyboards import (
    BTN_BACK_MAIN,
    BTN_BROWSE,
    BTN_CANCEL_EDIT,
    BTN_MY_PROFILE,
    BTN_PREF_AGE,
    BTN_PREF_ALL,
    BTN_PREF_DISTANCE,
    BTN_PREF_GENDER,
    BTN_PREF_MEN,
    BTN_PREF_MW,
    BTN_PREF_SHOW,
    BTN_PREF_WOMEN,
    BTN_SEARCH_PREFS,
    BTN_PROFILE_ADD_PHOTO,
    BTN_PROFILE_BIO,
    BTN_PROFILE_BIRTH,
    BTN_INCOMING_LIKES,
    BTN_PROFILE_DEL_PHOTO,
    BTN_PROFILE_GENDER,
    BTN_PROFILE_INTERESTS,
    BTN_PROFILE_LOCATION,
    BTN_PROFILE_NAME,
    BTN_PROFILE_REORDER_INFO,
    BTN_PROFILE_SHOW,
    GENDER_KEYBOARD,
    MAIN_MENU_KEYBOARD,
    PROFILE_MENU_KEYBOARD,
    SEARCH_GENDER_REPLY,
    SEARCH_PREFS_MENU_KEYBOARD,
    location_reply_with_cancel,
    photo_delete_inline_keyboard,
    photo_reorder_inline_keyboard,
    settings_cancel_reply_keyboard,
    settings_interests_keyboard,
)
from bot.resilience import ApiUnavailableError
from bot.states import RegistrationStates, SettingsStates
from bot.utils.api_errors import format_http_error

logger = logging.getLogger(__name__)
router = Router()

SETTINGS_PARENT = "settings_parent"
PARENT_PROFILE = "profile"
PARENT_PREFS = "prefs"

_SETTINGS_MENU_LABELS: frozenset[str] = frozenset(
    {
        BTN_PROFILE_SHOW,
        BTN_PROFILE_NAME,
        BTN_PROFILE_BIRTH,
        BTN_PROFILE_GENDER,
        BTN_PROFILE_LOCATION,
        BTN_PROFILE_BIO,
        BTN_PROFILE_INTERESTS,
        BTN_PROFILE_ADD_PHOTO,
        BTN_PROFILE_DEL_PHOTO,
        BTN_PROFILE_REORDER_INFO,
        BTN_INCOMING_LIKES,
        BTN_PREF_SHOW,
        BTN_PREF_AGE,
        BTN_PREF_GENDER,
        BTN_PREF_DISTANCE,
        BTN_BROWSE,
        BTN_MY_PROFILE,
        BTN_SEARCH_PREFS,
    }
)


def _parent_keyboard(data: dict) -> ReplyKeyboardMarkup:
    parent = data.get(SETTINGS_PARENT)
    if parent == PARENT_PREFS:
        return SEARCH_PREFS_MENU_KEYBOARD
    if parent == PARENT_PROFILE:
        return PROFILE_MENU_KEYBOARD
    return MAIN_MENU_KEYBOARD


@router.message(StateFilter(SettingsStates), F.text == BTN_CANCEL_EDIT)
async def settings_cancel(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    await message.answer("Отменено.", reply_markup=_parent_keyboard(data))


@router.message(F.text == BTN_BACK_MAIN)
async def back_to_main_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Главное меню:", reply_markup=MAIN_MENU_KEYBOARD)


@router.message(
    F.text == BTN_PROFILE_SHOW,
    ~StateFilter(RegistrationStates),
    ~StateFilter(SettingsStates),
)
async def settings_profile_show(message: Message, state: FSMContext) -> None:
    await state.clear()
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except ApiUnavailableError:
        await message.answer("Сервис временно недоступен. Попробуйте через несколько секунд.")
        return
    except httpx.HTTPStatusError as exc:
        await _maybe_http(message, exc)
        return
    if not await _ensure_complete_or_prompt(message, state, data):
        return
    prof = data.get("profile")
    if not prof:
        await message.answer("Профиль пока пуст.")
        return
    extra = f"\n\nЗаполненность анкеты: {prof.get('completeness_score', 0)}%"
    await send_profile_card_media(message, prof, caption_extra=extra)


@router.message(
    F.text == BTN_PROFILE_NAME,
    ~StateFilter(RegistrationStates),
    ~StateFilter(SettingsStates),
)
async def settings_profile_name_start(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _maybe_http(message, exc)
        return
    if not await _ensure_complete_or_prompt(message, state, data):
        return
    await state.update_data({SETTINGS_PARENT: PARENT_PROFILE})
    await state.set_state(SettingsStates.profile_display_name)
    await message.answer(
        "Новое имя в анкете (текстом):",
        reply_markup=settings_cancel_reply_keyboard(),
    )


@router.message(SettingsStates.profile_display_name, F.text)
async def settings_profile_name_save(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip() == BTN_CANCEL_EDIT:
        await settings_cancel(message, state)
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer("Имя не может быть пустым.")
        return
    try:
        await api_client.profile_set_display_name(message.from_user.id, name)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _handle_api_error(message, exc)
        return
    await state.clear()
    await message.answer("Имя обновлено.", reply_markup=PROFILE_MENU_KEYBOARD)


@router.message(
    F.text == BTN_PROFILE_BIRTH,
    ~StateFilter(RegistrationStates),
    ~StateFilter(SettingsStates),
)
async def settings_profile_birth_start(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _maybe_http(message, exc)
        return
    if not await _ensure_complete_or_prompt(message, state, data):
        return
    await state.update_data({SETTINGS_PARENT: PARENT_PROFILE})
    await state.set_state(SettingsStates.profile_birth_date)
    await message.answer(
        "Дата рождения (ГГГГ-ММ-ДД):",
        reply_markup=settings_cancel_reply_keyboard(),
    )


@router.message(SettingsStates.profile_birth_date, F.text)
async def settings_profile_birth_save(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip() == BTN_CANCEL_EDIT:
        await settings_cancel(message, state)
        return
    raw = (message.text or "").strip()
    try:
        parsed = dateutil_parser.parse(raw, dayfirst=False).date()
    except (ValueError, OverflowError):
        await message.answer("Неверный формат. Используйте ГГГГ-ММ-ДД.")
        return
    try:
        await api_client.profile_set_birth_date(message.from_user.id, parsed)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _handle_api_error(message, exc)
        return
    await state.clear()
    await message.answer("Дата рождения обновлена.", reply_markup=PROFILE_MENU_KEYBOARD)


@router.message(
    F.text == BTN_PROFILE_GENDER,
    ~StateFilter(RegistrationStates),
    ~StateFilter(SettingsStates),
)
async def settings_profile_gender_start(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _maybe_http(message, exc)
        return
    if not await _ensure_complete_or_prompt(message, state, data):
        return
    await state.update_data({SETTINGS_PARENT: PARENT_PROFILE})
    await state.set_state(SettingsStates.profile_gender)
    await message.answer(
        "Можно отменить кнопкой «Отмена» ниже.",
        reply_markup=settings_cancel_reply_keyboard(),
    )
    await message.answer("Ваш пол:", reply_markup=GENDER_KEYBOARD)


@router.callback_query(SettingsStates.profile_gender, F.data.startswith("gender:"))
async def settings_profile_gender_save(callback: CallbackQuery, state: FSMContext) -> None:
    gender = callback.data.split(":", 1)[1]
    await callback.answer()
    if not callback.from_user or not callback.message:
        return
    try:
        await api_client.profile_set_gender(callback.from_user.id, gender)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        if callback.message:
            await _handle_api_error(callback.message, exc)
        return
    await state.clear()
    if callback.message:
        await callback.message.answer("Пол обновлён.", reply_markup=PROFILE_MENU_KEYBOARD)


@router.message(
    F.text == BTN_PROFILE_LOCATION,
    ~StateFilter(RegistrationStates),
    ~StateFilter(SettingsStates),
)
async def settings_profile_location_start(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _maybe_http(message, exc)
        return
    if not await _ensure_complete_or_prompt(message, state, data):
        return
    await state.update_data({SETTINGS_PARENT: PARENT_PROFILE})
    await state.set_state(SettingsStates.profile_location)
    await message.answer(
        "Поделитесь новой геолокацией или нажмите «Отмена».",
        reply_markup=location_reply_with_cancel(),
    )


@router.message(SettingsStates.profile_location, F.location)
async def settings_profile_location_save(message: Message, state: FSMContext) -> None:
    loc = message.location
    if loc is None:
        return
    try:
        await api_client.profile_set_location(
            message.from_user.id, loc.latitude, loc.longitude
        )
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _handle_api_error(message, exc)
        return
    await state.clear()
    await message.answer("Локация обновлена.", reply_markup=PROFILE_MENU_KEYBOARD)


@router.message(
    F.text == BTN_PROFILE_BIO,
    ~StateFilter(RegistrationStates),
    ~StateFilter(SettingsStates),
)
async def settings_profile_bio_start(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _maybe_http(message, exc)
        return
    if not await _ensure_complete_or_prompt(message, state, data):
        return
    await state.update_data({SETTINGS_PARENT: PARENT_PROFILE})
    await state.set_state(SettingsStates.profile_bio)
    await message.answer(
        "Текст «о себе» (одним сообщением):",
        reply_markup=settings_cancel_reply_keyboard(),
    )


@router.message(SettingsStates.profile_bio, F.text)
async def settings_profile_bio_save(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip() == BTN_CANCEL_EDIT:
        await settings_cancel(message, state)
        return
    text = (message.text or "").strip()
    try:
        await api_client.profile_set_bio(message.from_user.id, text)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _handle_api_error(message, exc)
        return
    await state.clear()
    await message.answer("О себе обновлено.", reply_markup=PROFILE_MENU_KEYBOARD)


@router.message(
    F.text == BTN_PROFILE_INTERESTS,
    ~StateFilter(RegistrationStates),
    ~StateFilter(SettingsStates),
)
async def settings_profile_interests_start(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _maybe_http(message, exc)
        return
    if not await _ensure_complete_or_prompt(message, state, data):
        return
    prof = data.get("profile") or {}
    intr = prof.get("interests")
    if isinstance(intr, list):
        selected = frozenset(str(x) for x in intr)
    else:
        selected = frozenset()
    await state.update_data(
        {
            "settings_interests_selected": list(selected),
            SETTINGS_PARENT: PARENT_PROFILE,
        }
    )
    await state.set_state(SettingsStates.profile_interests)
    await message.answer(
        "Нажмите «Отмена» внизу, чтобы выйти без сохранения.",
        reply_markup=settings_cancel_reply_keyboard(),
    )
    await message.answer(
        "Отметьте интересы и нажмите «Сохранить».",
        reply_markup=settings_interests_keyboard(selected),
    )


@router.callback_query(SettingsStates.profile_interests, F.data.startswith("setint:"))
async def settings_interests_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    part = callback.data.split(":", 1)[1]
    if part == "done":
        await callback.answer()
        if not callback.from_user:
            return
        data = await state.get_data()
        selected: list[str] = list(data.get("settings_interests_selected") or [])
        try:
            await api_client.profile_set_interests(callback.from_user.id, selected)
        except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
            if callback.message:
                await _handle_api_error(callback.message, exc)
            return
        await state.clear()
        if callback.message:
            await callback.message.answer(
                "Интересы сохранены.",
                reply_markup=PROFILE_MENU_KEYBOARD,
            )
        return

    await callback.answer()
    iid = part
    data = await state.get_data()
    selected = list(data.get("settings_interests_selected") or [])
    if iid in selected:
        selected = [x for x in selected if x != iid]
    else:
        selected.append(iid)
    await state.update_data(settings_interests_selected=selected)
    await callback.message.edit_reply_markup(
        reply_markup=settings_interests_keyboard(frozenset(selected))
    )


@router.message(
    F.text == BTN_PROFILE_ADD_PHOTO,
    ~StateFilter(RegistrationStates),
    ~StateFilter(SettingsStates),
)
async def settings_profile_add_photo_start(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _maybe_http(message, exc)
        return
    if not await _ensure_complete_or_prompt(message, state, data):
        return
    await state.update_data({SETTINGS_PARENT: PARENT_PROFILE})
    await state.set_state(SettingsStates.profile_add_photo)
    await message.answer(
        "Отправьте фото одним сообщением (как фото, не файлом). Нажмите «Отмена», чтобы выйти.",
        reply_markup=settings_cancel_reply_keyboard(),
    )


@router.message(SettingsStates.profile_add_photo, F.photo)
async def settings_profile_add_photo_save(message: Message, state: FSMContext) -> None:
    if not message.photo:
        return
    fid = message.photo[-1].file_id
    try:
        await api_client.profile_add_photo(message.from_user.id, fid)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _handle_api_error(message, exc)
        return
    await state.clear()
    await message.answer("Фото добавлено.", reply_markup=PROFILE_MENU_KEYBOARD)


@router.message(
    F.text == BTN_PROFILE_DEL_PHOTO,
    ~StateFilter(RegistrationStates),
    ~StateFilter(SettingsStates),
)
async def settings_profile_del_photo_start(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _maybe_http(message, exc)
        return
    if not await _ensure_complete_or_prompt(message, state, data):
        return
    prof = data.get("profile") or {}
    photos = [p for p in (prof.get("photos") or []) if p.get("id")]
    if not photos:
        await message.answer("Нет фото для удаления.", reply_markup=PROFILE_MENU_KEYBOARD)
        return
    await state.update_data({SETTINGS_PARENT: PARENT_PROFILE})
    await state.set_state(SettingsStates.profile_delete_photo)
    await message.answer(
        "Выберите фото для удаления:",
        reply_markup=photo_delete_inline_keyboard(photos),
    )


@router.callback_query(SettingsStates.profile_delete_photo, F.data.startswith("setphdel:"))
async def settings_profile_delete_photo_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data or not callback.from_user or not callback.message:
        await callback.answer()
        return
    part = callback.data.split(":", 1)[1]
    await callback.answer()
    if part == "cancel":
        data = await state.get_data()
        await state.clear()
        await callback.message.answer("Отменено.", reply_markup=_parent_keyboard(data))
        return
    try:
        pid = str(uuid.UUID(part))
    except ValueError:
        await callback.message.answer("Некорректный выбор.")
        return
    try:
        await api_client.profile_delete_photo(callback.from_user.id, pid)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _handle_api_error(callback.message, exc)
        return
    await state.clear()
    await callback.message.answer("Фото удалено.", reply_markup=PROFILE_MENU_KEYBOARD)


@router.message(
    F.text == BTN_PROFILE_REORDER_INFO,
    ~StateFilter(RegistrationStates),
    ~StateFilter(SettingsStates),
)
async def settings_profile_reorder_start(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _maybe_http(message, exc)
        return
    if not await _ensure_complete_or_prompt(message, state, data):
        return
    prof = data.get("profile") or {}
    photos = sorted(
        [p for p in (prof.get("photos") or []) if p.get("id")],
        key=lambda p: int(p.get("sort_order") or 0),
    )
    ids = [str(p["id"]) for p in photos]
    if not ids:
        await message.answer("Нет фото.", reply_markup=PROFILE_MENU_KEYBOARD)
        return
    label_by_id = {pid: i + 1 for i, pid in enumerate(ids)}
    await state.update_data(
        {
            SETTINGS_PARENT: PARENT_PROFILE,
            "photo_reorder_ids": ids,
            "photo_reorder_labels": label_by_id,
        }
    )
    await state.set_state(SettingsStates.profile_reorder_photos)
    await message.answer(
        _reorder_caption(ids, label_by_id),
        reply_markup=photo_reorder_inline_keyboard(ids, label_by_id),
    )


def _photo_reorder_label_map_from_state(data: dict) -> dict[str, int] | None:
    raw = data.get("photo_reorder_labels")
    if not isinstance(raw, dict) or not raw:
        return None
    out: dict[str, int] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError):
            return None
    return out


def _reorder_caption(order_ids: list[str], label_by_id: dict[str, int]) -> str:
    tags = [str(label_by_id[pid]) for pid in order_ids]
    chain = " → ".join(tags)
    lines = [
        "Порядок фото в анкете (слева направо в ленте).",
        f"Сейчас в ленте: {chain}.",
        "Цифра — номер фото (не меняется на этом экране). Строка выше — текущий порядок в ленте. "
        "Стрелки ↑ / ↓ меняют соседей местами. «Готово» — сохранить.",
    ]
    return "\n".join(lines)


@router.callback_query(SettingsStates.profile_reorder_photos, F.data.startswith("setphre:"))
async def settings_profile_reorder_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data or not callback.message or not callback.from_user:
        await callback.answer()
        return
    action = callback.data.split(":", 2)
    if len(action) < 2:
        await callback.answer()
        return
    kind = action[1]
    if kind == "nop":
        await callback.answer()
        return
    data = await state.get_data()
    order: list[str] = list(data.get("photo_reorder_ids") or [])
    if not order:
        await callback.answer("Сессия устарела. Откройте «Порядок фото» снова.", show_alert=True)
        return

    if kind == "cancel":
        await callback.answer()
        await state.clear()
        await callback.message.answer("Отменено.", reply_markup=_parent_keyboard(data))
        return

    if kind == "done":
        await callback.answer()
        try:
            await api_client.profile_reorder_photos(callback.from_user.id, order)
        except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
            await _handle_api_error(callback.message, exc)
            return
        await state.clear()
        await callback.message.answer("Порядок фото обновлён.", reply_markup=PROFILE_MENU_KEYBOARD)
        return

    if len(action) < 3:
        await callback.answer()
        return
    try:
        idx = int(action[2])
    except ValueError:
        await callback.answer()
        return

    label_by_id = _photo_reorder_label_map_from_state(data)
    if label_by_id is None or not all(pid in label_by_id for pid in order):
        await callback.answer("Сессия устарела. Откройте «Порядок фото» снова.", show_alert=True)
        return

    if kind == "u" and 0 < idx < len(order):
        order[idx - 1], order[idx] = order[idx], order[idx - 1]
    elif kind == "d" and 0 <= idx < len(order) - 1:
        order[idx], order[idx + 1] = order[idx + 1], order[idx]
    else:
        await callback.answer()
        return

    await state.update_data(photo_reorder_ids=order)
    await callback.answer()
    try:
        await callback.message.edit_text(
            _reorder_caption(order, label_by_id),
            reply_markup=photo_reorder_inline_keyboard(order, label_by_id),
        )
    except Exception:
        logger.exception("edit reorder message failed")


@router.message(
    F.text == BTN_PREF_SHOW,
    ~StateFilter(RegistrationStates),
    ~StateFilter(SettingsStates),
)
async def settings_prefs_show(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _maybe_http(message, exc)
        return
    if not await _ensure_complete_or_prompt(message, state, data):
        return
    await message.answer(_format_preferences_text(data.get("preferences")))


@router.message(
    F.text == BTN_PREF_AGE,
    ~StateFilter(RegistrationStates),
    ~StateFilter(SettingsStates),
)
async def settings_prefs_age_start(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _maybe_http(message, exc)
        return
    if not await _ensure_complete_or_prompt(message, state, data):
        return
    await state.update_data({SETTINGS_PARENT: PARENT_PREFS})
    await state.set_state(SettingsStates.prefs_age)
    await message.answer(
        "Введите два целых числа через пробел: минимальный и максимальный возраст анкет "
        "(например: 18 35). Диапазон 18–120.",
        reply_markup=settings_cancel_reply_keyboard(),
    )


_INT_TOKEN = re.compile(r"^-?\d+$")


@router.message(SettingsStates.prefs_age, F.text)
async def settings_prefs_age_save(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw == BTN_CANCEL_EDIT:
        await settings_cancel(message, state)
        return
    if raw in _SETTINGS_MENU_LABELS:
        await message.answer(
            "Сначала завершите ввод двух чисел или нажмите «Отмена».",
            reply_markup=settings_cancel_reply_keyboard(),
        )
        return
    parts = raw.replace(",", " ").split()
    if len(parts) != 2 or not _INT_TOKEN.match(parts[0]) or not _INT_TOKEN.match(parts[1]):
        await message.answer(
            "Нужны два целых числа через пробел, например: 18 35",
            reply_markup=settings_cancel_reply_keyboard(),
        )
        return
    a, b = int(parts[0]), int(parts[1])
    lo, hi = min(a, b), max(a, b)
    try:
        await api_client.preferences_set_age(message.from_user.id, lo, hi)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _handle_api_error(message, exc)
        return
    await state.clear()
    await message.answer(
        "Возрастной диапазон обновлён.",
        reply_markup=SEARCH_PREFS_MENU_KEYBOARD,
    )


@router.message(
    F.text == BTN_PREF_GENDER,
    ~StateFilter(RegistrationStates),
    ~StateFilter(SettingsStates),
)
async def settings_prefs_gender_start(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _maybe_http(message, exc)
        return
    if not await _ensure_complete_or_prompt(message, state, data):
        return
    await state.update_data({SETTINGS_PARENT: PARENT_PREFS})
    await state.set_state(SettingsStates.prefs_gender)
    await message.answer(
        "Кого показывать:",
        reply_markup=SEARCH_GENDER_REPLY,
    )


@router.message(SettingsStates.prefs_gender, F.text)
async def settings_prefs_gender_save(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw == BTN_CANCEL_EDIT:
        await settings_cancel(message, state)
        return
    mapping = {
        BTN_PREF_ALL: [],
        BTN_PREF_MEN: ["male"],
        BTN_PREF_WOMEN: ["female"],
        BTN_PREF_MW: ["male", "female"],
    }
    if raw not in mapping:
        await message.answer("Выберите вариант с клавиатуры ниже.")
        return
    try:
        await api_client.preferences_set_gender(message.from_user.id, mapping[raw])
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _handle_api_error(message, exc)
        return
    await state.clear()
    await message.answer(
        "Фильтр по полу обновлён.",
        reply_markup=SEARCH_PREFS_MENU_KEYBOARD,
    )


@router.message(
    F.text == BTN_PREF_DISTANCE,
    ~StateFilter(RegistrationStates),
    ~StateFilter(SettingsStates),
)
async def settings_prefs_distance_start(message: Message, state: FSMContext) -> None:
    try:
        data = await _fetch_profile_me(message.from_user.id)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _maybe_http(message, exc)
        return
    if not await _ensure_complete_or_prompt(message, state, data):
        return
    await state.update_data({SETTINGS_PARENT: PARENT_PREFS})
    await state.set_state(SettingsStates.prefs_distance)
    await message.answer(
        f"Макс. расстояние (км), целое число от 1 до {settings.preferences_max_distance_km}.",
        reply_markup=settings_cancel_reply_keyboard(),
    )


@router.message(SettingsStates.prefs_distance, F.text)
async def settings_prefs_distance_save(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw == BTN_CANCEL_EDIT:
        await settings_cancel(message, state)
        return
    if raw in _SETTINGS_MENU_LABELS:
        await message.answer(
            "Сначала введите число километров или нажмите «Отмена».",
            reply_markup=settings_cancel_reply_keyboard(),
        )
        return
    if not _INT_TOKEN.match(raw):
        await message.answer(
            f"Введите одно целое число от 1 до {settings.preferences_max_distance_km}.",
            reply_markup=settings_cancel_reply_keyboard(),
        )
        return
    km = int(raw)
    try:
        await api_client.preferences_set_distance(message.from_user.id, km)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _handle_api_error(message, exc)
        return
    await state.clear()
    await message.answer(
        "Расстояние обновлено.",
        reply_markup=SEARCH_PREFS_MENU_KEYBOARD,
    )


async def _maybe_http(message: Message, exc: BaseException) -> None:
    if isinstance(exc, ApiUnavailableError):
        await message.answer("Сервис временно недоступен. Попробуйте через несколько секунд.")
        return
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code == 404:
            await message.answer("Сначала нажмите /start.")
        else:
            logger.error("API error: %s", exc)
            await message.answer(format_http_error(exc))
        return
