"""
Pydantic schemas for the code-analysis domain.

These models define the normalized "finding" format that every analyzer
(static analysis, compiler, complexity, AI) must produce, plus the request
and response contracts for POST /api/analyze.
"""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.ai_review import AIReviewSummary
from app.schemas.enums import Category, FindingSource, Language, Severity

__all__ = [
    "Language", "Severity", "Category", "FindingSource",  # re-exported from enums.py
    "Finding", "ComplexityEstimate", "ScoreBreakdown",
    "AnalyzeRequest", "AnalyzeResponse", "AnalysisHistoryItem", "AnalysisRunDetail",
]


class Finding(BaseModel):
    """A single normalized issue found in submitted code."""

    rule_id: str
    category: Category
    severity: Severity
    message: str
    file: str = "submitted_code"
    line: Optional[int] = None
    column: Optional[int] = None
    explanation: Optional[str] = None
    why_it_matters: Optional[str] = None
    suggestion: Optional[str] = None
    improved_code: Optional[str] = None
    source: FindingSource


class ComplexityEstimate(BaseModel):
    time_complexity: Optional[str] = None
    space_complexity: Optional[str] = None
    is_estimated: bool = True
    notes: Optional[str] = None


class ScoreBreakdown(BaseModel):
    total: int = Field(ge=0, le=100)
    base: int = 100
    bug_penalty: int = 0
    security_penalty: int = 0
    complexity_penalty: int = 0
    maintainability_penalty: int = 0


class AnalyzeRequest(BaseModel):
    code: str = Field(min_length=1)
    language: Language
    filename: Optional[str] = "submitted_code"
    project_id: Optional[int] = None
    """If set (and the caller is authenticated as the project's owner), the
    result is persisted as an AnalysisRun and can be retrieved later via
    GET /api/analysis/{id} or GET /api/analysis/history. If omitted, the
    request behaves exactly as in Phase 1/2: transient, not saved.
    """
    include_ai_review: bool = False
    """Opt-in: also ask the configured AI provider (Phase 4) to explain
    findings, suggest additional issues, and propose refactors. Off by
    default -- an AI call costs money and latency, and requires
    ANTHROPIC_API_KEY to be configured; deterministic static analysis
    always runs regardless of this flag.
    """

    @field_validator("code")
    @classmethod
    def not_just_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("code must not be empty or whitespace-only")
        return v


class AnalyzeResponse(BaseModel):
    language: Language
    findings: List[Finding]
    complexity: ComplexityEstimate
    score: ScoreBreakdown
    summary: str
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    analysis_id: Optional[int] = None
    """Set only when `project_id` was provided on the request and the
    result was persisted (Phase 3+); None for anonymous/unsaved runs.
    """
    ai_review: Optional[AIReviewSummary] = None
    """Set only when `include_ai_review=True` was requested AND the AI
    call succeeded and validated (Phase 4+); None otherwise -- including
    on any AI failure, which never fails the overall request (see
    analysis_service.py). additional_issues from a successful AI review
    are merged into `findings` above (source="ai"), not duplicated here.
    """


class AnalysisHistoryItem(BaseModel):
    id: int
    filename: str
    language: Language
    score_total: int
    critical_count: int
    high_count: int
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class AnalysisRunDetail(AnalyzeResponse):
    id: int
    filename: str
    project_id: int
    created_at: dt.datetime
