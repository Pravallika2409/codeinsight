"""
Background version of the analysis pipeline (Phase 5).

Runs the exact same app/services/analysis_service.run_analysis() used by
the synchronous POST /api/analyze -- this task adds no new analysis logic,
only a way to run it off the request thread. Persistence (when project_id
is supplied) reuses app/services/history_service.py the same way the
synchronous endpoint does.

SessionLocal is imported inside the function body (not at module level) so
tests can monkeypatch app.database.session.SessionLocal to point at the
isolated test database -- see backend/tests/conftest.py.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.celery_app import celery_app
from app.schemas.analysis import AnalyzeRequest
from app.services.analysis_service import UnsupportedLanguageError, run_analysis
from app.services.history_service import ProjectNotOwnedError, save_analysis_run

logger = logging.getLogger(__name__)


@celery_app.task(name="analyze_code_task", bind=True)
def analyze_code_task(self, request_data: Dict[str, Any], user_id: Optional[int]) -> Dict[str, Any]:
    """Returns a JSON-serializable dict, always shaped as either
    {"success": true, "result": <AnalyzeResponse dict>} or
    {"success": false, "error": <message>} -- never raises, so
    GET /api/tasks/{id} can present a clean result either way instead of
    Celery's own traceback-shaped failure payload.
    """
    from app.database.session import SessionLocal

    try:
        request = AnalyzeRequest.model_validate(request_data)
    except Exception as exc:
        return {"success": False, "error": f"Invalid request: {exc}"}

    try:
        response = run_analysis(request)
    except UnsupportedLanguageError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        logger.exception("Unexpected failure during background analysis")
        return {"success": False, "error": "Analysis failed unexpectedly."}

    if request.project_id is not None:
        if user_id is None:
            return {"success": False, "error": "Authentication is required to save an analysis to a project."}
        db = SessionLocal()
        try:
            run = save_analysis_run(
                db=db,
                user_id=user_id,
                project_id=request.project_id,
                filename=request.filename or "submitted_code",
                code=request.code,
                response=response,
            )
            response.analysis_id = run.id
        except ProjectNotOwnedError as exc:
            return {"success": False, "error": str(exc)}
        finally:
            db.close()

    return {"success": True, "result": response.model_dump(mode="json")}
