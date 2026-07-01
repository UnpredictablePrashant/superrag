from __future__ import annotations

import mimetypes
from datetime import datetime
from io import BytesIO
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, capability
from app.core.config import settings
from app.core.security import utcnow
from app.db.session import get_db
from app.models.entities import (
    OrganizationMember,
    TeamChatConversation,
    TeamChatMessage,
    TeamChatParticipant,
    User,
)
from app.schemas.api import (
    ChatPresencePatchIn,
    TeamChatConversationCreateIn,
    TeamChatConversationOut,
    TeamChatDirectCreateIn,
    TeamChatMessageCreateIn,
    TeamChatMessageOut,
    TeamChatMessagePatchIn,
    TeamChatParticipantOut,
    TeamChatParticipantsAddIn,
)
from app.services.storage import get_object_bytes, put_object_bytes

router = APIRouter(prefix="/team-chat", tags=["team-chat"])

DEFAULT_PUBLIC_CHANNEL_NAME = "general"
MAX_CHAT_ATTACHMENTS = 10


@router.patch("/presence", response_model=TeamChatParticipantOut)
def update_presence(
    payload: ChatPresencePatchIn,
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> TeamChatParticipantOut:
    member = db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == ctx.organization_id,
            OrganizationMember.user_id == ctx.user.id,
            OrganizationMember.status == "active",
        )
    )
    if not member:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Active organization member not found.")
    member.chat_status = payload.chat_status
    member.status_message = payload.status_message.strip() if payload.status_message else None
    member.status_updated_at = utcnow()
    db.commit()
    db.refresh(member)
    return TeamChatParticipantOut(
        user_id=ctx.user.id,
        email=ctx.user.email,
        full_name=ctx.user.full_name,
        role="member",
        chat_status=member.chat_status,
        status_message=member.status_message,
        status_updated_at=member.status_updated_at,
    )


@router.get("/conversations", response_model=list[TeamChatConversationOut])
def list_conversations(
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> list[TeamChatConversationOut]:
    _ensure_default_public_channel(db, ctx.organization_id, ctx.user.id)
    rows = db.execute(
        select(TeamChatConversation)
        .join(TeamChatParticipant, TeamChatParticipant.conversation_id == TeamChatConversation.id)
        .where(
            TeamChatConversation.organization_id == ctx.organization_id,
            TeamChatConversation.is_archived.is_(False),
            TeamChatParticipant.user_id == ctx.user.id,
        )
        .order_by(TeamChatConversation.last_message_at.desc().nullslast(), TeamChatConversation.created_at.desc())
    ).scalars()
    return [_conversation_out(db, conversation, ctx.user.id) for conversation in rows]


@router.post("/channels", response_model=TeamChatConversationOut)
def create_channel(
    payload: TeamChatConversationCreateIn,
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> TeamChatConversationOut:
    user_ids = _active_member_user_ids(db, ctx.organization_id, set(payload.member_user_ids) | {ctx.user.id})
    conversation = TeamChatConversation(
        organization_id=ctx.organization_id,
        kind="channel",
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        created_by_user_id=ctx.user.id,
        last_message_at=utcnow(),
    )
    db.add(conversation)
    db.flush()
    for user_id in user_ids:
        db.add(
            TeamChatParticipant(
                organization_id=ctx.organization_id,
                conversation_id=conversation.id,
                user_id=user_id,
                role="owner" if user_id == ctx.user.id else "member",
                last_read_at=utcnow() if user_id == ctx.user.id else None,
            )
        )
    db.commit()
    db.refresh(conversation)
    return _conversation_out(db, conversation, ctx.user.id)


@router.post("/direct", response_model=TeamChatConversationOut)
def create_direct_conversation(
    payload: TeamChatDirectCreateIn,
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> TeamChatConversationOut:
    if payload.user_id == ctx.user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Choose another member to start a direct message.")
    user_ids = _active_member_user_ids(db, ctx.organization_id, {ctx.user.id, payload.user_id})
    direct_key = _direct_conversation_key(user_ids)
    conversation = db.scalar(
        select(TeamChatConversation).where(
            TeamChatConversation.organization_id == ctx.organization_id,
            TeamChatConversation.direct_key == direct_key,
        )
    )
    if not conversation:
        conversation = TeamChatConversation(
            organization_id=ctx.organization_id,
            kind="direct",
            created_by_user_id=ctx.user.id,
            direct_key=direct_key,
            last_message_at=utcnow(),
        )
        db.add(conversation)
        db.flush()
        for user_id in user_ids:
            db.add(
                TeamChatParticipant(
                    organization_id=ctx.organization_id,
                    conversation_id=conversation.id,
                    user_id=user_id,
                    role="member",
                    last_read_at=utcnow() if user_id == ctx.user.id else None,
                )
            )
        db.commit()
        db.refresh(conversation)
    return _conversation_out(db, conversation, ctx.user.id)


@router.post("/conversations/{conversation_id}/participants", response_model=TeamChatConversationOut)
def add_participants(
    conversation_id: UUID,
    payload: TeamChatParticipantsAddIn,
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> TeamChatConversationOut:
    conversation = _get_conversation_for_user(db, ctx, conversation_id)
    if conversation.kind != "channel":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Direct message participants cannot be changed.")
    user_ids = _active_member_user_ids(db, ctx.organization_id, set(payload.user_ids))
    existing_user_ids = set(
        db.scalars(
            select(TeamChatParticipant.user_id).where(TeamChatParticipant.conversation_id == conversation.id)
        )
    )
    for user_id in user_ids:
        if user_id not in existing_user_ids:
            db.add(
                TeamChatParticipant(
                    organization_id=ctx.organization_id,
                    conversation_id=conversation.id,
                    user_id=user_id,
                    role="member",
                )
            )
    db.commit()
    db.refresh(conversation)
    return _conversation_out(db, conversation, ctx.user.id)


@router.get("/conversations/{conversation_id}/messages", response_model=list[TeamChatMessageOut])
def list_messages(
    conversation_id: UUID,
    before: datetime | None = Query(default=None),
    limit: int = Query(default=80, ge=1, le=200),
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> list[TeamChatMessageOut]:
    conversation = _get_conversation_for_user(db, ctx, conversation_id)
    query = (
        select(TeamChatMessage, User)
        .join(User, User.id == TeamChatMessage.user_id)
        .where(TeamChatMessage.conversation_id == conversation.id)
        .order_by(TeamChatMessage.created_at.desc())
        .limit(limit)
    )
    if before:
        query = query.where(TeamChatMessage.created_at < before)
    rows = list(db.execute(query).all())
    return [_message_out(message, user) for message, user in reversed(rows)]


@router.post("/conversations/{conversation_id}/messages", response_model=TeamChatMessageOut)
def create_message(
    conversation_id: UUID,
    payload: TeamChatMessageCreateIn,
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> TeamChatMessageOut:
    conversation = _get_conversation_for_user(db, ctx, conversation_id)
    content = payload.content.strip()
    if not content or payload.message_type != "text":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Message content is required.")
    message = TeamChatMessage(
        organization_id=ctx.organization_id,
        conversation_id=conversation.id,
        user_id=ctx.user.id,
        content=content,
        message_type="text",
        attachments=[],
    )
    _commit_created_message(db, conversation, message, ctx.user.id)
    return _message_out(message, ctx.user)


@router.post("/conversations/{conversation_id}/messages/upload", response_model=TeamChatMessageOut)
def create_upload_message(
    conversation_id: UUID,
    content: str = Form(default=""),
    message_type: str = Form(default="attachment"),
    files: list[UploadFile] = File(...),
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> TeamChatMessageOut:
    conversation = _get_conversation_for_user(db, ctx, conversation_id)
    if message_type not in {"attachment", "voice"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported upload message type.")
    if not files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Attach at least one file.")
    if len(files) > MAX_CHAT_ATTACHMENTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Attach up to {MAX_CHAT_ATTACHMENTS} files.")
    if message_type == "voice" and len(files) != 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Voice messages must contain one audio file.")

    attachments = []
    for file in files:
        filename = _safe_attachment_filename(file.filename or "attachment")
        content_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        if message_type == "voice" and not content_type.startswith("audio/"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Voice messages must be audio uploads.")
        data = _read_upload_bytes(file)
        if not data:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Attachment cannot be empty.")
        attachment_id = str(uuid4())
        object_key = _attachment_object_key(ctx.organization_id, conversation.id, attachment_id, filename)
        put_object_bytes(object_key, data, content_type)
        attachments.append(
            {
                "id": attachment_id,
                "filename": filename,
                "content_type": content_type,
                "size_bytes": len(data),
                "kind": "voice" if message_type == "voice" else "attachment",
                "object_key": object_key,
            }
        )

    message = TeamChatMessage(
        organization_id=ctx.organization_id,
        conversation_id=conversation.id,
        user_id=ctx.user.id,
        content=content.strip(),
        message_type=message_type,
        attachments=attachments,
    )
    _commit_created_message(db, conversation, message, ctx.user.id)
    return _message_out(message, ctx.user)


@router.get("/conversations/{conversation_id}/messages/{message_id}/attachments/{attachment_id}")
def download_attachment(
    conversation_id: UUID,
    message_id: UUID,
    attachment_id: str,
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    _get_conversation_for_user(db, ctx, conversation_id)
    message = _get_message(db, ctx, conversation_id, message_id)
    if message.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attachment not found.")
    attachment = next(
        (item for item in message.attachments if str(item.get("id")) == attachment_id),
        None,
    )
    if not attachment or not attachment.get("object_key"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attachment not found.")
    data = get_object_bytes(str(attachment["object_key"]))
    filename = _safe_attachment_filename(str(attachment.get("filename") or "attachment"))
    content_type = str(attachment.get("content_type") or "application/octet-stream")
    disposition = "inline" if content_type.startswith("audio/") else "attachment"
    return StreamingResponse(
        BytesIO(data),
        media_type=content_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.patch("/conversations/{conversation_id}/messages/{message_id}", response_model=TeamChatMessageOut)
def patch_message(
    conversation_id: UUID,
    message_id: UUID,
    payload: TeamChatMessagePatchIn,
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> TeamChatMessageOut:
    _get_conversation_for_user(db, ctx, conversation_id)
    message = _get_message(db, ctx, conversation_id, message_id)
    if message.user_id != ctx.user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the sender can edit this message.")
    if message.deleted_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Deleted messages cannot be edited.")
    content = payload.content.strip()
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Message content is required.")
    message.content = content
    message.edited_at = utcnow()
    db.commit()
    db.refresh(message)
    return _message_out(message, ctx.user)


@router.delete("/conversations/{conversation_id}/messages/{message_id}", response_model=TeamChatMessageOut)
def delete_message(
    conversation_id: UUID,
    message_id: UUID,
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> TeamChatMessageOut:
    _get_conversation_for_user(db, ctx, conversation_id)
    message = _get_message(db, ctx, conversation_id, message_id)
    if message.user_id != ctx.user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the sender can delete this message.")
    message.deleted_at = utcnow()
    db.commit()
    db.refresh(message)
    return _message_out(message, ctx.user)


@router.post("/conversations/{conversation_id}/read", response_model=TeamChatConversationOut)
def mark_conversation_read(
    conversation_id: UUID,
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> TeamChatConversationOut:
    conversation = _get_conversation_for_user(db, ctx, conversation_id)
    participant = _get_participant(db, conversation.id, ctx.user.id)
    if participant:
        participant.last_read_at = utcnow()
        db.commit()
        db.refresh(conversation)
    return _conversation_out(db, conversation, ctx.user.id)


def _get_conversation_for_user(db: Session, ctx: AuthContext, conversation_id: UUID) -> TeamChatConversation:
    conversation = db.get(TeamChatConversation, conversation_id)
    if not conversation or conversation.organization_id != ctx.organization_id or conversation.is_archived:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    if not _get_participant(db, conversation.id, ctx.user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conversation


def _get_participant(db: Session, conversation_id: UUID, user_id: UUID) -> TeamChatParticipant | None:
    return db.scalar(
        select(TeamChatParticipant).where(
            TeamChatParticipant.conversation_id == conversation_id,
            TeamChatParticipant.user_id == user_id,
        )
    )


def _get_message(db: Session, ctx: AuthContext, conversation_id: UUID, message_id: UUID) -> TeamChatMessage:
    message = db.get(TeamChatMessage, message_id)
    if not message or message.organization_id != ctx.organization_id or message.conversation_id != conversation_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Message not found.")
    return message


def _commit_created_message(
    db: Session,
    conversation: TeamChatConversation,
    message: TeamChatMessage,
    user_id: UUID,
) -> None:
    conversation.last_message_at = utcnow()
    participant = _get_participant(db, conversation.id, user_id)
    if participant:
        participant.last_read_at = utcnow()
    db.add(message)
    db.commit()
    db.refresh(message)


def _active_member_user_ids(db: Session, organization_id: UUID, user_ids: set[UUID]) -> list[UUID]:
    if not user_ids:
        return []
    active_ids = list(
        db.scalars(
            select(OrganizationMember.user_id).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.status == "active",
                OrganizationMember.user_id.in_(user_ids),
            )
        )
    )
    if len(set(active_ids)) != len(user_ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Every chat participant must be an active organization member.")
    return sorted(active_ids, key=lambda value: str(value))


def _conversation_out(db: Session, conversation: TeamChatConversation, current_user_id: UUID) -> TeamChatConversationOut:
    participants = _participant_outs(db, conversation.id)
    latest = _latest_message_out(db, conversation.id)
    last_read_at = db.scalar(
        select(TeamChatParticipant.last_read_at).where(
            TeamChatParticipant.conversation_id == conversation.id,
            TeamChatParticipant.user_id == current_user_id,
        )
    )
    unread_query = select(func.count(TeamChatMessage.id)).where(
        TeamChatMessage.conversation_id == conversation.id,
        TeamChatMessage.user_id != current_user_id,
        TeamChatMessage.deleted_at.is_(None),
    )
    if last_read_at:
        unread_query = unread_query.where(TeamChatMessage.created_at > last_read_at)
    unread_count = db.scalar(unread_query) or 0
    return TeamChatConversationOut(
        id=conversation.id,
        kind=conversation.kind,  # type: ignore[arg-type]
        name=conversation.name,
        description=conversation.description,
        created_by_user_id=conversation.created_by_user_id,
        is_public=conversation.is_public,
        is_default=conversation.is_default,
        is_archived=conversation.is_archived,
        last_message_at=conversation.last_message_at,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        participants=participants,
        unread_count=unread_count,
        latest_message=latest,
    )


def _participant_outs(db: Session, conversation_id: UUID) -> list[TeamChatParticipantOut]:
    rows = db.execute(
        select(TeamChatParticipant, User, OrganizationMember)
        .join(User, User.id == TeamChatParticipant.user_id)
        .join(
            OrganizationMember,
            (OrganizationMember.organization_id == TeamChatParticipant.organization_id)
            & (OrganizationMember.user_id == TeamChatParticipant.user_id),
        )
        .where(TeamChatParticipant.conversation_id == conversation_id)
        .order_by(User.full_name.nullslast(), User.email)
    ).all()
    return [
        TeamChatParticipantOut(
            user_id=participant.user_id,
            email=user.email,
            full_name=user.full_name,
            role=participant.role,
            chat_status=member.chat_status,
            status_message=member.status_message,
            status_updated_at=member.status_updated_at,
            last_read_at=participant.last_read_at,
        )
        for participant, user, member in rows
    ]


def _latest_message_out(db: Session, conversation_id: UUID) -> TeamChatMessageOut | None:
    row = db.execute(
        select(TeamChatMessage, User)
        .join(User, User.id == TeamChatMessage.user_id)
        .where(TeamChatMessage.conversation_id == conversation_id)
        .order_by(TeamChatMessage.created_at.desc())
        .limit(1)
    ).first()
    if not row:
        return None
    message, user = row
    return _message_out(message, user)


def _message_out(message: TeamChatMessage, user: User) -> TeamChatMessageOut:
    attachments = [] if message.deleted_at else [_attachment_out(message, item) for item in message.attachments]
    return TeamChatMessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        user_id=message.user_id,
        email=user.email,
        full_name=user.full_name,
        content="This message was deleted." if message.deleted_at else message.content,
        message_type="text" if message.deleted_at else message.message_type,  # type: ignore[arg-type]
        attachments=attachments,
        edited_at=message.edited_at,
        deleted_at=message.deleted_at,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )


def _attachment_out(message: TeamChatMessage, attachment: dict) -> dict:
    attachment_id = str(attachment.get("id") or "")
    return {
        "id": attachment_id,
        "filename": str(attachment.get("filename") or "attachment"),
        "content_type": attachment.get("content_type"),
        "size_bytes": int(attachment.get("size_bytes") or 0),
        "kind": attachment.get("kind") or "attachment",
        "download_url": (
            f"/team-chat/conversations/{message.conversation_id}/messages/{message.id}/attachments/{attachment_id}"
        ),
    }


def _ensure_default_public_channel(db: Session, organization_id: UUID, current_user_id: UUID) -> TeamChatConversation | None:
    active_user_ids = list(
        db.scalars(
            select(OrganizationMember.user_id).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.status == "active",
            )
        )
    )
    if not active_user_ids:
        return None
    conversation = db.scalar(
        select(TeamChatConversation).where(
            TeamChatConversation.organization_id == organization_id,
            TeamChatConversation.is_default.is_(True),
            TeamChatConversation.is_archived.is_(False),
        )
    )
    changed = False
    if not conversation:
        conversation = TeamChatConversation(
            organization_id=organization_id,
            kind="channel",
            name=DEFAULT_PUBLIC_CHANNEL_NAME,
            description="Company-wide public channel for everyone in the organization.",
            created_by_user_id=current_user_id if current_user_id in active_user_ids else active_user_ids[0],
            is_public=True,
            is_default=True,
            last_message_at=utcnow(),
        )
        db.add(conversation)
        db.flush()
        changed = True
    elif not conversation.is_public:
        conversation.is_public = True
        changed = True

    existing_user_ids = set(
        db.scalars(select(TeamChatParticipant.user_id).where(TeamChatParticipant.conversation_id == conversation.id))
    )
    for user_id in active_user_ids:
        if user_id not in existing_user_ids:
            db.add(
                TeamChatParticipant(
                    organization_id=organization_id,
                    conversation_id=conversation.id,
                    user_id=user_id,
                    role="owner" if user_id == conversation.created_by_user_id else "member",
                )
            )
            changed = True
    if changed:
        db.commit()
        db.refresh(conversation)
    return conversation


def _direct_conversation_key(user_ids: list[UUID]) -> str:
    return ":".join(sorted(str(user_id) for user_id in user_ids))


def _safe_attachment_filename(filename: str) -> str:
    return PurePosixPath(filename).name.replace("\\", "_").replace("/", "_").replace('"', "_") or "attachment"


def _attachment_object_key(organization_id: UUID, conversation_id: UUID, attachment_id: str, filename: str) -> str:
    return (
        f"organizations/{organization_id}/team-chat/conversations/{conversation_id}/"
        f"attachments/{attachment_id}/{filename}"
    )


def _read_upload_bytes(file: UploadFile) -> bytes:
    data = bytearray()
    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Upload is too large.")
    return bytes(data)
