from __future__ import annotations

from typing import Any

import httpx


class TelegramClient:
    def __init__(self, bot_token: str) -> None:
        self.bot_token = bot_token
        self.api_base = f"https://api.telegram.org/bot{bot_token}"
        self.file_base = f"https://api.telegram.org/file/bot{bot_token}"

    def get_me(self) -> dict[str, Any]:
        return self._post("getMe")

    def set_webhook(self, webhook_url: str, secret_token: str) -> dict[str, Any]:
        return self._post(
            "setWebhook",
            {
                "url": webhook_url,
                "secret_token": secret_token,
                "allowed_updates": ["message"],
            },
        )

    def send_message(self, chat_id: str | int, text: str) -> dict[str, Any]:
        return self._post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text[:4096],
                "disable_web_page_preview": True,
            },
        )

    def get_file(self, file_id: str) -> dict[str, Any]:
        return self._post("getFile", {"file_id": file_id})

    def download_file(self, file_path: str) -> bytes:
        with httpx.Client(timeout=60) as client:
            response = client.get(f"{self.file_base}/{file_path}")
        response.raise_for_status()
        return response.content

    def _post(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        with httpx.Client(timeout=30) as client:
            response = client.post(f"{self.api_base}/{method}", json=payload or {})
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise ValueError(str(body.get("description") or f"Telegram {method} failed."))
        return dict(body.get("result") or {})
