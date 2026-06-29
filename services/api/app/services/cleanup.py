from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.services.quality import PII_PATTERNS, SECRET_PATTERNS


@dataclass
class CleanedText:
    extracted_text: str
    cleaned_text: str
    redacted_text: str
    warnings: list[dict]


def clean_text(text: str, strategy: str, custom_patterns: list[str] | None = None) -> CleanedText:
    if strategy == "preserve_raw":
        cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    else:
        cleaned = standard_cleanup(text)
    warnings = []

    if strategy == "aggressive":
        cleaned = aggressive_cleanup(cleaned)
        warnings.append({"code": "aggressive_cleanup", "message": "Aggressive cleanup can alter paragraph boundaries."})

    redacted = redact_sensitive_text(cleaned, custom_patterns or [])
    if strategy == "redaction":
        cleaned = standard_cleanup(text)

    return CleanedText(extracted_text=text, cleaned_text=cleaned, redacted_text=redacted, warnings=warnings)


def standard_cleanup(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = _remove_repeated_headers_footers(text)
    return text.strip()


def aggressive_cleanup(text: str) -> str:
    text = standard_cleanup(text)
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    seen: set[str] = set()
    kept: list[str] = []
    for paragraph in paragraphs:
        fingerprint = re.sub(r"\W+", "", paragraph.lower())[:160]
        if fingerprint and fingerprint in seen:
            continue
        seen.add(fingerprint)
        kept.append(_repair_sentence_boundaries(paragraph))
    return "\n\n".join(kept)


def redact_sensitive_text(text: str, custom_patterns: list[str]) -> str:
    redacted = text
    for label, pattern in {**PII_PATTERNS, **SECRET_PATTERNS}.items():
        redacted = pattern.sub(f"[REDACTED {label.upper()}]", redacted)
    for pattern_text in custom_patterns:
        redacted = re.sub(pattern_text, "[REDACTED CUSTOM]", redacted)
    return redacted


def _remove_repeated_headers_footers(text: str) -> str:
    pages = re.split(r"\n?\[Page \d+\]\n", text)
    if len(pages) < 4:
        return text
    first_lines = [page.splitlines()[0].strip() for page in pages if page.splitlines()]
    last_lines = [page.splitlines()[-1].strip() for page in pages if page.splitlines()]
    repeated = {
        line
        for line in first_lines + last_lines
        if line and (first_lines + last_lines).count(line) >= max(3, len(pages) // 2)
    }
    if not repeated:
        return text
    lines = [line for line in text.splitlines() if line.strip() not in repeated]
    return "\n".join(lines)


def _repair_sentence_boundaries(paragraph: str) -> str:
    return re.sub(r"(?<=[a-z])\n(?=[a-z])", " ", paragraph, flags=re.I)
