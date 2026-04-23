from fastapi import APIRouter

from api.dependencies import BotAuth, DBSession, EventPublisherDep, RedisClient, S3Client
from api.schemas.discovery import (
    DiscoveryActionRequest,
    DiscoveryIncomingLikesRequest,
    DiscoveryIncomingLikesResponse,
    DiscoveryLikeResponse,
    DiscoveryNextRequest,
    DiscoveryNextResponse,
    DiscoverySkipResponse,
    IncomingLikeItem,
)
from api.services import discovery_service as disc

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.post("/next", response_model=DiscoveryNextResponse)
async def discovery_next(
    body: DiscoveryNextRequest,
    session: DBSession,
    redis: RedisClient,
    s3: S3Client,
    _auth: BotAuth,
) -> DiscoveryNextResponse:
    data = await disc.get_next_profile(redis, session, body.telegram_id, s3)
    return DiscoveryNextResponse(**data)


@router.post("/like", response_model=DiscoveryLikeResponse)
async def discovery_like(
    body: DiscoveryActionRequest,
    session: DBSession,
    redis: RedisClient,
    publisher: EventPublisherDep,
    _auth: BotAuth,
) -> DiscoveryLikeResponse:
    data = await disc.record_like(
        redis,
        session,
        publisher,
        telegram_id=body.telegram_id,
        target_user_id=body.target_user_id,
    )
    return DiscoveryLikeResponse(**data)


@router.post("/skip", response_model=DiscoverySkipResponse)
async def discovery_skip(
    body: DiscoveryActionRequest,
    session: DBSession,
    redis: RedisClient,
    publisher: EventPublisherDep,
    _auth: BotAuth,
) -> DiscoverySkipResponse:
    data = await disc.record_skip(
        redis,
        session,
        publisher,
        telegram_id=body.telegram_id,
        target_user_id=body.target_user_id,
    )
    return DiscoverySkipResponse(**data)


@router.post("/incoming-likes", response_model=DiscoveryIncomingLikesResponse)
async def discovery_incoming_likes(
    body: DiscoveryIncomingLikesRequest,
    session: DBSession,
    s3: S3Client,
    _auth: BotAuth,
) -> DiscoveryIncomingLikesResponse:
    if body.mode == "inbox":
        rows = await disc.list_incoming_likes_inbox(
            session, body.telegram_id, s3_client=s3
        )
    else:
        lim = min(max(body.limit, 1), 100)
        rows = await disc.list_incoming_likes(session, body.telegram_id, limit=lim)
    items = [IncomingLikeItem(**r) for r in rows]
    return DiscoveryIncomingLikesResponse(likes=items)
