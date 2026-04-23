"""Download files from Telegram Bot API (getFile) and validate image bytes."""
from __future__ import annotations

from typing import Final

import httpx

_JPEG: Final[bytes] = b"\xff\xd8\xff"
_PNG: Final[bytes] = b"\x89\x50\x4e\x47"
_RIFF: Final[bytes] = b"RIFF"
_WEBP: Final[bytes] = b"WEBP"

# Types we accept; magic bytes only (no full parser)
_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def sniff_image_content_type(data: bytes) -> str | None:
    if len(data) < 12:
        return None
    if data[:3] == _JPEG:
        return "image/jpeg"
    if data[:4] == _PNG:
        return "image/png"
    if data[:4] == _RIFF and data[8:12] == _WEBP:
        return "image/webp"
    return None


def extension_for_content_type(content_type: str) -> str:
    return _CONTENT_TYPES.get(content_type, "bin")


async def get_file_path(telegram_token: str, file_id: str) -> str:
    url = f"https://api.telegram.org/bot{telegram_token}/getFile"
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url, params={"file_id": file_id})
        r.raise_for_status()
        data = r.json()
    if not data.get("ok") or "result" not in data:
        msg = (data or {}).get("description", "getFile failed")
        raise ValueError(f"getFile: {msg}")
    path = data["result"].get("file_path")
    if not path or not isinstance(path, str):
        raise ValueError("getFile: missing file_path in response")
    return path


async def download_file_bytes(
    telegram_token: str, file_id: str, max_size: int
) -> tuple[bytes, str]:
    file_path = await get_file_path(telegram_token, file_id)
    url = f"https://api.telegram.org/file/bot{telegram_token}/{file_path}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(url)
        r.raise_for_status()
    body = r.content
    if len(body) > max_size:
        raise ValueError("File is too large.")
    content_type = sniff_image_content_type(body)
    if content_type is None:
        raise ValueError("Unsupported or invalid image data.")
    return body, content_type
