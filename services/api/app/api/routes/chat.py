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
from app.core.permissions import require_capability
from app.db.session import SessionLocal, get_db
from app.models.entities import ChatMessage, ChatSession, KnowledgeBase, RetrievalEvent
from app.schemas.api import (
    ChatMessageCreateIn,
    ChatMessageOut,
    ChatSessionCreateIn,
    ChatSessionOut,
    ChatSessionPatchIn,
    ChatTurnOut,
)
from app.services.chat import generate_grounded_answer
from app.services.connectors import live_connector_candidates
from app.services.model_runtime import resolve_chat_model
from app.services.retrieval import Candidate, retrieve

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
    retrieval_config = payload.retrieval_config or _default_retrieval_config(
        db, ctx.organization_id, payload.knowledge_base_ids
    )
    session = ChatSession(
        organization_id=ctx.organization_id,
        user_id=ctx.user.id,
        title=payload.title,
        knowledge_base_ids=[str(value) for value in payload.knowledge_base_ids],
        retrieval_config=retrieval_config,
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
    if "model_profile_id" in payload.model_fields_set:
        if payload.model_profile_id is None:
            session.model_profile_id = None
        else:
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
    answer_mode, use_web_search, use_mcp_tools, indexed_scope = _resolve_answer_mode(payload)
    kb_ids = [str(value) for value in payload.knowledge_base_ids] if payload.knowledge_base_ids else session.knowledge_base_ids
    session_retrieval_config = session.retrieval_config or _default_retrieval_config(db, ctx.organization_id, kb_ids)
    filters = {**session_retrieval_config, **payload.filters}
    filters["answer_mode"] = answer_mode
    if use_web_search:
        filters["use_web_search"] = True
    if use_mcp_tools:
        filters["use_mcp_tools"] = True
    if payload.connector_connection_ids:
        filters["connector_connection_ids"] = [str(value) for value in payload.connector_connection_ids]
    user_message = ChatMessage(
        organization_id=ctx.organization_id,
        chat_session_id=session.id,
        role="user",
        content=payload.content,
    )
    db.add(user_message)
    db.flush()
    if indexed_scope:
        try:
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
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Retrieval failed before an answer could be generated: {str(exc)[:300]}",
            ) from exc
    else:
        candidates = []
        event = RetrievalEvent(
            organization_id=ctx.organization_id,
            user_id=ctx.user.id,
            chat_session_id=session.id,
            original_query=payload.content,
            rewritten_query=payload.content.strip(),
            applied_filters={"knowledge_base_ids": [], **filters},
            vector_candidates=[],
            keyword_candidates=[],
            rrf_ranking=[],
            reranker_scores=[],
            final_context_chunks=[],
            token_usage={"estimated_context_tokens": 0},
            latency_ms_by_stage={},
        )
        db.add(event)
    db.flush()
    if filters.get("use_web_search") or filters.get("use_mcp_tools"):
        require_capability(ctx.role or "", "use_live_tools")
        try:
            live_candidates = live_connector_candidates(
                db,
                organization_id=ctx.organization_id,
                user_id=ctx.user.id,
                query=payload.content,
                use_web_search=use_web_search,
                use_mcp_tools=use_mcp_tools,
                connector_connection_ids=[str(value) for value in filters.get("connector_connection_ids", [])],
                chat_session_id=session.id,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail=f"Live tool retrieval failed: {str(exc)[:300]}",
            ) from exc
        candidates = _merge_live_candidates(candidates, live_candidates)
        if live_candidates:
            event.applied_filters = {
                **event.applied_filters,
                "use_web_search": bool(filters.get("use_web_search")),
                "use_mcp_tools": bool(filters.get("use_mcp_tools")),
                "connector_connection_ids": [str(value) for value in filters.get("connector_connection_ids", [])],
            }
            event.final_context_chunks = [
                *event.final_context_chunks,
                *[_candidate_debug(candidate) for candidate in live_candidates],
            ]
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


def _merge_live_candidates(indexed: list[Candidate], live: list[Candidate]) -> list[Candidate]:
    if not live:
        return indexed
    return sorted([*indexed, *live], key=lambda candidate: candidate.score, reverse=True)


def _candidate_debug(candidate: Candidate) -> dict:
    return {
        "chunk_id": candidate.chunk_id,
        "document_id": candidate.document_id,
        "document_name": candidate.document_name,
        "score": candidate.score,
        "source": candidate.source,
        "preview": candidate.text[:280],
        "metadata": candidate.metadata,
    }


def _resolve_answer_mode(payload: ChatMessageCreateIn) -> tuple[str, bool, bool, bool]:
    if payload.answer_mode == "company_data":
        return "company_data", False, False, True
    if payload.answer_mode == "live_web":
        return "live_web", True, False, False
    if payload.answer_mode == "mcp_tools":
        return "mcp_tools", False, True, False
    if payload.answer_mode == "blended":
        return "blended", True, True, True
    if payload.use_web_search or payload.use_mcp_tools:
        return "blended", payload.use_web_search, payload.use_mcp_tools, True
    return "company_data", False, False, True


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


def _default_retrieval_config(db: Session, organization_id: UUID, knowledge_base_ids: list[UUID | str]) -> dict:
    if not knowledge_base_ids:
        return {}
    try:
        kb_id = UUID(str(knowledge_base_ids[0]))
    except ValueError:
        return {}
    kb = db.get(KnowledgeBase, kb_id)
    if not kb or kb.organization_id != organization_id or kb.deleted_at is not None:
        return {}
    return dict(kb.default_retrieval_config or {})
