"""
Explainable 0-100 code quality score.

The score always starts at 100 and is reduced by named, visible penalties
so the frontend can show the user exactly why they received the score
they did (see project rule: "do not make the score arbitrary").
"""
from __future__ import annotations

from typing import List

from app.schemas.analysis import ComplexityEstimate, Finding, FindingSource, ScoreBreakdown, Severity

_SEVERITY_WEIGHT = {
    Severity.CRITICAL: 12,
    Severity.HIGH: 7,
    Severity.MEDIUM: 3,
    Severity.LOW: 1,
    Severity.INFO: 0,
}


def calculate_score(findings: List[Finding], complexity: ComplexityEstimate) -> ScoreBreakdown:
    bug_penalty = 0
    security_penalty = 0
    maintainability_penalty = 0

    for f in findings:
        weight = _SEVERITY_WEIGHT.get(f.severity, 0)
        if f.source == FindingSource.AI:
            # An AI-suggested issue is never a guaranteed bug (see
            # app/services/ai_service.py); it shouldn't move the score as
            # much as a deterministic tool's confirmed finding of the same
            # severity.
            weight = weight // 2
        if f.category.value == "security":
            security_penalty += weight
        elif f.category.value in ("bug",):
            bug_penalty += weight
        else:
            maintainability_penalty += weight

    complexity_penalty = 0
    if complexity.time_complexity in ("O(n\u00b2)", "O(n\u00b3)"):
        complexity_penalty = 5 if complexity.time_complexity == "O(n\u00b2)" else 10

    bug_penalty = min(bug_penalty, 40)
    security_penalty = min(security_penalty, 40)
    maintainability_penalty = min(maintainability_penalty, 25)

    total = 100 - bug_penalty - security_penalty - complexity_penalty - maintainability_penalty
    total = max(0, min(100, total))

    return ScoreBreakdown(
        total=total,
        base=100,
        bug_penalty=bug_penalty,
        security_penalty=security_penalty,
        complexity_penalty=complexity_penalty,
        maintainability_penalty=maintainability_penalty,
    )
