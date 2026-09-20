"""
Analysis orchestration service.

Implements the pipeline from the spec:
    validate -> static analysis -> complexity analysis -> normalize
    -> AI analysis (opt-in, Phase 4) -> merge -> score -> respond

Phase 1 wired up the deterministic side end-to-end for Python and C++.
Phase 2 added JavaScript (ESLint) and Java (javac + javalang). Phase 4
adds an opt-in AI explanation layer (see app/services/ai_service.py) that
never blocks or fails the request -- any AI failure just means
`ai_review` stays None and one INFO finding notes why.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Type

from app.analyzers.base import BaseAnalyzer
from app.analyzers.complexity_analyzer import estimate_complexity
from app.analyzers.cpp_analyzer import CppAnalyzer
from app.analyzers.java_analyzer import JavaAnalyzer
from app.analyzers.javascript_analyzer import JavaScriptAnalyzer
from app.analyzers.python_analyzer import PythonAnalyzer
from app.core.config import get_settings
from app.schemas.ai_review import AIReviewSummary
from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse, Finding, FindingSource, Language, Severity
from app.services.ai_service import AIServiceError, get_ai_provider
from app.services.scoring_service import calculate_score

logger = logging.getLogger(__name__)

_ANALYZER_REGISTRY: Dict[Language, Type[BaseAnalyzer]] = {
    Language.CPP: CppAnalyzer,
    Language.PYTHON: PythonAnalyzer,
    Language.JAVASCRIPT: JavaScriptAnalyzer,
    Language.JAVA: JavaAnalyzer,
}


class UnsupportedLanguageError(Exception):
    pass


def run_analysis(request: AnalyzeRequest) -> AnalyzeResponse:
    analyzer_cls = _ANALYZER_REGISTRY.get(request.language)
    if analyzer_cls is None:
        raise UnsupportedLanguageError(
            f"Language '{request.language.value}' is not yet supported by the analysis engine."
        )

    analyzer = analyzer_cls()
    findings: List[Finding] = analyzer.analyze(request.code, request.filename or "submitted_code")

    complexity = estimate_complexity(request.code, request.language)

    ai_review: AIReviewSummary | None = None
    if request.include_ai_review:
        ai_review, ai_findings = _run_ai_review(request, findings)
        findings = findings + ai_findings

    score = calculate_score(findings, complexity)
    counts = _count_by_severity(findings)

    return AnalyzeResponse(
        language=request.language,
        findings=findings,
        complexity=complexity,
        score=score,
        summary=_build_summary(findings, score.total),
        critical_count=counts[Severity.CRITICAL],
        high_count=counts[Severity.HIGH],
        medium_count=counts[Severity.MEDIUM],
        low_count=counts[Severity.LOW],
        info_count=counts[Severity.INFO],
        ai_review=ai_review,
    )


def _run_ai_review(request: AnalyzeRequest, findings: List[Finding]) -> tuple[AIReviewSummary | None, List[Finding]]:
    """Never raises -- any AI failure degrades to a single INFO finding
    (mirroring how cppcheck/ESLint/javac being unavailable degrades) so
    one flaky/misconfigured AI call can never fail the whole request.
    """
    provider = get_ai_provider(get_settings())
    try:
        result = provider.review(code=request.code, language=request.language.value, findings=findings)
    except AIServiceError as exc:
        logger.info("AI review unavailable: %s", exc)
        return None, [
            Finding(
                rule_id="ai-review-unavailable",
                category="maintainability",
                severity=Severity.INFO,
                message=f"AI review was requested but unavailable: {exc}",
                source=FindingSource.AI,
            )
        ]
    except Exception:
        # Belt-and-suspenders: even an unexpected bug in the AI layer must
        # not take down /api/analyze, which has already computed real
        # deterministic results by this point.
        logger.exception("Unexpected error during AI review")
        return None, [
            Finding(
                rule_id="ai-review-unavailable",
                category="maintainability",
                severity=Severity.INFO,
                message="AI review was requested but failed unexpectedly.",
                source=FindingSource.AI,
            )
        ]

    ai_findings = [
        Finding(
            rule_id="ai-suggested-issue",
            category=issue.category,
            severity=issue.severity,
            message=issue.title,
            file=request.filename or "submitted_code",
            line=issue.line,
            explanation=issue.explanation,
            suggestion=issue.suggestion,
            source=FindingSource.AI,
        )
        for issue in result.additional_issues
    ]
    summary = AIReviewSummary(
        summary=result.summary,
        overall_assessment=result.overall_assessment,
        recommendations=result.recommendations,
        improved_code=result.improved_code,
    )
    return summary, ai_findings


def _count_by_severity(findings: List[Finding]) -> Dict[Severity, int]:
    counts = {s: 0 for s in Severity}
    for f in findings:
        counts[f.severity] += 1
    return counts


def _build_summary(findings: List[Finding], score_total: int) -> str:
    if not findings:
        return f"No issues detected by static analysis. Quality score: {score_total}/100."
    return f"{len(findings)} issue(s) found by static analysis. Quality score: {score_total}/100."
