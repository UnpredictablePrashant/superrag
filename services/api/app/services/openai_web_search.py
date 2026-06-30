from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import httpx

from app.services.model_runtime import get_openai_connection
from app.services.retrieval import Candidate


def openai_web_search_candidates(
    db,
    *,
    organization_id: UUID,
    query: str,
    preferred_model: str | None = None,
) -> list[Candidate]:
    connection = get_openai_connection(db, organization_id)
    if not connection:
        raise ValueError("OpenAI web search requires an enabled OpenAI provider connection.")
    api_key, base_url = connection
    response = _call_openai_web_search(
        api_key=api_key,
        base_url=base_url,
        model=preferred_model or "gpt-5.1-mini",
        query=query,
    )
    text = _response_text(response).strip()
    if not text:
        return []
    annotations = _response_annotations(response)
    first_url = next((annotation.get("url") for annotation in annotations if annotation.get("url")), None)
    title = next((annotation.get("title") for annotation in annotations if annotation.get("title")), None)
    return [
        Candidate(
            chunk_id=f"openai-web:{uuid4()}",
            document_id="openai-web-search",
            document_name=title or "OpenAI web search",
            text=text[:6000],
            score=0.74,
            source="openai_web_search",
            metadata={
                "source_type": "OpenAI Web",
                "source_url": first_url,
                "annotations": annotations[:12],
                "live": True,
            },
        )
    ]


def _call_openai_web_search(*, api_key: str, base_url: str | None, model: str, query: str) -> dict[str, Any]:
    url = f"{(base_url or 'https://api.openai.com/v1').rstrip('/')}/responses"
    payload = {
        "model": model,
        "input": query,
        "tools": [{"type": "web_search"}],
    }
    with httpx.Client(timeout=60) as client:
        response = client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    response.raise_for_status()
    return response.json()


def _response_text(response: dict[str, Any]) -> str:
    if response.get("output_text"):
        return str(response["output_text"])
    parts: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("text"):
                parts.append(str(content["text"]))
    return "\n\n".join(parts)


def _response_annotations(response: dict[str, Any]) -> list[dict[str, str]]:
    annotations: list[dict[str, str]] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            for annotation in content.get("annotations", []):
                if not isinstance(annotation, dict):
                    continue
                url = str(annotation.get("url") or "").strip()
                title = str(annotation.get("title") or "").strip()
                if url or title:
                    annotations.append({"url": url, "title": title})
    return annotations
