"""
Schemas for the AI explanation/reasoning layer (Phase 4).

The AI is prompted to respond with JSON matching AIReviewResult exactly
(see app/services/ai_service.py). Anything that doesn't validate against
this schema is treated as a failed AI call, not partially trusted --
see AIServiceError in ai_service.py.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.enums import Category, Severity


class AIAdditionalIssue(BaseModel):
    """A possible issue the AI noticed that deterministic analysis did not.

    Always surfaced to the user with source="ai" and never described as a
    guaranteed bug (see Finding.source docs and the project's own rule:
    "Do not claim an AI prediction is a guaranteed bug").
    """

    title: str = Field(min_length=1, max_length=200)
    category: Category = Category.MAINTAINABILITY
    severity: Severity = Severity.INFO
    line: Optional[int] = None
    explanation: str = Field(min_length=1)
    suggestion: Optional[str] = None


class AIRecommendation(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)


class AIReviewResult(BaseModel):
    summary: str = Field(min_length=1)
    overall_assessment: str = Field(min_length=1)
    additional_issues: List[AIAdditionalIssue] = Field(default_factory=list)
    recommendations: List[AIRecommendation] = Field(default_factory=list)
    improved_code: Optional[str] = None


class AIReviewSummary(BaseModel):
    """The subset of AIReviewResult surfaced directly on AnalyzeResponse.

    `additional_issues` is intentionally excluded here -- those are
    converted into normal `Finding` objects (source="ai") and merged into
    the response's main `findings` list instead of living in a separate
    place the UI would have to know about specially.
    """

    summary: str
    overall_assessment: str
    recommendations: List[AIRecommendation] = Field(default_factory=list)
    improved_code: Optional[str] = None
