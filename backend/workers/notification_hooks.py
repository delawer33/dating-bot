"""Telegram push hooks for Rabbit events (called from behavior_consumer after DB commit)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models import Profile, User
from workers.telegram_notify import send_telegram_text

logger = logging.getLogger(__name__)


async def send_telegram_for_event(session: AsyncSession, envelope: dict[str, Any]) -> None:
    etype = envelope.get("type")
    payload = envelope.get("payload") or {}
    if etype == "profile.liked":
        await _notify_profile_liked(session, payload)
    elif etype == "match.created":
        await _notify_match_created(session, payload)


async def _notify_profile_liked(session: AsyncSession, payload: dict[str, Any]) -> None:
    if payload.get("creates_match"):
        return
    try:
        target_id = uuid.UUID(str(payload["target_user_id"]))
        actor_id = uuid.UUID(str(payload["actor_user_id"]))
    except (KeyError, TypeError, ValueError):
        logger.warning("profile.liked payload missing uuids: %s", payload)
        return
    t_user = await session.get(User, target_id)
    a_prof = await session.get(Profile, actor_id)
    if not t_user or t_user.telegram_id is None:
        return
    name = (a_prof.display_name if a_prof else None) or "Кто-то"
    text = (
        f"💌 Вас лайкнул(а) {name}. Откройте бота → «Кто меня лайкнул», "
        "чтобы ответить лайком или пропуском."
    )
    await send_telegram_text(int(t_user.telegram_id), text)


async def _notify_match_created(session: AsyncSession, payload: dict[str, Any]) -> None:
    try:
        ua = uuid.UUID(str(payload["user_a_id"]))
        ub = uuid.UUID(str(payload["user_b_id"]))
    except (KeyError, TypeError, ValueError):
        logger.warning("match.created payload missing uuids: %s", payload)
        return
    initiator: uuid.UUID | None = None
    raw_init = payload.get("initiated_by_user_id")
    if raw_init is not None:
        try:
            initiator = uuid.UUID(str(raw_init))
        except (TypeError, ValueError):
            initiator = None

    user_a = await session.get(User, ua)
    user_b = await session.get(User, ub)
    prof_a = await session.get(Profile, ua)
    prof_b = await session.get(Profile, ub)
    name_a = (prof_a.display_name if prof_a else None) or "Пользователь"
    name_b = (prof_b.display_name if prof_b else None) or "Пользователь"

    async def _push_match(chat_user: User | None, peer_name: str) -> None:
        if not chat_user or chat_user.telegram_id is None:
            return
        await send_telegram_text(
            int(chat_user.telegram_id),
            f"💜 У вас матч с {peer_name}! Загляните в бота — там контакт.",
        )

    if initiator is None:
        await _push_match(user_a, name_b)
        await _push_match(user_b, name_a)
        return

    if initiator == ua:
        await _push_match(user_b, name_a)
    elif initiator == ub:
        await _push_match(user_a, name_b)
