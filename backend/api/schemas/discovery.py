"""Discovery / feed API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TelegramIdBody(BaseModel):
    telegram_id: int = Field(..., ge=1)


class DiscoveryNextRequest(TelegramIdBody):
    pass


class DiscoveryActionRequest(TelegramIdBody):
    target_user_id: uuid.UUID


class ProfilePhotoOut(BaseModel):
    id: uuid.UUID | None = None
    telegram_file_id: str | None = None
    presigned_url: str | None = None
    sort_order: int = 0


class DiscoveryProfileOut(BaseModel):
    target_user_id: uuid.UUID
    display_name: str | None = None
    bio: str | None = None
    interests: list[str] | None = None
    age: int | None = None
    city: str | None = None
    gender: str | None = None
    photos: list[ProfilePhotoOut] = Field(
        default_factory=list,
        description="All photos, ascending sort_order",
    )


class DiscoveryNextResponse(BaseModel):
    profile: DiscoveryProfileOut | None = None
    exhausted: bool = False


class DiscoveryLikeResponse(BaseModel):
    matched: bool
    match_id: uuid.UUID | None = None
    peer_display_name: str | None = None
    peer_telegram_id: int | None = None
    peer_username: str | None = None
    target_user_id: uuid.UUID


class DiscoverySkipResponse(BaseModel):
    ok: bool = True
    target_user_id: uuid.UUID


class IncomingLikeItem(BaseModel):
    interaction_id: uuid.UUID
    actor_user_id: uuid.UUID
    created_at: datetime
    actor_display_name: str
    is_matched: bool = False
    actor_telegram_id: int | None = None
    actor_username: str | None = None
    profile: DiscoveryProfileOut | None = None


class DiscoveryIncomingLikesRequest(TelegramIdBody):
    """`mode=inbox`: up to 10 pending likers + full profile cards. `mode=history`: text list only."""

    mode: Literal["inbox", "history"] = "inbox"
    limit: int = Field(default=10, ge=1, le=100)


class DiscoveryIncomingLikesResponse(BaseModel):
    likes: list[IncomingLikeItem] = Field(default_factory=list)
