from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_organization
from app.db.session import get_db
from app.models.entities import CompanyEvidence, CompanyProfile
from app.schemas.api import CompanyEvidenceOut, CompanyProfileDetailOut, CompanyProfileOut

router = APIRouter(prefix="/company-profiles", tags=["company-profiles"])


@router.get("", response_model=list[CompanyProfileOut])
def list_company_profiles(
    search: str | None = Query(default=None),
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> list[CompanyProfile]:
    query = select(CompanyProfile).where(
        CompanyProfile.organization_id == ctx.organization_id,
        CompanyProfile.deleted_at.is_(None),
    )
    if search:
        query = query.where(CompanyProfile.name.ilike(f"%{search}%"))
    return list(db.scalars(query.order_by(CompanyProfile.updated_at.desc()).limit(100)))


@router.get("/{company_profile_id}", response_model=CompanyProfileDetailOut)
def get_company_profile(
    company_profile_id: UUID,
    ctx: AuthContext = Depends(require_organization),
    db: Session = Depends(get_db),
) -> CompanyProfileDetailOut:
    profile = db.get(CompanyProfile, company_profile_id)
    if not profile or profile.organization_id != ctx.organization_id or profile.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Company profile not found.")
    evidence = list(
        db.scalars(
            select(CompanyEvidence)
            .where(CompanyEvidence.company_profile_id == profile.id)
            .order_by(CompanyEvidence.created_at.desc())
        )
    )
    return CompanyProfileDetailOut(
        **CompanyProfileOut.model_validate(profile).model_dump(),
        evidence=[CompanyEvidenceOut.model_validate(row) for row in evidence],
    )
