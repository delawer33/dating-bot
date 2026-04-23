import asyncio
import html
import logging
import uuid
from datetime import datetime, timezone

import httpx
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from bot import api_client
from bot.resilience import ApiUnavailableError
logger = logging.getLogger(__name__)
router = Router()

_MAX_ALBUM = 10


def _photo_media_entries(profile: dict) -> list[str]:
    """Ordered Telegram file_id or HTTPS URL strings for sendPhoto / media group."""
    photos = profile.get("photos") or []
    out: list[str] = []
    for p in photos[:_MAX_ALBUM]:
        fid = p.get("telegram_file_id")
        if fid:
            out.append(str(fid))
            continue
        url = p.get("presigned_url")
        if url:
            out.append(str(url))
    return out


async def send_profile_card_media(
    message: Message,
    profile: dict,
    *,
    caption_extra: str = "",
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Send all card photos in order; caption on first item. Inline keyboard on single photo or text-only."""
    caption = format_discovery_card_caption(profile)
    if caption_extra:
        caption = f"{caption}{caption_extra}"

    media_values = _photo_media_entries(profile)
    if not media_values:
        await message.answer(caption, reply_markup=reply_markup)
        return

    if len(media_values) == 1:
        await message.answer_photo(
            photo=media_values[0],
            caption=caption,
            reply_markup=reply_markup,
        )
        return

    media: list[InputMediaPhoto] = [
        InputMediaPhoto(media=m, caption=caption if i == 0 else None)
        for i, m in enumerate(media_values)
    ]
    await message.answer_media_group(media=media)
    if reply_markup:
        await message.answer("👇 Лайк или пропуск:", reply_markup=reply_markup)


def _discovery_keyboard(target_id: uuid.UUID) -> InlineKeyboardMarkup:
    tid = str(target_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❤️ Лайк", callback_data=f"disc:like:{tid}"),
                InlineKeyboardButton(text="⏭ Пропуск", callback_data=f"disc:skip:{tid}"),
            ]
        ]
    )


def _inbox_keyboard(target_id: uuid.UUID) -> InlineKeyboardMarkup:
    tid = str(target_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❤️ Лайк", callback_data=f"inlikes:like:{tid}"),
                InlineKeyboardButton(text="⏭ Пропуск", callback_data=f"inlikes:skip:{tid}"),
            ]
        ]
    )


def _format_like_age(created_at: str) -> str:
    try:
        raw = created_at.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
    except (TypeError, ValueError, OSError):
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    sec = int((now - dt.astimezone(timezone.utc)).total_seconds())
    if sec < 60:
        return "только что"
    if sec < 3600:
        return f"{sec // 60} мин. назад"
    if sec < 86400:
        return f"{sec // 3600} ч. назад"
    if sec < 86400 * 7:
        return f"{sec // 86400} дн. назад"
    return f"{sec // (86400 * 7)} нед. назад"


def _telegram_contact_html(username: str | None, telegram_id: int | None) -> str:
    u = (username or "").strip().lstrip("@")
    if u:
        u_esc = html.escape(u, quote=True)
        return f'<a href="https://t.me/{u_esc}">@{u_esc}</a>'
    if telegram_id is not None:
        tid = int(telegram_id)
        return f'<a href="tg://user?id={tid}">Написать в Telegram</a>'
    return ""


def _match_reply_html(
    display_name: str, username: str | None, telegram_id: int | None
) -> str:
    name_e = html.escape(display_name or "Пользователь", quote=False)
    link = _telegram_contact_html(username, telegram_id)
    if link:
        return f"💜 <b>Матч!</b> {name_e} — {link}"
    return f"💜 <b>Матч!</b> {name_e}."


async def answer_incoming_likes_history(message: Message) -> None:
    try:
        data = await api_client.discovery_incoming_likes(
            message.from_user.id, mode="history", limit=40
        )
    except ApiUnavailableError:
        await message.answer("Сервис временно недоступен. Попробуйте через несколько секунд.")
        return
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (403, 404):
            await message.answer("Сначала завершите регистрацию или нажмите /start.")
        else:
            logger.error("discovery/incoming-likes failed: %s", exc)
            await message.answer("Не удалось загрузить список. Попробуйте позже.")
        return

    likes = data.get("likes") or []
    if not likes:
        await message.answer("Пока никто вас не лайкал. Загляните в «Анкеты» позже.")
        return

    lines: list[str] = ["<b>Кто вас лайкал</b> (история, новые сверху):"]
    for item in likes[:40]:
        name = item.get("actor_display_name") or "Без имени"
        name_e = html.escape(str(name), quote=False)
        when = item.get("created_at") or ""
        age = _format_like_age(str(when)) if when else ""
        suffix = f" — {html.escape(age, quote=False)}" if age else ""
        row = f"• {name_e}{suffix}"
        if item.get("is_matched"):
            link = _telegram_contact_html(
                item.get("actor_username"),
                item.get("actor_telegram_id"),
            )
            row += f" — 💜 {link}" if link else " — 💜 матч"
        lines.append(row)
    await message.answer("\n".join(lines), parse_mode="HTML")


async def answer_incoming_likes(message: Message) -> None:
    try:
        data = await api_client.discovery_incoming_likes(message.from_user.id, mode="inbox")
    except ApiUnavailableError:
        await message.answer("Сервис временно недоступен. Попробуйте через несколько секунд.")
        return
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (403, 404):
            await message.answer("Сначала завершите регистрацию или нажмите /start.")
        else:
            logger.error("discovery/incoming-likes failed: %s", exc)
            await message.answer("Не удалось загрузить список. Попробуйте позже.")
        return

    likes = data.get("likes") or []
    if not likes:
        await message.answer(
            "Во входящих пусто: либо вас ещё никто не лайкнул, либо вы уже ответили всем. "
            "Полный список лайков текстом: /likes_history"
        )
        return

    await message.answer(
        "💌 <b>Входящие</b> (до 10). Под фото — ❤️ лайк или ⏭ пропуск.",
        parse_mode="HTML",
    )
    for item in likes:
        prof = item.get("profile")
        if not prof or not isinstance(prof, dict):
            continue
        when = item.get("created_at")
        age = _format_like_age(str(when)) if when else ""
        extra = f"\n\n💌 Лайкнул вас: {age}" if age else "\n\n💌 Лайкнул вас."
        tid = uuid.UUID(str(prof["target_user_id"]))
        await send_profile_card_media(
            message,
            prof,
            caption_extra=extra,
            reply_markup=_inbox_keyboard(tid),
        )
        await asyncio.sleep(0.05)


def format_discovery_card_caption(profile: dict) -> str:
    lines: list[str] = []
    if profile.get("display_name"):
        lines.append(profile["display_name"])
    if profile.get("age") is not None:
        lines.append(f"Возраст: {profile['age']}")
    if profile.get("city"):
        lines.append(profile["city"])
    if profile.get("bio"):
        lines.append("")
        lines.append(str(profile["bio"])[:500])
    intr = profile.get("interests")
    if intr:
        lines.append("")
        lines.append("Интересы: " + ", ".join(str(x) for x in intr[:12]))
    return "\n".join(lines) if lines else "Анкета без описания."


async def send_next_discovery_card(message: Message) -> None:
    try:
        data = await api_client.discovery_next(message.from_user.id)
    except ApiUnavailableError:
        await message.answer("Сервис временно недоступен. Попробуйте через несколько секунд.")
        return
    except httpx.HTTPStatusError as exc:
        logger.error("discovery/next failed: %s", exc)
        await message.answer("Не удалось загрузить анкеты. Попробуйте позже.")
        return

    if data.get("exhausted") or not data.get("profile"):
        await message.answer("Пока больше нет подходящих анкет. Загляните позже — /browse")
        return

    profile = data["profile"]
    tid = uuid.UUID(str(profile["target_user_id"]))
    kb = _discovery_keyboard(tid)
    await send_profile_card_media(message, profile, reply_markup=kb)


@router.message(Command("browse"))
async def cmd_browse(message: Message) -> None:
    await message.answer("🔍 Ищем для вас следующую анкету…")
    await send_next_discovery_card(message)


@router.message(Command("likes"))
async def cmd_likes(message: Message) -> None:
    await answer_incoming_likes(message)


@router.message(Command("likes_history"))
async def cmd_likes_history(message: Message) -> None:
    await answer_incoming_likes_history(message)


@router.callback_query(F.data.startswith("inlikes:like:"))
async def on_inlikes_like(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.data:
        await callback.answer()
        return
    try:
        tid = callback.data.split(":", 2)[2]
        uuid.UUID(tid)
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные.", show_alert=True)
        return

    try:
        result = await api_client.discovery_like(callback.from_user.id, tid)
    except ApiUnavailableError:
        await callback.answer("Сервис недоступен.", show_alert=True)
        return
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            await callback.answer("Вы уже отметили этого пользователя.", show_alert=True)
        else:
            logger.error("discovery/like failed: %s", exc)
            await callback.answer("Ошибка сервиса.", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    if result.get("matched"):
        text = _match_reply_html(
            str(result.get("peer_display_name") or "Пользователь"),
            result.get("peer_username"),
            result.get("peer_telegram_id"),
        )
        text += (
            "\n\n<i>«Кто меня лайкнул» — чтобы увидеть остальных входящих.</i>"
        )
        await callback.message.answer(text, parse_mode="HTML")
    else:
        await callback.message.answer(
            "✅ Готово. Ещё раз: «Кто меня лайкнул».",
        )


@router.callback_query(F.data.startswith("inlikes:skip:"))
async def on_inlikes_skip(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.data:
        await callback.answer()
        return
    try:
        tid = callback.data.split(":", 2)[2]
        uuid.UUID(tid)
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные.", show_alert=True)
        return

    try:
        await api_client.discovery_skip(callback.from_user.id, tid)
    except ApiUnavailableError:
        await callback.answer("Сервис недоступен.", show_alert=True)
        return
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            await callback.answer("Уже обработано.", show_alert=True)
        else:
            logger.error("discovery/skip failed: %s", exc)
            await callback.answer("Ошибка сервиса.", show_alert=True)
        return

    await callback.answer("⏭ Пропуск.")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✅ Готово. Ещё раз: «Кто меня лайкнул».")


@router.callback_query(F.data.startswith("disc:like:"))
async def on_like(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.data:
        await callback.answer()
        return
    try:
        tid = callback.data.split(":", 2)[2]
        uuid.UUID(tid)
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные.", show_alert=True)
        return

    try:
        result = await api_client.discovery_like(callback.from_user.id, tid)
    except ApiUnavailableError:
        await callback.answer("Сервис недоступен.", show_alert=True)
        return
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            await callback.answer("Вы уже отметили этого пользователя.", show_alert=True)
        else:
            logger.error("discovery/like failed: %s", exc)
            await callback.answer("Ошибка сервиса.", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    if result.get("matched"):
        text = _match_reply_html(
            str(result.get("peer_display_name") or "Пользователь"),
            result.get("peer_username"),
            result.get("peer_telegram_id"),
        )
        await callback.message.answer(text, parse_mode="HTML")
        return
    await send_next_discovery_card(callback.message)


@router.callback_query(F.data.startswith("disc:skip:"))
async def on_skip(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.data:
        await callback.answer()
        return
    try:
        tid = callback.data.split(":", 2)[2]
        uuid.UUID(tid)
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные.", show_alert=True)
        return

    try:
        await api_client.discovery_skip(callback.from_user.id, tid)
    except ApiUnavailableError:
        await callback.answer("Сервис недоступен.", show_alert=True)
        return
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            await callback.answer("Уже обработано.", show_alert=True)
        else:
            logger.error("discovery/skip failed: %s", exc)
            await callback.answer("Ошибка сервиса.", show_alert=True)
        return

    await callback.answer("Пропуск.")
    await callback.message.edit_reply_markup(reply_markup=None)
    await send_next_discovery_card(callback.message)
