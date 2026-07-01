from __future__ import annotations

from uuid import uuid4

from app.api.routes.team_chat import _attachment_out, _direct_conversation_key, _message_out
from app.core.security import utcnow
from app.models.entities import TeamChatMessage, User


def test_direct_conversation_key_is_stable_for_member_pair() -> None:
    first_user_id = uuid4()
    second_user_id = uuid4()

    assert _direct_conversation_key([first_user_id, second_user_id]) == _direct_conversation_key(
        [second_user_id, first_user_id]
    )


def test_deleted_team_chat_message_does_not_expose_original_content() -> None:
    now = utcnow()
    user_id = uuid4()
    message = TeamChatMessage(
        id=uuid4(),
        organization_id=uuid4(),
        conversation_id=uuid4(),
        user_id=user_id,
        content="sensitive draft",
        deleted_at=now,
        created_at=now,
        updated_at=now,
    )
    user = User(id=user_id, email="member@example.com", full_name="Member Example")

    output = _message_out(message, user)

    assert output.content == "This message was deleted."
    assert output.email == "member@example.com"
    assert output.attachments == []


def test_team_chat_attachment_output_uses_guarded_download_url() -> None:
    now = utcnow()
    message = TeamChatMessage(
        id=uuid4(),
        organization_id=uuid4(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        content="",
        message_type="voice",
        attachments=[],
        created_at=now,
        updated_at=now,
    )

    output = _attachment_out(
        message,
        {
            "id": "voice-1",
            "filename": "voice.webm",
            "content_type": "audio/webm",
            "size_bytes": 2048,
            "kind": "voice",
            "object_key": "private/object/key",
        },
    )

    assert output == {
        "id": "voice-1",
        "filename": "voice.webm",
        "content_type": "audio/webm",
        "size_bytes": 2048,
        "kind": "voice",
        "download_url": f"/team-chat/conversations/{message.conversation_id}/messages/{message.id}/attachments/voice-1",
    }
