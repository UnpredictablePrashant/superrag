from app.services.answer_exports import build_answer_export, requested_export_format


def test_requested_export_format_detects_docx_and_pdf() -> None:
    assert requested_export_format("Please give this as a DOCX") == "docx"
    assert requested_export_format("Export the answer in PDF format") == "pdf"
    assert requested_export_format("Just answer in chat") is None


def test_build_answer_export_creates_docx_and_pdf_bytes() -> None:
    citations = [{"id": 1, "document_name": "Policy", "source_type": "Indexed KB", "preview": "Source text"}]

    docx = build_answer_export(export_format="docx", title="Leave policy", answer="The answer.", citations=citations)
    pdf = build_answer_export(export_format="pdf", title="Leave policy", answer="The answer.", citations=citations)

    assert docx.filename == "Leave-policy.docx"
    assert docx.data.startswith(b"PK")
    assert pdf.filename == "Leave-policy.pdf"
    assert pdf.data.startswith(b"%PDF")
