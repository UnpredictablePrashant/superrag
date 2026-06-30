from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.models.entities import (
    ConfidentialityLevel,
    OrganizationMember,
    TelegramAllowedUser,
    TelegramIntegration,
    TelegramMessageLog,
)
from app.services.chat import complete_with_chat_model, generate_grounded_answer
from app.services.cleanup import clean_text
from app.services.document_ingestion import (
    create_uploaded_document_from_bytes,
    queue_pipeline_for_documents,
)
from app.services.model_runtime import get_openai_connection, resolve_chat_model
from app.services.retrieval import retrieve
from app.services.telegram_client import TelegramClient
from app.services.transcription import transcribe_audio_openai


def process_telegram_update(db: Session, integration: TelegramIntegration, update: dict[str, Any]) -> None:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    chat_id = str(message.get("chat", {}).get("id") or "")
    message_id = int(message.get("message_id") or 0)
    if not chat_id or not message_id:
        return
    existing = db.scalar(
        select(TelegramMessageLog).where(
            TelegramMessageLog.integration_id == integration.id,
            TelegramMessageLog.telegram_chat_id == chat_id,
            TelegramMessageLog.telegram_message_id == message_id,
        )
    )
    if existing and existing.status not in {"queued", "received"}:
        return
    source_type = _source_type(message)
    mode = _message_mode(message)
    sender = message.get("from") or {}
    sender_id = sender.get("id")
    if existing:
        log = existing
        log.mode = mode
        log.source_type = source_type
        log.payload = {"update_id": update.get("update_id"), "from": sender, "source": source_type}
    else:
        log = TelegramMessageLog(
            organization_id=integration.organization_id,
            integration_id=integration.id,
            telegram_chat_id=chat_id,
            telegram_message_id=message_id,
            telegram_user_id=int(sender_id) if sender_id else None,
            mode=mode,
            source_type=source_type,
            payload={"update_id": update.get("update_id"), "from": sender, "source": source_type},
        )
        db.add(log)
    db.flush()
    client = _client(integration)
    try:
        allowed = _authorize_sender(db, integration, message)
        if not allowed:
            log.status = "rejected"
            client.send_message(chat_id, "This Telegram account is not allowed to use this RAG bot.")
            db.commit()
            return
        if mode == "help":
            log.status = "completed"
            client.send_message(chat_id, _help_text())
            db.commit()
            return
        if mode == "ask":
            if not allowed.can_query:
                raise ValueError("This Telegram user is not allowed to ask questions.")
            answer = _answer_question(db, integration, allowed, _command_body(message, "/ask"))
            log.status = "completed"
            client.send_message(chat_id, answer)
            db.commit()
            return
        if not allowed.can_ingest:
            raise ValueError("This Telegram user is not allowed to add content.")
        document, run = _ingest_message(db, integration, allowed, message, source_type)
        log.document_id = document.id
        log.pipeline_run_id = run.id
        log.status = "completed"
        client.send_message(
            chat_id,
            f"Added to RAG: {document.name}\nIngestion run queued: {run.id}",
        )
    except Exception as exc:
        log.status = "failed"
        log.error = str(exc)[:1000]
        client.send_message(chat_id, f"Telegram RAG action failed: {str(exc)[:700]}")
    finally:
        db.commit()


def record_telegram_update_receipt(
    db: Session,
    integration: TelegramIntegration,
    update: dict[str, Any],
) -> TelegramMessageLog | None:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return None
    chat_id = str(message.get("chat", {}).get("id") or "")
    message_id = int(message.get("message_id") or 0)
    if not chat_id or not message_id:
        return None
    existing = db.scalar(
        select(TelegramMessageLog).where(
            TelegramMessageLog.integration_id == integration.id,
            TelegramMessageLog.telegram_chat_id == chat_id,
            TelegramMessageLog.telegram_message_id == message_id,
        )
    )
    source_type = _source_type(message)
    mode = _message_mode(message)
    sender = message.get("from") or {}
    sender_id = sender.get("id")
    payload = {"update_id": update.get("update_id"), "from": sender, "source": source_type}
    if existing:
        if existing.status in {"received", "queued"}:
            existing.status = "queued"
            existing.mode = mode
            existing.source_type = source_type
            existing.payload = payload
        db.flush()
        return existing
    log = TelegramMessageLog(
        organization_id=integration.organization_id,
        integration_id=integration.id,
        telegram_chat_id=chat_id,
        telegram_message_id=message_id,
        telegram_user_id=int(sender_id) if sender_id else None,
        mode=mode,
        source_type=source_type,
        status="queued",
        payload=payload,
    )
    db.add(log)
    db.flush()
    return log


def register_telegram_webhook(integration: TelegramIntegration, webhook_url: str) -> dict[str, Any]:
    return _client(integration).set_webhook(webhook_url, integration.webhook_secret_token)


def test_telegram_bot(integration: TelegramIntegration) -> dict[str, Any]:
    return _client(integration).get_me()


def build_webhook_url(api_base_url: str, integration_id: UUID) -> str:
    return f"{api_base_url.rstrip('/')}/api/integrations/telegram/webhook/{integration_id}"


def _client(integration: TelegramIntegration) -> TelegramClient:
    if not integration.encrypted_bot_token:
        raise ValueError("Telegram bot token is not configured.")
    return TelegramClient(decrypt_secret(integration.encrypted_bot_token))


def _source_type(message: dict[str, Any]) -> str:
    if message.get("voice"):
        return "voice"
    if message.get("audio"):
        return "audio"
    if message.get("document"):
        return "document"
    if message.get("contact"):
        return "contact"
    return "text"


def _message_mode(message: dict[str, Any]) -> str:
    text = str(message.get("text") or message.get("caption") or "").strip()
    if text.startswith("/help") or text.startswith("/start"):
        return "help"
    if text.startswith("/ask"):
        return "ask"
    return "ingest"


def _authorize_sender(
    db: Session,
    integration: TelegramIntegration,
    message: dict[str, Any],
) -> TelegramAllowedUser | None:
    sender = message.get("from") or {}
    telegram_user_id = sender.get("id")
    username = _normalize_username(sender.get("username"))
    phone_number = _contact_phone(message, telegram_user_id)
    clauses = []
    if telegram_user_id:
        clauses.append(TelegramAllowedUser.telegram_user_id == int(telegram_user_id))
    if username:
        clauses.append(TelegramAllowedUser.username == username)
    if phone_number:
        clauses.append(TelegramAllowedUser.phone_number == phone_number)
    if not clauses:
        return None
    allowed = db.scalar(
        select(TelegramAllowedUser).where(
            TelegramAllowedUser.integration_id == integration.id,
            TelegramAllowedUser.deleted_at.is_(None),
            TelegramAllowedUser.is_enabled.is_(True),
            *clauses[:1],
        )
    )
    for clause in clauses[1:]:
        if allowed:
            break
        allowed = db.scalar(
            select(TelegramAllowedUser).where(
                TelegramAllowedUser.integration_id == integration.id,
                TelegramAllowedUser.deleted_at.is_(None),
                TelegramAllowedUser.is_enabled.is_(True),
                clause,
            )
        )
    if allowed and telegram_user_id and not allowed.telegram_user_id:
        allowed.telegram_user_id = int(telegram_user_id)
    return allowed


def _ingest_message(
    db: Session,
    integration: TelegramIntegration,
    allowed: TelegramAllowedUser,
    message: dict[str, Any],
    source_type: str,
):
    if not integration.default_knowledge_base_id:
        raise ValueError("Configure a default knowledge base for Telegram ingestion first.")
    if source_type == "document":
        if not integration.auto_ingest_documents:
            raise ValueError("Telegram document ingestion is disabled.")
        data, filename, content_type = _download_document(integration, message["document"])
        document = create_uploaded_document_from_bytes(
            db,
            organization_id=integration.organization_id,
            knowledge_base_id=integration.default_knowledge_base_id,
            filename=filename,
            data=data,
            content_type=content_type,
            uploaded_by_user_id=allowed.user_id,
            confidentiality=ConfidentialityLevel.INTERNAL,
            source_url=f"telegram:{message.get('message_id')}",
            custom_metadata=_telegram_metadata(message, source_type),
        )
    else:
        text, raw_text = _text_for_ingestion(db, integration, message, source_type)
        filename = _generated_note_filename(source_type, message)
        body = _markdown_note(text, raw_text, message, source_type)
        document = create_uploaded_document_from_bytes(
            db,
            organization_id=integration.organization_id,
            knowledge_base_id=integration.default_knowledge_base_id,
            filename=filename,
            data=body.encode("utf-8"),
            content_type="text/markdown",
            uploaded_by_user_id=allowed.user_id,
            confidentiality=ConfidentialityLevel.INTERNAL,
            source_url=f"telegram:{message.get('message_id')}",
            custom_metadata=_telegram_metadata(message, source_type),
        )
    run = queue_pipeline_for_documents(
        db,
        organization_id=integration.organization_id,
        knowledge_base_id=integration.default_knowledge_base_id,
        document_ids=[document.id],
        cleanup_profile_id=integration.default_cleanup_profile_id,
        chunking_profile_id=integration.default_chunking_profile_id,
        embedding_profile_id=integration.default_embedding_profile_id,
    )
    return document, run


def _download_document(
    integration: TelegramIntegration,
    document_payload: dict[str, Any],
) -> tuple[bytes, str, str | None]:
    client = _client(integration)
    file_info = client.get_file(document_payload["file_id"])
    file_path = file_info["file_path"]
    filename = PurePosixPath(document_payload.get("file_name") or file_path).name
    return client.download_file(file_path), filename, document_payload.get("mime_type")


def _text_for_ingestion(
    db: Session,
    integration: TelegramIntegration,
    message: dict[str, Any],
    source_type: str,
) -> tuple[str, str]:
    if source_type in {"voice", "audio"}:
        if not integration.auto_ingest_voice:
            raise ValueError("Telegram voice ingestion is disabled.")
        raw_text = _transcribe_message_audio(db, integration, message, source_type)
    else:
        if not integration.auto_ingest_text:
            raise ValueError("Telegram text ingestion is disabled.")
        raw_text = _command_body(message, "/add") or str(message.get("text") or "").strip()
    if not raw_text:
        raise ValueError("No text was found to ingest.")
    return _refine_text(db, integration, raw_text, source_type), raw_text


def _transcribe_message_audio(
    db: Session,
    integration: TelegramIntegration,
    message: dict[str, Any],
    source_type: str,
) -> str:
    payload = message[source_type]
    openai = get_openai_connection(db, integration.organization_id)
    if not openai:
        raise ValueError("Voice transcription requires an enabled OpenAI provider connection.")
    api_key, base_url = openai
    client = _client(integration)
    file_info = client.get_file(payload["file_id"])
    file_path = file_info["file_path"]
    filename = PurePosixPath(file_path).name or f"telegram-{source_type}.ogg"
    data = client.download_file(file_path)
    return transcribe_audio_openai(
        api_key=api_key,
        base_url=base_url,
        data=data,
        filename=filename,
        content_type=payload.get("mime_type") or "audio/ogg",
        model=str((integration.config or {}).get("transcription_model") or "whisper-1"),
    )


def _refine_text(db: Session, integration: TelegramIntegration, text: str, source_type: str) -> str:
    model = resolve_chat_model(db, integration.organization_id, integration.default_chat_model_profile_id)
    if model.provider == "Local":
        return clean_text(text, "standard").cleaned_text
    system = (
        "You refine Telegram content for a RAG knowledge base. Preserve facts, names, dates, "
        "numbers, and intent. Do not invent details. Convert rough speech into clear, structured notes."
    )
    user = f"Source type: {source_type}\n\nRaw text:\n{text}"
    return complete_with_chat_model(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        model,
    )


def _answer_question(
    db: Session,
    integration: TelegramIntegration,
    allowed: TelegramAllowedUser,
    question: str,
) -> str:
    if not question:
        raise ValueError("Use /ask followed by a question.")
    if not allowed.user_id:
        raise ValueError("This Telegram entry must be linked to a RAG account before it can ask questions.")
    membership = db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == integration.organization_id,
            OrganizationMember.user_id == allowed.user_id,
            OrganizationMember.status == "active",
        )
    )
    if not membership:
        raise ValueError("Linked RAG account is not an active member of this organization.")
    kb_ids = [str(integration.default_knowledge_base_id)] if integration.default_knowledge_base_id else []
    filters: dict[str, Any] = {}
    if integration.default_embedding_profile_id:
        filters["embedding_profile_id"] = str(integration.default_embedding_profile_id)
    candidates, _event = retrieve(
        db,
        organization_id=integration.organization_id,
        user_id=allowed.user_id,
        role=membership.role.value,
        query=question,
        knowledge_base_ids=kb_ids,
        filters=filters,
    )
    answer = generate_grounded_answer(
        question,
        candidates,
        resolve_chat_model(db, integration.organization_id, integration.default_chat_model_profile_id),
    )
    citations = "\n".join(f"[{item['id']}] {item['document_name']}" for item in answer.citations[:5])
    return answer.answer if not citations else f"{answer.answer}\n\nSources:\n{citations}"


def _command_body(message: dict[str, Any], command: str) -> str:
    text = str(message.get("text") or message.get("caption") or "").strip()
    match = re.match(rf"^{re.escape(command)}(?:@[A-Za-z0-9_]+)?(?:\s+|$)(.*)$", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def _generated_note_filename(source_type: str, message: dict[str, Any]) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    message_id = message.get("message_id") or "message"
    return f"telegram-{source_type}-{stamp}-{message_id}.md"


def _markdown_note(refined_text: str, raw_text: str, message: dict[str, Any], source_type: str) -> str:
    sender = message.get("from") or {}
    username = sender.get("username") or sender.get("id") or "unknown"
    created_at = datetime.now(UTC).isoformat()
    if refined_text.strip() == raw_text.strip():
        return f"# Telegram {source_type} note\n\nFrom: {username}\nReceived: {created_at}\n\n{refined_text.strip()}\n"
    return (
        f"# Telegram {source_type} note\n\n"
        f"From: {username}\nReceived: {created_at}\n\n"
        f"## Refined note\n\n{refined_text.strip()}\n\n"
        f"## Original transcript\n\n{raw_text.strip()}\n"
    )


def _telegram_metadata(message: dict[str, Any], source_type: str) -> dict[str, Any]:
    sender = message.get("from") or {}
    chat = message.get("chat") or {}
    return {
        "source": "telegram",
        "source_type": source_type,
        "telegram_message_id": message.get("message_id"),
        "telegram_chat_id": chat.get("id"),
        "telegram_user_id": sender.get("id"),
        "telegram_username": _normalize_username(sender.get("username")),
    }


def _normalize_username(username: Any) -> str | None:
    if not username:
        return None
    return str(username).strip().lstrip("@").lower() or None


def _contact_phone(message: dict[str, Any], sender_id: Any) -> str | None:
    contact = message.get("contact") or {}
    if sender_id and contact.get("user_id") and int(contact["user_id"]) != int(sender_id):
        return None
    return _normalize_phone(contact.get("phone_number"))


def _normalize_phone(phone_number: Any) -> str | None:
    if not phone_number:
        return None
    normalized = re.sub(r"[^\d+]", "", str(phone_number).strip())
    if normalized.startswith("00"):
        normalized = "+" + normalized[2:]
    return normalized or None


def _help_text() -> str:
    return (
        "Telegram RAG commands:\n"
        "/add your note - add text to the knowledge base\n"
        "/ask your question - query the knowledge base\n"
        "Send a document to ingest it.\n"
        "Send a voice note to transcribe, refine, and ingest it."
    )
