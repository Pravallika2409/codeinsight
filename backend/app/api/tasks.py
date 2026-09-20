"""
Background/async analysis endpoints (Phase 5).

POST /api/analyze/async enqueues the same analysis pipeline used by the
synchronous POST /api/analyze (see app/tasks/analysis_tasks.py) and
returns immediately with a task id; GET /api/tasks/{id} polls its status.
This is an addition, not a replacement -- POST /api/analyze remains the
simple, synchronous default.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.celery_app import celery_app
from app.core.config import get_settings
from app.core.deps import get_current_user_optional
from app.core.rate_limit import rate_limit
from app.models.user import User
from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse
from app.tasks.analysis_tasks import analyze_code_task

logger = logging.getLogger(__name__)
router = APIRouter(tags=["tasks"])
settings = get_settings()


class TaskEnqueuedResponse(BaseModel):
    task_id: str
    status: str = "pending"


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # pending | started | success | failure
    result: Optional[AnalyzeResponse] = None
    error: Optional[str] = None


@router.post("/analyze/async", response_model=TaskEnqueuedResponse, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(rate_limit("analyze"))])
def analyze_code_async(
    request: AnalyzeRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> TaskEnqueuedResponse:
    if len(request.code.encode("utf-8")) > settings.MAX_CODE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Submitted code exceeds the {settings.MAX_CODE_SIZE_BYTES}-byte limit.",
        )
    if request.project_id is not None and current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required to save an analysis to a project.",
        )

    async_result = analyze_code_task.delay(
        request.model_dump(mode="json"),
        current_user.id if current_user else None,
    )
    return TaskEnqueuedResponse(task_id=async_result.id)


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str) -> TaskStatusResponse:
    async_result = celery_app.AsyncResult(task_id)

    if async_result.state == "PENDING":
        return TaskStatusResponse(task_id=task_id, status="pending")
    if async_result.state == "STARTED":
        return TaskStatusResponse(task_id=task_id, status="started")
    if async_result.state == "FAILURE":
        # An unexpected exception escaped the task itself (rather than the
        # task's own {"success": False, ...} path) -- still never leak the
        # raw traceback to the client.
        logger.error("Celery task %s failed: %s", task_id, async_result.result)
        return TaskStatusResponse(task_id=task_id, status="failure", error="Task failed unexpectedly.")

    # SUCCESS -- but the task itself may have recorded a handled failure.
    payload = async_result.result or {}
    if payload.get("success"):
        return TaskStatusResponse(task_id=task_id, status="success", result=payload["result"])
    return TaskStatusResponse(task_id=task_id, status="failure", error=payload.get("error", "Task failed."))
