"""Outbound Telegram Bot API (sendMessage) for workers — no aiogram dependency."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def send_telegram_text(
    chat_id: int,
    text: str,
    *,
    parse_mode: str | None = None,
    disable_web_page_preview: bool = False,
) -> bool:
    token = (os.environ.get("BOT_TOKEN") or "").strip()
    if not token:
        logger.warning("BOT_TOKEN unset; skip Telegram notification")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if disable_web_page_preview:
        payload["disable_web_page_preview"] = True
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
    except Exception:
        logger.exception("Telegram sendMessage request failed")
        return False
    if resp.status_code != 200:
        logger.warning(
            "Telegram sendMessage failed: %s %s", resp.status_code, resp.text[:500]
        )
        return False
    return True
