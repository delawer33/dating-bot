import logging
from datetime import date

import httpx
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from dateutil import parser as dateutil_parser

from bot import api_client
from bot.config import settings
from bot.utils.api_errors import format_http_error
from bot.keyboards import (
    BTN_PREF_ALL,
    BTN_PREF_MEN,
    BTN_PREF_MW,
    BTN_PREF_WOMEN,
    GENDER_KEYBOARD,
    LOCATION_KEYBOARD,
    MAIN_MENU_KEYBOARD,
    OPTIONAL_BIO_KEYBOARD,
    REGISTRATION_COMPLETE,
    REGISTRATION_PHOTOS_NEXT,
    SEARCH_GENDER_REPLY,
    registration_interests_keyboard,
)
from bot.redis_client import get_redis
from bot.resilience import ApiUnavailableError
from bot.states import RegistrationStates

logger = logging.getLogger(__name__)
router = Router()

_STEP_MESSAGES = {
    "display_name": "Как вас зовут? (имя, которое увидят другие пользователи)",
    "birth_date": "Введите дату рождения в формате ГГГГ-ММ-ДД (например, 1990-01-15).",
    "gender": "Укажите ваш пол:",
    "location": "Поделитесь геолокацией, чтобы мы могли находить людей рядом с вами.",
    "photos": (
        f"Отправьте хотя бы {settings.registration_min_photos} фото "
        f"профиля. Можно не более {settings.registration_max_photos} фотографий."
    ),
    "search_preferences": (
        "Параметры поиска. Сначала введите возрастной диапазон анкет двумя числами "
        "через пробел (например: 18 35) — минимальный и максимальный возраст."
    ),
    "optional_profile": (
        "Необязательно: расскажите о себе одним сообщением или нажмите «Пропустить «о себе»»."
    ),
}

_STEP_TO_STATE = {
    "display_name": RegistrationStates.waiting_display_name,
    "birth_date": RegistrationStates.waiting_birth_date,
    "gender": RegistrationStates.waiting_gender,
    "location": RegistrationStates.waiting_location,
    "photos": RegistrationStates.waiting_photos,
    "search_preferences": RegistrationStates.waiting_search_age,
    "optional_profile": RegistrationStates.waiting_optional_bio,
}


async def prompt_for_step(message: Message, state: FSMContext, step: str) -> None:
    if step == "complete":
        await state.clear()
        await message.answer(
            "Регистрация завершена! Добро пожаловать в dating-бот. 🎉",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(
            "Главное меню:",
            reply_markup=MAIN_MENU_KEYBOARD,
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
    elif step == "photos":
        await message.answer(_STEP_MESSAGES[step], reply_markup=ReplyKeyboardRemove())
    elif step == "search_preferences":
        await message.answer(_STEP_MESSAGES[step], reply_markup=ReplyKeyboardRemove())
    elif step == "optional_profile":
        await message.answer(_STEP_MESSAGES[step], reply_markup=OPTIONAL_BIO_KEYBOARD)
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

    await prompt_for_step(message, state, result["registration_step"])


@router.message(RegistrationStates.waiting_location)
async def handle_location_wrong_type(message: Message) -> None:
    await message.answer("Пожалуйста, используйте кнопку «Поделиться геолокацией».")


@router.message(RegistrationStates.waiting_photos, F.photo)
async def handle_registration_photo(message: Message, state: FSMContext) -> None:
    if not message.photo:
        return
    file_id = message.photo[-1].file_id

    msg_dedup_key: str | None = None
    if message.message_id is not None and message.chat is not None:
        msg_dedup_key = f"reg_photo_msg:{message.chat.id}:{message.message_id}"
        r = get_redis()
        if not await r.set(msg_dedup_key, "1", ex=300, nx=True):
            return

    try:
        result = await api_client.add_registration_photo(message.from_user.id, file_id)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        if msg_dedup_key:
            await get_redis().delete(msg_dedup_key)
        await _handle_api_error(message, exc)
        return

    n = int(result.get("photo_count", 0))
    min_p = settings.registration_min_photos
    max_p = settings.registration_max_photos

    if n < min_p:
        await message.answer(
            f"Фото сохранено ({n} из {min_p}). Можно отправить ещё снимок.",
        )
    elif n < max_p:
        await message.answer(
            f"Фото сохранено ({n}). Можно добавить ещё (до {max_p}) "
            f"или нажмите «Дальше».",
            reply_markup=REGISTRATION_PHOTOS_NEXT,
        )
    else:
        await message.answer(
            "Сохранено максимальное количество фотографий. Нажмите «Дальше».",
            reply_markup=REGISTRATION_PHOTOS_NEXT,
        )


@router.message(RegistrationStates.waiting_photos, F.text)
async def handle_photos_text_not_photo(message: Message) -> None:
    await message.answer("Пожалуйста, отправьте изображение как фото, а не файлом.")


@router.callback_query(
    RegistrationStates.waiting_photos,
    F.data == "registration:photos_next",
)
async def handle_photos_next(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.message or not callback.from_user:
        return
    try:
        result = await api_client.registration_start(
            callback.from_user.id,
            callback.from_user.username if callback.from_user else None,
            None,
        )
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        if callback.message:
            await _handle_api_error(callback.message, exc)
        return
    n = int(result.get("photo_count", 0))
    if n < settings.registration_min_photos:
        if callback.message:
            await callback.message.answer(
                f"Нужно минимум {settings.registration_min_photos} фото. Отправьте ещё снимок."
            )
        return
    step = result.get("registration_step", "photos")
    if callback.message:
        await prompt_for_step(callback.message, state, step)


@router.message(RegistrationStates.waiting_search_age, F.text)
async def handle_search_age(message: Message, state: FSMContext) -> None:
    parsed = _parse_two_ints((message.text or "").strip())
    if parsed is None:
        await message.answer("Введите два целых числа через пробел, например: 18 35")
        return
    lo, hi = parsed
    try:
        await api_client.registration_search_age(message.from_user.id, lo, hi)
        result = await api_client.registration_start(
            message.from_user.id, message.from_user.username, None
        )
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _handle_api_error(message, exc)
        return
    step = result.get("registration_step", "search_preferences")
    if step == "search_preferences":
        await state.set_state(RegistrationStates.waiting_search_gender)
        await message.answer(
            "Кого показывать в ленте?",
            reply_markup=SEARCH_GENDER_REPLY,
        )
    else:
        await prompt_for_step(message, state, step)


@router.message(RegistrationStates.waiting_search_gender, F.text)
async def handle_search_gender(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    mapping = {
        BTN_PREF_ALL: [],
        BTN_PREF_MEN: ["male"],
        BTN_PREF_WOMEN: ["female"],
        BTN_PREF_MW: ["male", "female"],
    }
    if raw not in mapping:
        await message.answer("Выберите вариант с клавиатуры ниже.")
        return
    prefs = mapping[raw]
    try:
        await api_client.registration_search_gender(message.from_user.id, prefs)
        result = await api_client.registration_start(
            message.from_user.id, message.from_user.username, None
        )
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _handle_api_error(message, exc)
        return
    step = result.get("registration_step", "search_preferences")
    if step == "search_preferences":
        await state.set_state(RegistrationStates.waiting_search_distance)
        await message.answer(
            "Максимальное расстояние до кандидатов (км). Введите целое число, "
            f"не больше {settings.preferences_max_distance_km}.",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await prompt_for_step(message, state, step)


@router.message(RegistrationStates.waiting_search_distance, F.text)
async def handle_search_distance(message: Message, state: FSMContext) -> None:
    t = (message.text or "").strip()
    try:
        km = int(t)
    except ValueError:
        await message.answer("Введите целое число километров.")
        return
    try:
        await api_client.registration_search_distance(message.from_user.id, km)
        result = await api_client.registration_start(
            message.from_user.id, message.from_user.username, None
        )
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _handle_api_error(message, exc)
        return
    await prompt_for_step(message, state, result["registration_step"])


@router.message(RegistrationStates.waiting_optional_bio, F.text)
async def handle_optional_bio(message: Message, state: FSMContext) -> None:
    from bot.keyboards import BTN_OPTIONAL_BIO_SKIP

    text = (message.text or "").strip()
    if text == BTN_OPTIONAL_BIO_SKIP:
        text = ""
    try:
        await api_client.registration_bio(message.from_user.id, text)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        await _handle_api_error(message, exc)
        return
    await state.update_data(reg_interests_selected=[])
    await state.set_state(RegistrationStates.waiting_optional_interests)
    await message.answer(
        "Скрываю текстовую клавиатуру.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "Выберите интересы (несколько можно), затем «Готово» или «Пропустить».",
        reply_markup=registration_interests_keyboard(frozenset()),
    )


@router.callback_query(
    RegistrationStates.waiting_optional_interests,
    F.data.startswith("regint:"),
)
async def handle_reg_interests(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data or not callback.message or not callback.from_user:
        await callback.answer()
        return
    action = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected: list[str] = list(data.get("reg_interests_selected") or [])

    if action in ("done", "skip"):
        await callback.answer()
        ids = [] if action == "skip" else selected
        try:
            await api_client.registration_interests(callback.from_user.id, ids)
        except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
            await _handle_api_error(callback.message, exc)
            return
        await state.set_state(RegistrationStates.waiting_complete_confirm)
        await callback.message.answer(
            "Готово. Нажмите кнопку ниже, чтобы завершить регистрацию.",
            reply_markup=REGISTRATION_COMPLETE,
        )
        return

    await callback.answer()
    iid = action
    if iid in selected:
        selected = [x for x in selected if x != iid]
    else:
        selected.append(iid)
    await state.update_data(reg_interests_selected=selected)
    await callback.message.edit_reply_markup(
        reply_markup=registration_interests_keyboard(frozenset(selected))
    )


@router.callback_query(
    RegistrationStates.waiting_complete_confirm,
    F.data == "registration:complete",
)
async def handle_registration_complete(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.message or not callback.from_user:
        return
    try:
        result = await api_client.complete_registration(callback.from_user.id)
    except (ApiUnavailableError, httpx.HTTPStatusError) as exc:
        if callback.message:
            await _handle_api_error(callback.message, exc)
        return

    if callback.message:
        await prompt_for_step(callback.message, state, result["registration_step"])


@router.message(RegistrationStates.waiting_photos)
async def handle_photos_unsupported(message: Message) -> None:
    await message.answer("Пожалуйста, отправьте фотографию.")


def _parse_date(raw: str) -> date | None:
    try:
        return dateutil_parser.parse(raw, dayfirst=False).date()
    except (ValueError, OverflowError):
        return None


def _parse_two_ints(raw: str) -> tuple[int, int] | None:
    parts = raw.replace(",", " ").split()
    if len(parts) != 2:
        return None
    try:
        a = int(parts[0])
        b = int(parts[1])
    except ValueError:
        return None
    return (min(a, b), max(a, b))


async def _handle_api_error(
    message: Message, exc: ApiUnavailableError | httpx.HTTPStatusError
) -> None:
    if isinstance(exc, ApiUnavailableError):
        await message.answer(
            "Сервис временно недоступен. Попробуйте через несколько секунд."
        )
        return

    await message.answer(f"Ошибка: {format_http_error(exc)}")
