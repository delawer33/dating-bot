"""Discovery response schema parsing."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from api.schemas.discovery import DiscoveryLikeResponse, DiscoveryProfileOut, IncomingLikeItem


def test_discovery_like_response_matched_with_peer_contact() -> None:
    tid = uuid.uuid4()
    mid = uuid.uuid4()
    
    m = DiscoveryLikeResponse(
        matched=True,
        match_id=mid,
        peer_display_name="Ann",
        peer_telegram_id=111,
        peer_username="ann_user",
        target_user_id=tid,
    )
    
    assert m.peer_telegram_id == 111
    assert m.peer_username == "ann_user"


def test_incoming_like_item_with_match_fields() -> None:
    iid = uuid.uuid4()
    aid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    item = IncomingLikeItem(
        interaction_id=iid,
        actor_user_id=aid,
        created_at=now,
        actor_display_name="Bob",
        is_matched=True,
        actor_telegram_id=222,
        actor_username=None,
    )
    assert item.is_matched is True
    assert item.actor_telegram_id == 222


def test_incoming_like_item_with_profile() -> None:
    iid = uuid.uuid4()
    aid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    prof = DiscoveryProfileOut(
        target_user_id=aid,
        display_name="Card",
        photos=[],
    )
    item = IncomingLikeItem(
        interaction_id=iid,
        actor_user_id=aid,
        created_at=now,
        actor_display_name="Card",
        profile=prof,
    )
    assert item.profile is not None
    assert item.profile.display_name == "Card"
