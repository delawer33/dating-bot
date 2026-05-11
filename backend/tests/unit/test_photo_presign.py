"""Photo presigner port implementations."""

from __future__ import annotations

import pytest

from api.services.photo_presign import StubPhotoPresigner


@pytest.mark.asyncio
async def test_stub_photo_presigner_builds_url() -> None:
    p = StubPhotoPresigner("https://cdn.example/")
    assert await p.presign("profiles/u/1.jpg") == "https://cdn.example/profiles/u/1.jpg"
