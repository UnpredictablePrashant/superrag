from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class TextChunk:
    text: str
    token_count: int
    chunk_index: int
    parent_index: int | None
    heading_hierarchy: list[str]
    start_offset: int
    end_offset: int
    provenance: dict[str, Any]


def estimate_tokens(text: str) -> int:
    return max(1, int(len(re.findall(r"\S+", text)) * 1.25))


def configuration_hash(strategy: str, size: int, overlap: int, config: dict[str, Any] | None = None) -> str:
    raw = f"{strategy}:{size}:{overlap}:{config or {}}"
    return hashlib.sha256(raw.encode()).hexdigest()


def chunk_text(
    text: str,
    *,
    strategy: str,
    chunk_size_tokens: int,
    overlap_tokens: int,
    provenance: list[dict[str, Any]] | None = None,
) -> list[TextChunk]:
    if strategy == "semantic":
        return _semantic_chunk(text, chunk_size_tokens, overlap_tokens)
    if strategy == "parent_child":
        return _parent_child_chunk(text, chunk_size_tokens, overlap_tokens)
    if strategy == "document_aware":
        return _document_aware_chunk(text, chunk_size_tokens, overlap_tokens, provenance or [])
    return _recursive_chunk(text, chunk_size_tokens, overlap_tokens)


def _recursive_chunk(text: str, size: int, overlap: int) -> list[TextChunk]:
    sections = _split_by_headings(text)
    chunks: list[TextChunk] = []
    offset = 0
    for heading, body in sections:
        for part in _window_words(body, size, overlap):
            start = text.find(part, offset)
            if start == -1:
                start = offset
            end = start + len(part)
            chunks.append(
                TextChunk(
                    text=part.strip(),
                    token_count=estimate_tokens(part),
                    chunk_index=len(chunks),
                    parent_index=None,
                    heading_hierarchy=[heading] if heading else [],
                    start_offset=start,
                    end_offset=end,
                    provenance={},
                )
            )
            offset = end
    return [chunk for chunk in chunks if chunk.text]


def _document_aware_chunk(text: str, size: int, overlap: int, provenance: list[dict[str, Any]]) -> list[TextChunk]:
    page_sections = re.split(r"(?=\[Page \d+\]|\[Slide \d+\]|\[Sheet: [^\]]+\])", text)
    if len(page_sections) <= 1:
        return _recursive_chunk(text, size, overlap)
    chunks: list[TextChunk] = []
    cursor = 0
    for section in page_sections:
        for part in _window_words(section, size, overlap):
            start = text.find(part, cursor)
            end = start + len(part) if start >= 0 else cursor + len(part)
            chunks.append(
                TextChunk(
                    text=part.strip(),
                    token_count=estimate_tokens(part),
                    chunk_index=len(chunks),
                    parent_index=None,
                    heading_hierarchy=_extract_headings(part),
                    start_offset=max(start, cursor),
                    end_offset=end,
                    provenance=_nearest_provenance(provenance, part),
                )
            )
            cursor = end
    return [chunk for chunk in chunks if chunk.text]


def _semantic_chunk(text: str, size: int, overlap: int) -> list[TextChunk]:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    groups: list[str] = []
    current: list[str] = []
    current_terms: set[str] = set()
    for paragraph in paragraphs:
        terms = set(re.findall(r"[a-zA-Z]{4,}", paragraph.lower()))
        shift = current_terms and len(terms & current_terms) / max(1, len(terms | current_terms)) < 0.08
        if current and (estimate_tokens("\n\n".join(current + [paragraph])) > size or shift):
            groups.append("\n\n".join(current))
            current = []
            current_terms = set()
        current.append(paragraph)
        current_terms |= terms
    if current:
        groups.append("\n\n".join(current))
    if not groups:
        return _recursive_chunk(text, size, overlap)
    chunks = []
    cursor = 0
    for group in groups:
        start = text.find(group, cursor)
        end = start + len(group) if start >= 0 else cursor + len(group)
        chunks.append(
            TextChunk(group, estimate_tokens(group), len(chunks), None, _extract_headings(group), start, end, {})
        )
        cursor = end
    return chunks


def _parent_child_chunk(text: str, size: int, overlap: int) -> list[TextChunk]:
    parent_size = max(size * 2, 1200)
    parents = _recursive_chunk(text, parent_size, overlap)
    children: list[TextChunk] = []
    for parent in parents:
        for child in _recursive_chunk(parent.text, size, overlap):
            child.parent_index = parent.chunk_index
            child.chunk_index = len(children)
            child.start_offset += parent.start_offset
            child.end_offset += parent.start_offset
            children.append(child)
    return children


def _split_by_headings(text: str) -> list[tuple[str | None, str]]:
    matches = list(re.finditer(r"(?m)^(#{1,6}\s+.+|[A-Z][A-Z0-9 ,:/-]{8,})$", text))
    if not matches:
        return [(None, text)]
    sections: list[tuple[str | None, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append((match.group(0).strip("# "), text[start:end]))
    return sections


def _window_words(text: str, size: int, overlap: int) -> list[str]:
    words = re.findall(r"\S+", text)
    if not words:
        return []
    approx_words = max(40, int(size / 1.25))
    overlap_words = max(0, int(overlap / 1.25))
    step = max(1, approx_words - overlap_words)
    windows = []
    for start in range(0, len(words), step):
        window = words[start : start + approx_words]
        if not window:
            continue
        windows.append(" ".join(window))
        if start + approx_words >= len(words):
            break
    return windows


def _extract_headings(text: str) -> list[str]:
    return [line.strip("# ").strip() for line in text.splitlines() if re.match(r"^(#{1,6}\s+|[A-Z][A-Z0-9 ,:/-]{8,}$)", line.strip())][:4]


def _nearest_provenance(provenance: list[dict[str, Any]], text: str) -> dict[str, Any]:
    if not provenance:
        return {}
    return max(provenance, key=lambda item: len(set(str(item.get("text", "")).split()) & set(text.split())))
