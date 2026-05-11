"""Port for S3 presigned GET URLs used by profile cards (testable without boto wiring)."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol, runtime_checkable

from botocore.client import BaseClient

from shared.storage.s3 import presigned_get_url

logger = logging.getLogger(__name__)


@runtime_checkable
class PhotoPresigner(Protocol):
    async def presign(self, s3_key: str) -> str | None:
        """Return a time-limited URL for the object key, or None on failure."""


class BotoPhotoPresigner:
    """Production presigner backed by boto3 + shared presigned_get_url helper."""

    def __init__(self, s3_client: BaseClient, bucket: str) -> None:
        self._client = s3_client
        self._bucket = bucket

    async def presign(self, s3_key: str) -> str | None:
        try:
            return await asyncio.to_thread(
                presigned_get_url,
                self._client,
                self._bucket,
                s3_key,
                3600,
            )
        except Exception:
            logger.exception("Presign failed for %s", s3_key)
            return None


class StubPhotoPresigner:
    """Deterministic URLs for unit tests (no S3)."""

    def __init__(self, prefix: str = "https://test.invalid/") -> None:
        self._prefix = prefix.rstrip("/") + "/"

    async def presign(self, s3_key: str) -> str | None:
        return f"{self._prefix}{s3_key}"
