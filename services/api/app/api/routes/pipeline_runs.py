from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, capability, require_organization
from app.db.session import SessionLocal, get_db
from app.models.entities import (
    Document,
    DocumentStatus,
    PipelineRun,
    PipelineRunDocument,
    PipelineStage,
)
from app.schemas.api import PipelineRunCreateIn, PipelineRunOut
from app.workers.tasks import process_pipeline_run_task

router = APIRouter(prefix="/pipeline-runs", tags=["pipeline-runs"])


@router.post("", response_model=PipelineRunOut)
def create_pipeline_run(
    payload: PipelineRunCreateIn,
    ctx: AuthContext = Depends(capability("run_ingestion")),
    db: Session = Depends(get_db),
) -> PipelineRunOut:
    if not payload.document_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Select at least one document.")
    documents = list(
        db.scalars(
            select(Document).where(
                Document.organization_id == ctx.organization_id,
                Document.id.in_(payload.document_ids),
                Document.deleted_at.is_(None),
            )
        )
    )
    if len(documents) != len(payload.document_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="One or more documents were not found.")
    run = PipelineRun(
        organization_id=ctx.organization_id,
        knowledge_base_id=payload.knowledge_base_id,
        cleanup_profile_id=payload.cleanup_profile_id,
        chunking_profile_id=payload.chunking_profile_id,
        embedding_profile_id=payload.embedding_profile_id,
        retrieval_index_config=payload.retrieval_index_config,
        current_stage=PipelineStage.QUEUED,
        total_count=len(documents),
        estimated_completion_seconds=max(30, len(documents) * 15),
        estimated_completion_confidence="Low",
    )
    db.add(run)
    db.flush()
    for document in documents:
        document.processing_status = DocumentStatus.QUEUED
        db.add(
            PipelineRunDocument(
                organization_id=ctx.organization_id,
                pipeline_run_id=run.id,
                document_id=document.id,
                status=PipelineStage.QUEUED,
            )
        )
    db.commit()
    process_pipeline_run_task.delay(str(run.id))
    db.refresh(run)
    return _run_out(db, run)


@router.get("", response_model=list[PipelineRunOut])
def list_pipeline_runs(
    ctx: AuthContext = Depends(require_organization), db: Session = Depends(get_db)
) -> list[PipelineRunOut]:
    runs = list(
        db.scalars(
            select(PipelineRun)
            .where(PipelineRun.organization_id == ctx.organization_id)
            .order_by(PipelineRun.created_at.desc())
            .limit(50)
        )
    )
    return [_run_out(db, run) for run in runs]


@router.get("/{pipeline_run_id}", response_model=PipelineRunOut)
def get_pipeline_run(
    pipeline_run_id: UUID,
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> PipelineRunOut:
    run = _get_run(db, ctx.organization_id, pipeline_run_id)
    return _run_out(db, run)


@router.post("/{pipeline_run_id}/cancel")
def cancel_pipeline_run(
    pipeline_run_id: UUID,
    ctx: AuthContext = Depends(capability("run_ingestion")),
    db: Session = Depends(get_db),
) -> dict:
    run = _get_run(db, ctx.organization_id, pipeline_run_id)
    run.cancelled_at = datetime.now(UTC)
    run.current_stage = PipelineStage.CANCELLED
    db.commit()
    return {"message": "Pipeline cancellation requested."}


@router.post("/{pipeline_run_id}/retry", response_model=PipelineRunOut)
def retry_pipeline_run(
    pipeline_run_id: UUID,
    ctx: AuthContext = Depends(capability("run_ingestion")),
    db: Session = Depends(get_db),
) -> PipelineRunOut:
    run = _get_run(db, ctx.organization_id, pipeline_run_id)
    run.retry_count += 1
    run.current_stage = PipelineStage.QUEUED
    run.progress_percentage = 0
    run.errors = []
    run.cancelled_at = None
    db.commit()
    process_pipeline_run_task.delay(str(run.id))
    return _run_out(db, run)


@router.get("/{pipeline_run_id}/events")
def pipeline_events(
    pipeline_run_id: UUID,
    ctx: AuthContext = Depends(require_organization),
) -> StreamingResponse:
    def event_stream():
        terminal = {
            PipelineStage.COMPLETED,
            PipelineStage.COMPLETED_WITH_WARNINGS,
            PipelineStage.FAILED,
            PipelineStage.CANCELLED,
            PipelineStage.AWAITING_REVIEW,
        }
        while True:
            db = SessionLocal()
            try:
                run = _get_run(db, ctx.organization_id, pipeline_run_id)
                payload = PipelineRunOut.model_validate(_run_out(db, run)).model_dump(mode="json")
                yield f"event: pipeline\ndata: {json.dumps(payload)}\n\n"
                if run.current_stage in terminal:
                    break
            finally:
                db.close()
            time.sleep(1.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _get_run(db: Session, organization_id: UUID, run_id: UUID) -> PipelineRun:
    run = db.get(PipelineRun, run_id)
    if not run or run.organization_id != organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Pipeline run not found.")
    return run


def _run_out(db: Session, run: PipelineRun) -> PipelineRunOut:
    docs = db.execute(
        select(PipelineRunDocument, Document.name)
        .join(Document, Document.id == PipelineRunDocument.document_id)
        .where(PipelineRunDocument.pipeline_run_id == run.id)
        .order_by(PipelineRunDocument.created_at)
    ).all()
    return PipelineRunOut(
        id=run.id,
        knowledge_base_id=run.knowledge_base_id,
        current_stage=run.current_stage,
        progress_percentage=run.progress_percentage,
        current_item=run.current_item,
        processed_count=run.processed_count,
        total_count=run.total_count,
        estimated_completion_seconds=run.estimated_completion_seconds,
        estimated_completion_confidence=run.estimated_completion_confidence,
        actual_completion_seconds=run.actual_completion_seconds,
        warnings=run.warnings,
        errors=run.errors,
        retry_count=run.retry_count,
        worker_logs=run.worker_logs,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        documents=[
            {
                "document_id": str(doc.document_id),
                "name": name,
                "status": doc.status.value,
                "progress_percentage": doc.progress_percentage,
                "error": doc.error,
                "warnings": doc.warnings,
            }
            for doc, name in docs
        ],
    )
