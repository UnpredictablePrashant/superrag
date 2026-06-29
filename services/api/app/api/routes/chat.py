from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, capability
from app.db.session import SessionLocal, get_db
from app.models.entities import ChatMessage, ChatSession
from app.schemas.api import (
    ChatMessageCreateIn,
    ChatMessageOut,
    ChatSessionCreateIn,
    ChatSessionOut,
    ChatSessionPatchIn,
    ChatTurnOut,
)
from app.services.chat import generate_grounded_answer
from app.services.model_runtime import resolve_chat_model
from app.services.retrieval import retrieve

router = APIRouter(prefix="/chat-sessions", tags=["chat"])


@router.get("", response_model=list[ChatSessionOut])
def list_chat_sessions(
    ctx: AuthContext = Depends(capability("chat")), db: Session = Depends(get_db)
) -> list[ChatSession]:
    return list(
        db.scalars(
            select(ChatSession)
            .where(
                ChatSession.organization_id == ctx.organization_id,
                ChatSession.user_id == ctx.user.id,
                ChatSession.deleted_at.is_(None),
            )
            .order_by(ChatSession.updated_at.desc())
            .limit(50)
        )
    )


@router.post("", response_model=ChatSessionOut)
def create_chat_session(
    payload: ChatSessionCreateIn,
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> ChatSession:
    if payload.model_profile_id:
        resolve_chat_model(db, ctx.organization_id, payload.model_profile_id)
    session = ChatSession(
        organization_id=ctx.organization_id,
        user_id=ctx.user.id,
        title=payload.title,
        knowledge_base_ids=[str(value) for value in payload.knowledge_base_ids],
        retrieval_config=payload.retrieval_config,
        model_profile_id=payload.model_profile_id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/{chat_session_id}", response_model=dict)
def get_chat_session(
    chat_session_id: UUID,
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> dict:
    session = _get_session(db, ctx, chat_session_id)
    messages = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.chat_session_id == session.id)
            .order_by(ChatMessage.created_at)
        )
    )
    return {
        "session": ChatSessionOut.model_validate(session),
        "messages": [ChatMessageOut.model_validate(message) for message in messages],
    }


@router.patch("/{chat_session_id}", response_model=ChatSessionOut)
def patch_chat_session(
    chat_session_id: UUID,
    payload: ChatSessionPatchIn,
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> ChatSession:
    session = _get_session(db, ctx, chat_session_id)
    if payload.title is not None:
        session.title = payload.title
    if payload.knowledge_base_ids is not None:
        session.knowledge_base_ids = [str(value) for value in payload.knowledge_base_ids]
    if payload.retrieval_config is not None:
        session.retrieval_config = payload.retrieval_config
    if payload.model_profile_id is not None:
        resolve_chat_model(db, ctx.organization_id, payload.model_profile_id)
        session.model_profile_id = payload.model_profile_id
    db.commit()
    db.refresh(session)
    return session


@router.delete("/{chat_session_id}")
def delete_chat_session(
    chat_session_id: UUID,
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> dict:
    session = _get_session(db, ctx, chat_session_id)
    session.deleted_at = datetime.now(UTC)
    db.commit()
    return {"message": "Chat deleted."}


@router.post("/{chat_session_id}/messages", response_model=ChatTurnOut)
def create_chat_message(
    chat_session_id: UUID,
    payload: ChatMessageCreateIn,
    ctx: AuthContext = Depends(capability("chat")),
    db: Session = Depends(get_db),
) -> ChatTurnOut:
    session = _get_session(db, ctx, chat_session_id)
    kb_ids = [str(value) for value in payload.knowledge_base_ids] if payload.knowledge_base_ids else session.knowledge_base_ids
    filters = {**session.retrieval_config, **payload.filters}
    user_message = ChatMessage(
        organization_id=ctx.organization_id,
        chat_session_id=session.id,
        role="user",
        content=payload.content,
    )
    db.add(user_message)
    db.flush()
    candidates, event = retrieve(
        db,
        organization_id=ctx.organization_id,
        user_id=ctx.user.id,
        role=ctx.role or "",
        query=payload.content,
        knowledge_base_ids=kb_ids,
        filters=filters,
        debug=payload.debug,
        chat_session_id=session.id,
    )
    chat_model = resolve_chat_model(db, ctx.organization_id, session.model_profile_id)
    try:
        answer = generate_grounded_answer(payload.content, candidates, chat_model)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"Selected chat model failed: {str(exc)[:300]}",
        ) from exc
    assistant_message = ChatMessage(
        organization_id=ctx.organization_id,
        chat_session_id=session.id,
        role="assistant",
        content=answer.answer,
        citations=answer.citations,
        metadata_json={
            "retrieval_event_id": str(event.id),
            "provider": chat_model.provider,
            "model": chat_model.model_name,
            "model_profile_id": chat_model.profile_id,
            "suggested_questions": answer.suggested_questions,
        },
    )
    db.add(assistant_message)
    if session.title == "New chat":
        session.title = payload.content[:80]
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)
    return ChatTurnOut(
        user_message=ChatMessageOut.model_validate(user_message),
        assistant_message=ChatMessageOut.model_validate(assistant_message),
        retrieval_event_id=event.id,
        suggested_questions=answer.suggested_questions,
    )


@router.get("/{chat_session_id}/stream")
def stream_chat_message(
    chat_session_id: UUID,
    message_id: UUID | None = Query(default=None),
    ctx: AuthContext = Depends(capability("chat")),
) -> StreamingResponse:
    def event_stream():
        db = SessionLocal()
        try:
            session = _get_session(db, ctx, chat_session_id)
            query = select(ChatMessage).where(
                ChatMessage.chat_session_id == session.id,
                ChatMessage.role == "assistant",
            )
            if message_id:
                query = query.where(ChatMessage.id == message_id)
            message = db.scalar(query.order_by(ChatMessage.created_at.desc()))
            if not message:
                yield "event: error\ndata: {\"message\":\"No assistant message found.\"}\n\n"
                return
            words = message.content.split(" ")
            buffer = ""
            for word in words:
                buffer += ("" if not buffer else " ") + word
                yield f"event: token\ndata: {json.dumps({'text': word + ' '})}\n\n"
                time.sleep(0.015)
            yield (
                "event: done\ndata: "
                + json.dumps({"message_id": str(message.id), "citations": message.citations, "content": buffer})
                + "\n\n"
            )
        finally:
            db.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _get_session(db: Session, ctx: AuthContext, session_id: UUID) -> ChatSession:
    session = db.get(ChatSession, session_id)
    if (
        not session
        or session.organization_id != ctx.organization_id
        or session.user_id != ctx.user.id
        or session.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Chat session not found.")
    return session
