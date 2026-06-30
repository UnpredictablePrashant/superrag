from uuid import UUID

from app.api.routes.documents import _record_quality_review_override


def test_record_quality_review_override_tracks_document_version() -> None:
    class Document:
        version_number = 4
        checksum = "checksum-4"
        custom_metadata = {"existing": True}

    document = Document()
    user_id = UUID("00000000-0000-0000-0000-000000000001")

    _record_quality_review_override(document, "continue_unchanged", user_id)

    override = document.custom_metadata["quality_review_override"]
    assert document.custom_metadata["existing"] is True
    assert override["action"] == "continue_unchanged"
    assert override["approved_by_user_id"] == str(user_id)
    assert override["version_number"] == 4
    assert override["checksum"] == "checksum-4"
