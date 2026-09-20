"""
Project endpoints. Every route requires authentication and every query is
scoped to `current_user.id` -- a project id belonging to someone else
returns 404, never 403, so as not to confirm to a caller that an id exists.
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database.session import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.github import ProjectAnalytics
from app.schemas.project import ProjectCreate, ProjectOut
from app.services.history_service import get_project_analytics

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])


def _to_out(project: Project) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        file_count=len(project.files),
    )


def _get_owned_project_or_404(project_id: int, current_user: User, db: Session) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.owner_id == current_user.id)
        .first()
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    project = Project(owner_id=current_user.id, name=payload.name, description=payload.description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return _to_out(project)


@router.get("", response_model=List[ProjectOut])
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ProjectOut]:
    projects = (
        db.query(Project)
        .filter(Project.owner_id == current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    return [_to_out(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    return _to_out(_get_owned_project_or_404(project_id, current_user, db))


@router.get("/{project_id}/analytics", response_model=ProjectAnalytics)
def get_analytics(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectAnalytics:
    """Aggregates every persisted analysis run for this project: score
    trend over time, severity totals, most frequent rule ids, language
    breakdown, and the lowest-scoring files (Phase 6).
    """
    analytics = get_project_analytics(project_id, current_user.id, db)
    if analytics is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return analytics


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    project = _get_owned_project_or_404(project_id, current_user, db)
    db.delete(project)
    db.commit()
