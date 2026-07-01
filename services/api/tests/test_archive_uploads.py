from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi import HTTPException

from app.api.routes.uploads import _read_archive_members


def test_zip_archive_members_preserve_nested_paths() -> None:
    payload = BytesIO()
    with ZipFile(payload, "w") as archive:
        archive.writestr("Projects/Alpha/brief.md", "# Alpha")
        archive.writestr("__MACOSX/ignored.md", "ignored")
        archive.writestr("Projects/Alpha/image.png", "ignored")

    members = _read_archive_members("upload.zip", payload.getvalue())

    assert [member.path.as_posix() for member in members] == ["Projects/Alpha/brief.md"]
    assert members[0].data == b"# Alpha"


def test_zip_archive_rejects_unsafe_paths() -> None:
    payload = BytesIO()
    with ZipFile(payload, "w") as archive:
        archive.writestr("../escape.md", "bad")

    with pytest.raises(HTTPException):
        _read_archive_members("upload.zip", payload.getvalue())
