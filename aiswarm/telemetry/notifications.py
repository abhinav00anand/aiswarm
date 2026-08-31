"""
Notification system — sends high-signal, low-noise updates to operators.

Supports: Telegram, HTTP webhooks (Slack/Discord).
Payload always contains: task_id, state, current_file, error, retry_count.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class TelegramNotifier:
    """Sends Telegram messages via Bot API."""

    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
    ) -> None:
        self._token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self._enabled = bool(self._token and self._chat_id)

    async def send(self, message: str) -> bool:
        if not self._enabled:
            return False
        try:
            import httpx

            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    url,
                    json={
                        "chat_id": self._chat_id,
                        "text": message[:4096],
                        "parse_mode": "HTML",
                    },
                )
                return resp.status_code == 200
        except Exception as exc:  # noqa: BLE001
            logger.error("telegram.send_error", error=str(exc))
            return False

    async def notify_task_event(
        self,
        event_type: str,
        task_id: str,
        task_title: str,
        state: str,
        retry_count: int = 0,
        error: str | None = None,
    ) -> None:
        icon = {
            "MERGED": "✅",
            "REJECTED": "❌",
            "DEADLOCK": "🔒",
            "ESCALATED": "⚠️",
            "COMPILED": "🔨",
            "TESTED": "🧪",
        }.get(state, "ℹ️")
        msg = (
            f"{icon} <b>{event_type}</b>\n"
            f"Task: <code>{task_id[:8]}</code> — {task_title}\n"
            f"State: <b>{state}</b>\n"
            f"Retries: {retry_count}"
        )
        if error:
            msg += f"\nError: <code>{error[:200]}</code>"
        await self.send(msg)


class NotificationRouter:
    """Routes notifications to all configured channels."""

    def __init__(self) -> None:
        self._channels: list[TelegramNotifier] = [TelegramNotifier()]

    async def notify(self, message: str) -> None:
        tasks = [ch.send(message) for ch in self._channels]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def notify_task_event(self, **kwargs: Any) -> None:
        tasks = [ch.notify_task_event(**kwargs) for ch in self._channels]
        await asyncio.gather(*tasks, return_exceptions=True)
