from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.enums import Language


class GitHubAnalyzeRequest(BaseModel):
    repo_url: str = Field(min_length=1, description="'owner/repo' or a github.com URL")
    project_id: int
    include_ai_review: bool = False


class GitHubFileSummary(BaseModel):
    path: str
    language: Language
    analysis_id: Optional[int] = None
    score_total: int
    critical_count: int
    high_count: int


class GitHubAnalysisReport(BaseModel):
    repo: str  # "owner/repo"
    default_branch: str
    files_analyzed: int
    files_skipped: int
    truncated: bool
    """True if GitHub's own file listing was truncated (an unusually large
    repository) -- files_analyzed/files_skipped may not reflect the whole
    repo in that case, and this is surfaced rather than silently ignored.
    """
    average_score: float
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    files: List[GitHubFileSummary]


# --- Project analytics (Phase 6) ---

class RuleFrequency(BaseModel):
    rule_id: str
    count: int


class AnalysisRunSummary(BaseModel):
    analysis_id: int
    filename: str
    language: Language
    created_at: dt.datetime
    score_total: int


class ProjectAnalytics(BaseModel):
    project_id: int
    total_runs: int
    average_score: Optional[float] = None
    language_breakdown: Dict[str, int] = Field(default_factory=dict)
    severity_totals: Dict[str, int] = Field(default_factory=dict)
    top_rule_ids: List[RuleFrequency] = Field(default_factory=list)
    score_trend: List[AnalysisRunSummary] = Field(default_factory=list)
    """Chronological (oldest first) -- lets a client plot score over time."""
    worst_files: List[AnalysisRunSummary] = Field(default_factory=list)
    """Up to 5 lowest-scoring runs, worst first."""
