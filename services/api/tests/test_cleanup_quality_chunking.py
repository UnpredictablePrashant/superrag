from app.services.chunking import chunk_text, estimate_tokens
from app.services.cleanup import clean_text
from app.services.quality import analyze_quality


def test_standard_cleanup_dehyphenates_and_normalizes_blank_lines() -> None:
    result = clean_text("Policy hy-\nphenation\r\n\r\n\r\nNext paragraph", "standard")
    assert "hyphenation" in result.cleaned_text
    assert "\n\n\n" not in result.cleaned_text


def test_redaction_masks_pii_and_secrets() -> None:
    result = clean_text("Email admin@example.com and password=supersecretvalue", "redaction")
    assert "admin@example.com" not in result.redacted_text
    assert "supersecretvalue" not in result.redacted_text


def test_quality_flags_empty_and_sensitive_content() -> None:
    report = analyze_quality("AWS key AKIAABCDEFGHIJKLMNOP", [])
    assert report.requires_review
    assert any(issue["code"] == "potential_aws_access_key" for issue in report.issues)


def test_recursive_chunking_preserves_text() -> None:
    text = " ".join(f"token{i}" for i in range(300))
    chunks = chunk_text(text, strategy="recursive", chunk_size_tokens=80, overlap_tokens=10)
    assert len(chunks) > 1
    assert all(chunk.token_count >= 1 for chunk in chunks)
    assert sum(estimate_tokens(chunk.text) for chunk in chunks) >= estimate_tokens(text)
