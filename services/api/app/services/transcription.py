from __future__ import annotations

import httpx


def transcribe_audio_openai(
    *,
    api_key: str,
    data: bytes,
    filename: str,
    content_type: str | None = None,
    base_url: str | None = None,
    model: str = "whisper-1",
) -> str:
    endpoint = (base_url or "https://api.openai.com/v1").rstrip("/")
    files = {"file": (filename, data, content_type or "application/octet-stream")}
    form = {"model": model}
    with httpx.Client(timeout=120) as client:
        response = client.post(
            f"{endpoint}/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            data=form,
            files=files,
        )
    response.raise_for_status()
    return str(response.json().get("text") or "").strip()
