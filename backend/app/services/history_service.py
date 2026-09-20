"""
Bridges the in-memory analysis pipeline (app/services/analysis_service.py)
to persistent storage. Nothing in app/analyzers/* or analysis_service.py
knows the database exists -- this module is the only place that translates
an AnalyzeResponse into rows and back.
"""
from __future__ import annotations

from collections import Counter
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.analysis_run import AnalysisRun
from app.models.file import ProjectFile
from app.models.finding import FindingRecord
from app.models.project import Project
from app.models.recommendation import Recommendation
from app.schemas.ai_review import AIRecommendation, AIReviewSummary
from app.schemas.analysis import (
    AnalysisHistoryItem,
    AnalysisRunDetail,
    AnalyzeResponse,
    ComplexityEstimate,
    Finding,
    ScoreBreakdown,
)
from app.schemas.github import AnalysisRunSummary, ProjectAnalytics, RuleFrequency


class ProjectNotOwnedError(Exception):
    """Raised when project_id doesn't exist or doesn't belong to the caller."""


def _get_owned_project(project_id: int, user_id: int, db: Session) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.owner_id == user_id)
        .first()
    )
    if project is None:
        raise ProjectNotOwnedError(f"Project {project_id} not found for this user.")
    return project


def save_analysis_run(
    *,
    db: Session,
    user_id: int,
    project_id: int,
    filename: str,
    code: str,
    response: AnalyzeResponse,
) -> AnalysisRun:
    """Persist an AnalyzeResponse under the given (owned) project.

    Raises ProjectNotOwnedError if project_id isn't a project the user owns
    -- callers should translate that into a 404, matching the rest of the
    projects API (never confirm another user's project id exists).
    """
    _get_owned_project(project_id, user_id, db)  # raises if not owned

    project_file = (
        db.query(ProjectFile)
        .filter(ProjectFile.project_id == project_id, ProjectFile.filename == filename)
        .first()
    )
    if project_file is None:
        project_file = ProjectFile(project_id=project_id, filename=filename, language=response.language.value)
        db.add(project_file)
        db.flush()  # assign project_file.id without a full commit yet

    run = AnalysisRun(
        file_id=project_file.id,
        language=response.language.value,
        code=code,
        score_total=response.score.total,
        score_base=response.score.base,
        bug_penalty=response.score.bug_penalty,
        security_penalty=response.score.security_penalty,
        complexity_penalty=response.score.complexity_penalty,
        maintainability_penalty=response.score.maintainability_penalty,
        summary=response.summary,
        time_complexity=response.complexity.time_complexity,
        space_complexity=response.complexity.space_complexity,
        critical_count=response.critical_count,
        high_count=response.high_count,
        medium_count=response.medium_count,
        low_count=response.low_count,
        info_count=response.info_count,
        ai_summary=response.ai_review.summary if response.ai_review else None,
        ai_overall_assessment=response.ai_review.overall_assessment if response.ai_review else None,
        ai_improved_code=response.ai_review.improved_code if response.ai_review else None,
    )
    db.add(run)
    db.flush()

    for finding in response.findings:
        db.add(
            FindingRecord(
                analysis_run_id=run.id,
                rule_id=finding.rule_id,
                category=finding.category.value,
                severity=finding.severity.value,
                message=finding.message,
                file=finding.file,
                line=finding.line,
                column=finding.column,
                explanation=finding.explanation,
                why_it_matters=finding.why_it_matters,
                suggestion=finding.suggestion,
                improved_code=finding.improved_code,
                source=finding.source.value,
            )
        )

    if response.ai_review:
        for rec in response.ai_review.recommendations:
            db.add(Recommendation(analysis_run_id=run.id, title=rec.title, content=rec.description))

    db.commit()
    db.refresh(run)
    return run


def _run_to_detail(run: AnalysisRun) -> AnalysisRunDetail:
    findings = [
        Finding(
            rule_id=f.rule_id,
            category=f.category,
            severity=f.severity,
            message=f.message,
            file=f.file,
            line=f.line,
            column=f.column,
            explanation=f.explanation,
            why_it_matters=f.why_it_matters,
            suggestion=f.suggestion,
            improved_code=f.improved_code,
            source=f.source,
        )
        for f in run.findings
    ]
    ai_review = None
    if run.ai_summary is not None:
        ai_review = AIReviewSummary(
            summary=run.ai_summary,
            overall_assessment=run.ai_overall_assessment or "",
            recommendations=[
                AIRecommendation(title=r.title, description=r.content) for r in run.recommendations
            ],
            improved_code=run.ai_improved_code,
        )
    return AnalysisRunDetail(
        id=run.id,
        filename=run.file.filename,
        project_id=run.file.project_id,
        language=run.language,
        findings=findings,
        complexity=ComplexityEstimate(
            time_complexity=run.time_complexity,
            space_complexity=run.space_complexity,
            is_estimated=True,
        ),
        score=ScoreBreakdown(
            total=run.score_total,
            base=run.score_base,
            bug_penalty=run.bug_penalty,
            security_penalty=run.security_penalty,
            complexity_penalty=run.complexity_penalty,
            maintainability_penalty=run.maintainability_penalty,
        ),
        summary=run.summary,
        critical_count=run.critical_count,
        high_count=run.high_count,
        medium_count=run.medium_count,
        low_count=run.low_count,
        info_count=run.info_count,
        analysis_id=run.id,
        ai_review=ai_review,
        created_at=run.created_at,
    )


def get_analysis_run(run_id: int, user_id: int, db: Session) -> Optional[AnalysisRunDetail]:
    """Returns None if the run doesn't exist or isn't owned by user_id
    (through file -> project -> owner), matching the "404, not 403" policy
    used throughout the projects API.
    """
    run = (
        db.query(AnalysisRun)
        .options(
            joinedload(AnalysisRun.findings),
            joinedload(AnalysisRun.recommendations),
            joinedload(AnalysisRun.file).joinedload(ProjectFile.project),
        )
        .filter(AnalysisRun.id == run_id)
        .first()
    )
    if run is None or run.file.project.owner_id != user_id:
        return None
    return _run_to_detail(run)


def list_history(user_id: int, db: Session, project_id: Optional[int] = None) -> List[AnalysisHistoryItem]:
    query = (
        db.query(AnalysisRun)
        .join(ProjectFile, AnalysisRun.file_id == ProjectFile.id)
        .join(Project, ProjectFile.project_id == Project.id)
        .filter(Project.owner_id == user_id)
    )
    if project_id is not None:
        query = query.filter(Project.id == project_id)

    runs = query.order_by(AnalysisRun.created_at.desc()).all()
    return [
        AnalysisHistoryItem(
            id=run.id,
            filename=run.file.filename,
            language=run.language,
            score_total=run.score_total,
            critical_count=run.critical_count,
            high_count=run.high_count,
            created_at=run.created_at,
        )
        for run in runs
    ]


def get_project_analytics(project_id: int, user_id: int, db: Session) -> Optional[ProjectAnalytics]:
    """Aggregates every persisted AnalysisRun for a project into trend/
    frequency data. Returns None if the project doesn't exist or isn't
    owned by user_id (404, not 403 -- same policy as everywhere else).
    """
    project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user_id).first()
    if project is None:
        return None

    runs = (
        db.query(AnalysisRun)
        .join(ProjectFile, AnalysisRun.file_id == ProjectFile.id)
        .filter(ProjectFile.project_id == project_id)
        .options(joinedload(AnalysisRun.file), joinedload(AnalysisRun.findings))
        .order_by(AnalysisRun.created_at.asc())
        .all()
    )

    if not runs:
        return ProjectAnalytics(project_id=project_id, total_runs=0)

    def _to_summary(run: AnalysisRun) -> AnalysisRunSummary:
        return AnalysisRunSummary(
            analysis_id=run.id,
            filename=run.file.filename,
            language=run.language,
            created_at=run.created_at,
            score_total=run.score_total,
        )

    language_breakdown = Counter(run.language for run in runs)
    severity_totals = Counter(f.severity for run in runs for f in run.findings)
    rule_id_counts = Counter(f.rule_id for run in runs for f in run.findings)

    score_trend = [_to_summary(r) for r in runs]
    worst_files = [_to_summary(r) for r in sorted(runs, key=lambda r: r.score_total)[:5]]

    return ProjectAnalytics(
        project_id=project_id,
        total_runs=len(runs),
        average_score=round(sum(r.score_total for r in runs) / len(runs), 1),
        language_breakdown=dict(language_breakdown),
        severity_totals=dict(severity_totals),
        top_rule_ids=[RuleFrequency(rule_id=rid, count=count) for rid, count in rule_id_counts.most_common(10)],
        score_trend=score_trend,
        worst_files=worst_files,
    )
