from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any


@dataclass
class QualityReport:
    issues: list[dict[str, Any]]
    severity: str
    requires_review: bool
    summary: str


SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "api_key": re.compile(r"\b(?:api[_-]?key|token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}", re.I),
    "password": re.compile(r"\bpassword\s*[:=]\s*['\"]?\S{8,}", re.I),
}

PII_PATTERNS = {
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "phone": re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3,4}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "aadhaar_like": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    "pan_like": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
}


def analyze_quality(text: str, extraction_warnings: list[dict[str, Any]]) -> QualityReport:
    issues = [*extraction_warnings]
    stripped = text.strip()
    if not stripped:
        issues.append({"code": "empty_extracted_text", "severity": "critical", "message": "No text was extracted."})
    if len(stripped.split()) < 20:
        issues.append({"code": "very_short_document", "severity": "warning", "message": "Document has very little text."})
    if "\ufffd" in text:
        issues.append({"code": "encoding_issue", "severity": "warning", "message": "Replacement characters indicate encoding loss."})
    if re.search(r"\w-\n\w", text):
        issues.append({"code": "hyphenated_line_breaks", "severity": "info", "message": "Hyphenated words across lines detected."})
    if re.search(r"\n{4,}", text):
        issues.append({"code": "excessive_whitespace", "severity": "info", "message": "Repeated blank lines detected."})

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 30]
    duplicates = [value for value, count in Counter(paragraphs).items() if count > 1]
    if duplicates:
        issues.append(
            {
                "code": "duplicate_paragraphs",
                "severity": "warning",
                "message": f"{len(duplicates)} duplicate paragraph(s) detected.",
            }
        )

    for name, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            issues.append({"code": f"potential_{name}", "severity": "critical", "message": f"Potential {name} detected."})

    for name, pattern in PII_PATTERNS.items():
        if pattern.search(text):
            issues.append({"code": f"potential_{name}", "severity": "warning", "message": f"Potential {name} detected."})

    severities = {issue.get("severity", "warning") for issue in issues}
    severity = "critical" if "critical" in severities else "warning" if "warning" in severities else "ok"
    requires_review = severity == "critical" or any(issue["code"].startswith("potential_") for issue in issues)
    summary = "No quality issues detected." if not issues else f"{len(issues)} quality issue(s) detected."
    return QualityReport(issues=issues, severity=severity, requires_review=requires_review, summary=summary)
