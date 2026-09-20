"""
GitHub repository analysis endpoints (Phase 6).

Always asynchronous (runs on a Celery worker) and always requires auth +
an owned project_id -- fetching and analyzing several files from a real
repository can take a while, and every resulting file analysis is
persisted, which needs an owner.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.celery_app import celery_app
from app.core.deps import get_current_user
from app.core.rate_limit import rate_limit
from app.models.user import User
from app.schemas.github import GitHubAnalysisReport, GitHubAnalyzeRequest
from app.tasks.github_tasks import analyze_github_repo_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/github", tags=["github"])


class GitHubTaskEnqueuedResponse(BaseModel):
    task_id: str
    status: str = "pending"


class GitHubTaskStatusResponse(BaseModel):
    task_id: str
    status: str  # pending | started | success | failure
    result: Optional[GitHubAnalysisReport] = None
    error: Optional[str] = None


@router.post("/analyze", response_model=GitHubTaskEnqueuedResponse, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(rate_limit("analyze"))])
def analyze_github_repo(
    request: GitHubAnalyzeRequest,
    current_user: User = Depends(get_current_user),
) -> GitHubTaskEnqueuedResponse:
    async_result = analyze_github_repo_task.delay(request.model_dump(mode="json"), current_user.id)
    return GitHubTaskEnqueuedResponse(task_id=async_result.id)


@router.get("/analyze/{task_id}", response_model=GitHubTaskStatusResponse)
def get_github_analysis_status(task_id: str) -> GitHubTaskStatusResponse:
    async_result = celery_app.AsyncResult(task_id)

    if async_result.state == "PENDING":
        return GitHubTaskStatusResponse(task_id=task_id, status="pending")
    if async_result.state == "STARTED":
        return GitHubTaskStatusResponse(task_id=task_id, status="started")
    if async_result.state == "FAILURE":
        logger.error("GitHub analysis task %s failed: %s", task_id, async_result.result)
        return GitHubTaskStatusResponse(task_id=task_id, status="failure", error="Task failed unexpectedly.")

    payload = async_result.result or {}
    if payload.get("success"):
        return GitHubTaskStatusResponse(task_id=task_id, status="success", result=payload["result"])
    return GitHubTaskStatusResponse(task_id=task_id, status="failure", error=payload.get("error", "Task failed."))
