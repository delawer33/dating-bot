"""Discovery viewer checks, inbox lists, next card, and like/skip."""

from __future__ import annotations

import logging
import uuid

import redis.asyncio as aioredis
from botocore.client import BaseClient
from fastapi import HTTPException
from sqlalchemy import and_, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from api.messaging.events import EventPublisher
from api.services import registration_service as reg_svc
from api.services.profile_card import build_profile_card
from shared.db.models import Match, Profile, ProfileInteraction, User, UserPreferences

from .queue import invalidate_discovery_queue, pop_next_target_id

logger = logging.getLogger(__name__)


async def _get_user_by_telegram(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def _require_registered_viewer(session: AsyncSession, telegram_id: int) -> User:
    user = await _get_user_by_telegram(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    prefs = await reg_svc.get_preferences_if_exists(session, user.id)
    if prefs is None or not user.registration_completed:
        raise HTTPException(status_code=403, detail="Registration not complete.")
    return user


async def list_incoming_likes(
    session: AsyncSession,
    telegram_id: int,
    *,
    limit: int = 40,
) -> list[dict]:
    """All likes toward this user (newest first). Telegram contact only if pair has a Match."""
    viewer = await _require_registered_viewer(session, telegram_id)
    pi = ProfileInteraction
    actor_user = aliased(User)
    stmt = (
        select(
            pi.id,
            pi.actor_user_id,
            pi.created_at,
            Profile.display_name,
            Match.id,
            actor_user.telegram_id,
            actor_user.username,
        )
        .join(Profile, Profile.user_id == pi.actor_user_id)
        .join(actor_user, actor_user.id == pi.actor_user_id)
        .outerjoin(
            Match,
            and_(
                Match.user_a_id == func.least(viewer.id, pi.actor_user_id),
                Match.user_b_id == func.greatest(viewer.id, pi.actor_user_id),
            ),
        )
        .where(pi.target_user_id == viewer.id)
        .where(pi.action == "like")
        .order_by(pi.created_at.desc())
        .limit(min(max(limit, 1), 100))
    )
    result = await session.execute(stmt)
    out: list[dict] = []
    for row in result.all():
        iid, actor_id, created_at, display_name, match_row_id, tg_id, username = row
        is_matched = match_row_id is not None
        tg_out: int | None = None
        uname_out: str | None = None
        if is_matched and tg_id is not None:
            tg_out = int(tg_id)
            uname_out = username
        out.append(
            {
                "interaction_id": iid,
                "actor_user_id": actor_id,
                "created_at": created_at,
                "actor_display_name": display_name or "Без имени",
                "is_matched": is_matched,
                "actor_telegram_id": tg_out,
                "actor_username": uname_out,
            }
        )
    return out


async def list_incoming_likes_inbox(
    session: AsyncSession,
    telegram_id: int,
    *,
    s3_client: BaseClient | None,
) -> list[dict]:
    """Up to 10 people who liked you, no match yet, and you have not liked/skipped them back."""
    viewer = await _require_registered_viewer(session, telegram_id)
    inc = aliased(ProfileInteraction, name="inc_like")
    actor_user = aliased(User)
    resp = aliased(ProfileInteraction, name="resp")

    you_responded = exists(
        select(1).select_from(resp).where(
            resp.actor_user_id == viewer.id,
            resp.target_user_id == inc.actor_user_id,
        )
    )

    stmt = (
        select(
            inc.id,
            inc.actor_user_id,
            inc.created_at,
            Profile.display_name,
        )
        .select_from(inc)
        .join(Profile, Profile.user_id == inc.actor_user_id)
        .join(actor_user, actor_user.id == inc.actor_user_id)
        .outerjoin(
            Match,
            and_(
                Match.user_a_id == func.least(viewer.id, inc.actor_user_id),
                Match.user_b_id == func.greatest(viewer.id, inc.actor_user_id),
            ),
        )
        .where(inc.target_user_id == viewer.id)
        .where(inc.action == "like")
        .where(Match.id.is_(None))
        .where(~you_responded)
        .order_by(inc.created_at.desc())
        .limit(10)
    )
    result = await session.execute(stmt)
    out: list[dict] = []
    for row in result.all():
        iid, actor_id, created_at, display_name = row
        profile_dict: dict | None = None
        try:
            profile_dict = await build_profile_card(session, actor_id, s3_client)
        except HTTPException:
            logger.warning("Inbox skip actor %s: profile card missing", actor_id)
            continue
        out.append(
            {
                "interaction_id": iid,
                "actor_user_id": actor_id,
                "created_at": created_at,
                "actor_display_name": display_name or "Без имени",
                "is_matched": False,
                "actor_telegram_id": None,
                "actor_username": None,
                "profile": profile_dict,
            }
        )
    return out


async def build_profile_out(
    session: AsyncSession,
    target_id: uuid.UUID,
    s3_client: BaseClient | None,
) -> dict:
    return await build_profile_card(session, target_id, s3_client)


async def get_next_profile(
    redis: aioredis.Redis,
    session: AsyncSession,
    telegram_id: int,
    s3_client: BaseClient | None,
) -> dict:
    viewer = await _require_registered_viewer(session, telegram_id)
    prefs = await reg_svc.get_preferences_if_exists(session, viewer.id)
    assert prefs is not None
    tid = await pop_next_target_id(redis, session, viewer, prefs)
    if tid is None:
        return {"profile": None, "exhausted": True}
    profile_out = await build_profile_out(session, tid, s3_client)
    return {"profile": profile_out, "exhausted": False}


def _ordered_pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (a, b) if a < b else (b, a)


async def record_like(
    redis: aioredis.Redis,
    session: AsyncSession,
    publisher: EventPublisher,
    *,
    telegram_id: int,
    target_user_id: uuid.UUID,
) -> dict:
    actor = await _require_registered_viewer(session, telegram_id)
    if target_user_id == actor.id:
        raise HTTPException(status_code=422, detail="Cannot like yourself.")
    target = await session.get(User, target_user_id)
    if not target or not target.is_active:
        raise HTTPException(status_code=404, detail="Target not found.")

    reciprocal_before = await session.scalar(
        select(ProfileInteraction.id).where(
            ProfileInteraction.actor_user_id == target_user_id,
            ProfileInteraction.target_user_id == actor.id,
            ProfileInteraction.action == "like",
        )
    )

    interaction_id = uuid.uuid4()
    session.add(
        ProfileInteraction(
            id=interaction_id,
            actor_user_id=actor.id,
            target_user_id=target_user_id,
            action="like",
        )
    )
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Already interacted with this profile.",
        ) from exc

    peer_name: str | None = None
    match_id: uuid.UUID | None = None
    matched = False
    is_new_match = False

    if reciprocal_before is not None:
        ua, ub = _ordered_pair(actor.id, target_user_id)
        existing = await session.scalar(
            select(Match.id).where(Match.user_a_id == ua, Match.user_b_id == ub)
        )
        if existing is None:
            match_id = uuid.uuid4()
            session.add(Match(id=match_id, user_a_id=ua, user_b_id=ub))
            is_new_match = True
        else:
            match_id = existing
        matched = True
        tp = await session.get(Profile, target_user_id)
        peer_name = tp.display_name if tp else None

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Already interacted with this profile.",
        ) from exc

    await invalidate_discovery_queue(redis, actor.id)

    try:
        await publisher.publish_profile_liked(
            actor_user_id=actor.id,
            target_user_id=target_user_id,
            interaction_id=interaction_id,
            creates_match=matched,
        )
        if is_new_match and match_id is not None:
            ua, ub = _ordered_pair(actor.id, target_user_id)
            await publisher.publish_match_created(
                match_id=match_id,
                user_a_id=ua,
                user_b_id=ub,
                initiated_by_user_id=actor.id,
            )
    except Exception:
        logger.exception("Failed to publish like/match events")

    peer_telegram_id: int | None = None
    peer_username: str | None = None
    if matched:
        peer_u = await session.get(User, target_user_id)
        if peer_u:
            if peer_u.telegram_id is not None:
                peer_telegram_id = int(peer_u.telegram_id)
            peer_username = peer_u.username

    return {
        "matched": matched,
        "match_id": match_id,
        "peer_display_name": peer_name,
        "target_user_id": target_user_id,
        "peer_telegram_id": peer_telegram_id,
        "peer_username": peer_username,
    }


async def record_skip(
    redis: aioredis.Redis,
    session: AsyncSession,
    publisher: EventPublisher,
    *,
    telegram_id: int,
    target_user_id: uuid.UUID,
) -> dict:
    actor = await _require_registered_viewer(session, telegram_id)
    if target_user_id == actor.id:
        raise HTTPException(status_code=422, detail="Cannot skip yourself.")

    interaction_id = uuid.uuid4()
    session.add(
        ProfileInteraction(
            id=interaction_id,
            actor_user_id=actor.id,
            target_user_id=target_user_id,
            action="skip",
        )
    )
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Already interacted with this profile.",
        ) from exc

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Already interacted with this profile.",
        ) from exc

    await invalidate_discovery_queue(redis, actor.id)

    try:
        await publisher.publish_profile_skipped(
            actor_user_id=actor.id,
            target_user_id=target_user_id,
            interaction_id=interaction_id,
        )
    except Exception:
        logger.exception("Failed to publish skip event")

    return {"ok": True, "target_user_id": target_user_id}
