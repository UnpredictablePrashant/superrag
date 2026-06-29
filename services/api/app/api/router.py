from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    audit_logs,
    auth,
    chat,
    documents,
    knowledge_bases,
    notifications,
    organizations,
    pipeline_runs,
    profiles,
    providers,
    retrieval,
    uploads,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(knowledge_bases.router)
api_router.include_router(uploads.router)
api_router.include_router(documents.router)
api_router.include_router(pipeline_runs.router)
api_router.include_router(providers.router)
api_router.include_router(profiles.router)
api_router.include_router(chat.router)
api_router.include_router(retrieval.router)
api_router.include_router(notifications.router)
api_router.include_router(audit_logs.router)
