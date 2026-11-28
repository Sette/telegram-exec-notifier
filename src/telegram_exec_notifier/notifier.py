"""Client for the local Telegram notification service."""

from __future__ import annotations

import asyncio
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class TelegramNotifier:
    """Send messages to the local notifier service."""

    def __init__(self, service_url: str | None = None) -> None:
        self.service_url = (service_url or os.getenv("TELEGRAM_NOTIFIER_URL", "http://127.0.0.1:8765")).rstrip("/")

    async def send(self, message: str) -> None:
        """Send a plain text notification via the local service."""
        await asyncio.to_thread(self._send, message)

    def _send(self, message: str) -> None:
        payload = json.dumps({"text": message}).encode()
        request = Request(
            f"{self.service_url}/notify",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                if response.status != 200:
                    raise RuntimeError(f"Notifier service returned HTTP {response.status}")
        except (HTTPError, URLError) as exc:
            raise RuntimeError(f"Could not send notification: {exc}") from exc

    async def execution_finished(self, tool: str, summary: str, *, success: bool = True) -> None:
        """Send a consistently formatted execution result."""
        status = "✅ concluída" if success else "❌ falhou"
        await self.send(f"{tool}: execução {status}\n\n{summary}")
