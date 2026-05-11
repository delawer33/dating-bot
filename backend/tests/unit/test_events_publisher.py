"""Event publisher guard rails."""

from __future__ import annotations

import pytest

from api.messaging.events import EventPublisher


@pytest.mark.asyncio
async def test_publish_requires_connected_exchange() -> None:
    pub = EventPublisher("amqp://guest:guest@localhost:5672//")
    with pytest.raises(RuntimeError, match="not connected"):
        await pub.publish("profile.liked", "profile.liked", {})
