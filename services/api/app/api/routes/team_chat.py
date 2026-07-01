from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, capability
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

router = APIRouter(prefix="/team-chat", tags=["team-chat"])


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
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Message content is required.")
    message = TeamChatMessage(
        organization_id=ctx.organization_id,
        conversation_id=conversation.id,
        user_id=ctx.user.id,
        content=content,
    )
    conversation.last_message_at = utcnow()
    participant = _get_participant(db, conversation.id, ctx.user.id)
    if participant:
        participant.last_read_at = utcnow()
    db.add(message)
    db.commit()
    db.refresh(message)
    return _message_out(message, ctx.user)


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
    return TeamChatMessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        user_id=message.user_id,
        email=user.email,
        full_name=user.full_name,
        content="This message was deleted." if message.deleted_at else message.content,
        edited_at=message.edited_at,
        deleted_at=message.deleted_at,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )


def _direct_conversation_key(user_ids: list[UUID]) -> str:
    return ":".join(sorted(str(user_id) for user_id in user_ids))
