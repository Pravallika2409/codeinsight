"""
Repository-level analysis (Phase 6).

Runs on a Celery worker (always -- there's no synchronous equivalent, since
fetching a repo and analyzing several files can easily take longer than a
single request should block for). Reuses the exact same
run_analysis()/save_analysis_run() functions the single-file endpoints use
for each file in the repo -- there's still exactly one analysis
implementation, just called once per file here instead of once per request.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.celery_app import celery_app
from app.core.config import get_settings
from app.schemas.analysis import AnalyzeRequest
from app.schemas.github import GitHubAnalysisReport, GitHubAnalyzeRequest, GitHubFileSummary
from app.services.analysis_service import run_analysis
from app.services.github_service import GitHubServiceError, fetch_repo_files
from app.services.history_service import ProjectNotOwnedError, save_analysis_run

logger = logging.getLogger(__name__)


@celery_app.task(name="analyze_github_repo_task", bind=True)
def analyze_github_repo_task(self, request_data: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    """Returns {"success": true, "result": <GitHubAnalysisReport dict>} or
    {"success": false, "error": <message>} -- same shape convention as
    analyze_code_task, never raises.
    """
    from app.database.session import SessionLocal

    try:
        request = GitHubAnalyzeRequest.model_validate(request_data)
    except Exception as exc:
        return {"success": False, "error": f"Invalid request: {exc}"}

    settings = get_settings()

    try:
        fetch_result = fetch_repo_files(request.repo_url, settings)
    except GitHubServiceError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        logger.exception("Unexpected failure fetching GitHub repository")
        return {"success": False, "error": "Failed to fetch the repository unexpectedly."}

    if not fetch_result.files:
        return {
            "success": False,
            "error": f"No supported source files (C++/Python/JavaScript/Java) found in {fetch_result.owner}/{fetch_result.repo}.",
        }

    db = SessionLocal()
    file_summaries = []
    total_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    try:
        for repo_file in fetch_result.files:
            analyze_request = AnalyzeRequest(
                code=repo_file.content,
                language=repo_file.language,
                filename=repo_file.path,
                project_id=request.project_id,
                include_ai_review=request.include_ai_review,
            )
            try:
                response = run_analysis(analyze_request)
            except Exception:
                logger.exception("Analysis failed for %s in %s/%s", repo_file.path, fetch_result.owner, fetch_result.repo)
                continue

            try:
                run = save_analysis_run(
                    db=db,
                    user_id=user_id,
                    project_id=request.project_id,
                    filename=repo_file.path,
                    code=repo_file.content,
                    response=response,
                )
            except ProjectNotOwnedError as exc:
                return {"success": False, "error": str(exc)}

            total_severity["critical"] += response.critical_count
            total_severity["high"] += response.high_count
            total_severity["medium"] += response.medium_count
            total_severity["low"] += response.low_count
            total_severity["info"] += response.info_count

            file_summaries.append(
                GitHubFileSummary(
                    path=repo_file.path,
                    language=repo_file.language,
                    analysis_id=run.id,
                    score_total=response.score.total,
                    critical_count=response.critical_count,
                    high_count=response.high_count,
                )
            )
    finally:
        db.close()

    if not file_summaries:
        return {"success": False, "error": "Every file in the repository failed to analyze."}

    average_score = round(sum(f.score_total for f in file_summaries) / len(file_summaries), 1)

    report = GitHubAnalysisReport(
        repo=f"{fetch_result.owner}/{fetch_result.repo}",
        default_branch=fetch_result.default_branch,
        files_analyzed=len(file_summaries),
        files_skipped=fetch_result.files_skipped,
        truncated=fetch_result.truncated,
        average_score=average_score,
        critical_count=total_severity["critical"],
        high_count=total_severity["high"],
        medium_count=total_severity["medium"],
        low_count=total_severity["low"],
        info_count=total_severity["info"],
        files=file_summaries,
    )
    return {"success": True, "result": report.model_dump(mode="json")}
