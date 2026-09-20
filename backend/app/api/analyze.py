"""
Analysis API endpoints.

POST /api/analyze always runs the deterministic pipeline, and additionally
runs an AI review when `include_ai_review=true` is set (Phase 4; degrades
to an INFO finding if no AI provider is configured -- never fails the
request). If the caller is authenticated and supplies `project_id` for a
project they own, the result is also persisted (Phase 3); otherwise it
behaves exactly as in Phase 1/2 -- transient, not saved, no auth required.
Identical requests are served from a Redis cache when available (Phase 5;
a cache miss or Redis outage just means a fresh computation, never a
failure), and the endpoint is rate-limited per IP. GET /api/analysis/{id}
and GET /api/analysis/history read persisted runs and always require auth.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
import redis
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user, get_current_user_optional
from app.core.rate_limit import rate_limit
from app.core.redis_client import get_redis_client
from app.database.session import get_db
from app.models.user import User
from app.schemas.analysis import AnalysisHistoryItem, AnalysisRunDetail, AnalyzeRequest, AnalyzeResponse
from app.services.analysis_service import UnsupportedLanguageError, run_analysis
from app.services.cache_service import build_cache_key, get_cached_response, set_cached_response
from app.services.history_service import ProjectNotOwnedError, get_analysis_run, list_history, save_analysis_run

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analysis"])
settings = get_settings()


@router.post("/analyze", response_model=AnalyzeResponse, dependencies=[Depends(rate_limit("analyze"))])
def analyze_code(
    request: AnalyzeRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis_client),
) -> AnalyzeResponse:
    if len(request.code.encode("utf-8")) > settings.MAX_CODE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Submitted code exceeds the {settings.MAX_CODE_SIZE_BYTES}-byte limit.",
        )

    cache_key = build_cache_key(request)
    response = get_cached_response(redis_client, cache_key)

    if response is None:
        try:
            response = run_analysis(request)
        except UnsupportedLanguageError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception:
            # Never leak internal stack traces to the client (rule #17).
            logger.exception("Unexpected failure while analyzing submitted code")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Analysis failed unexpectedly. Please try again.",
            )
        set_cached_response(redis_client, cache_key, response, settings)

    if request.project_id is not None:
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication is required to save an analysis to a project.",
            )
        try:
            run = save_analysis_run(
                db=db,
                user_id=current_user.id,
                project_id=request.project_id,
                filename=request.filename or "submitted_code",
                code=request.code,
                response=response,
            )
        except ProjectNotOwnedError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        response.analysis_id = run.id

    return response


@router.get("/analysis/history", response_model=List[AnalysisHistoryItem])
def get_history(
    project_id: Optional[int] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[AnalysisHistoryItem]:
    return list_history(user_id=current_user.id, db=db, project_id=project_id)


@router.get("/analysis/{analysis_id}", response_model=AnalysisRunDetail)
def get_analysis(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisRunDetail:
    detail = get_analysis_run(analysis_id, current_user.id, db)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found.")
    return detail
