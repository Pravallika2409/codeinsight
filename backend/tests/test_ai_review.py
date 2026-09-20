import pytest

from app.schemas.ai_review import AIReviewResult
from app.services.ai_service import AIServiceError, AnthropicAIProvider, NullAIProvider, get_ai_provider
from tests import sample_code


# --- Provider selection ---

def test_get_ai_provider_returns_null_provider_with_no_api_key():
    from app.core.config import Settings

    settings = Settings(ANTHROPIC_API_KEY="", _env_file=None)
    assert isinstance(get_ai_provider(settings), NullAIProvider)


def test_get_ai_provider_returns_anthropic_provider_with_api_key():
    from app.core.config import Settings

    settings = Settings(ANTHROPIC_API_KEY="sk-fake-key-for-testing", _env_file=None)
    assert isinstance(get_ai_provider(settings), AnthropicAIProvider)


def test_null_provider_fails_fast_with_no_network_call():
    provider = NullAIProvider()
    with pytest.raises(AIServiceError):
        provider.review(code="print(1)", language="python", findings=[])


# --- Response parsing (the part we can test deterministically without a real API key) ---

class _FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


def test_parse_response_accepts_valid_json():
    payload = {
        "summary": "Looks reasonable overall.",
        "overall_assessment": "Minor readability concerns.",
        "additional_issues": [
            {
                "title": "Off-by-one risk in loop bound",
                "category": "bug",
                "severity": "medium",
                "line": 3,
                "explanation": "The loop may run one iteration too many.",
                "suggestion": "Use < instead of <=.",
            }
        ],
        "recommendations": [{"title": "Extract helper", "description": "Pull the inner block into its own function."}],
        "improved_code": "def f(): pass",
    }
    import json

    fake_response = type("R", (), {"content": [_FakeTextBlock(json.dumps(payload))]})()
    result = AnthropicAIProvider._parse_response(fake_response)
    assert isinstance(result, AIReviewResult)
    assert result.additional_issues[0].title == "Off-by-one risk in loop bound"
    assert result.recommendations[0].title == "Extract helper"


def test_parse_response_strips_markdown_fences():
    import json

    payload = {"summary": "ok", "overall_assessment": "ok", "additional_issues": [], "recommendations": []}
    fenced = "```json\n" + json.dumps(payload) + "\n```"
    fake_response = type("R", (), {"content": [_FakeTextBlock(fenced)]})()
    result = AnthropicAIProvider._parse_response(fake_response)
    assert result.summary == "ok"


def test_parse_response_rejects_invalid_json():
    fake_response = type("R", (), {"content": [_FakeTextBlock("not json at all")]})()
    with pytest.raises(AIServiceError):
        AnthropicAIProvider._parse_response(fake_response)


def test_parse_response_rejects_json_missing_required_fields():
    import json

    fake_response = type("R", (), {"content": [_FakeTextBlock(json.dumps({"summary": "ok"}))]})()
    with pytest.raises(AIServiceError):
        AnthropicAIProvider._parse_response(fake_response)


# --- End-to-end through /api/analyze ---

def test_analyze_without_include_ai_review_never_attempts_ai(client):
    resp = client.post("/api/analyze", json={"code": sample_code.PYTHON_CLEAN, "language": "python"})
    body = resp.json()
    assert body["ai_review"] is None
    assert not any(f["rule_id"] == "ai-review-unavailable" for f in body["findings"])


def test_analyze_with_include_ai_review_degrades_gracefully_with_no_api_key(client):
    # Test environment has no ANTHROPIC_API_KEY set -> NullAIProvider -> graceful degradation.
    resp = client.post(
        "/api/analyze",
        json={"code": sample_code.PYTHON_CLEAN, "language": "python", "include_ai_review": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ai_review"] is None
    ai_findings = [f for f in body["findings"] if f["rule_id"] == "ai-review-unavailable"]
    assert len(ai_findings) == 1
    assert ai_findings[0]["source"] == "ai"
    assert ai_findings[0]["severity"] == "info"


def test_analyze_with_mocked_successful_ai_review_merges_findings_and_summary(client, monkeypatch):
    from app.schemas.ai_review import AIAdditionalIssue, AIRecommendation
    from app.services import analysis_service

    fake_result = AIReviewResult(
        summary="The function is small and mostly fine.",
        overall_assessment="Low risk, one logic concern worth a look.",
        additional_issues=[
            AIAdditionalIssue(
                title="Possible off-by-one",
                category="bug",
                severity="high",
                line=2,
                explanation="Loop bound may be exclusive when it should be inclusive.",
                suggestion="Double check the intended range.",
            )
        ],
        recommendations=[AIRecommendation(title="Add a docstring", description="Explain what the function returns.")],
        improved_code="def process(items):\n    return items\n",
    )

    class _FakeProvider:
        def review(self, *, code, language, findings):
            return fake_result

    monkeypatch.setattr(analysis_service, "get_ai_provider", lambda settings: _FakeProvider())

    resp = client.post(
        "/api/analyze",
        json={"code": sample_code.PYTHON_CLEAN, "language": "python", "include_ai_review": True},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["ai_review"]["summary"] == "The function is small and mostly fine."
    assert body["ai_review"]["recommendations"][0]["title"] == "Add a docstring"
    assert body["ai_review"]["improved_code"].startswith("def process")

    ai_findings = [f for f in body["findings"] if f["source"] == "ai"]
    assert len(ai_findings) == 1
    assert ai_findings[0]["message"] == "Possible off-by-one"
    assert ai_findings[0]["severity"] == "high"
    assert body["high_count"] == 1


def test_ai_findings_are_weighted_half_in_scoring(monkeypatch):
    from app.schemas.analysis import ComplexityEstimate, Finding
    from app.services.scoring_service import calculate_score

    complexity = ComplexityEstimate(time_complexity="O(1)", space_complexity="O(1)", is_estimated=True)

    static_critical = Finding(
        rule_id="x", category="bug", severity="critical", message="m", source="static-analysis"
    )
    ai_critical = Finding(rule_id="y", category="bug", severity="critical", message="m", source="ai")

    static_score = calculate_score([static_critical], complexity)
    ai_score = calculate_score([ai_critical], complexity)

    assert ai_score.bug_penalty == static_score.bug_penalty // 2
    assert ai_score.total > static_score.total


def test_analyze_with_ai_review_persists_recommendations(client, auth_headers, monkeypatch):
    from app.schemas.ai_review import AIRecommendation
    from app.services import analysis_service

    fake_result = AIReviewResult(
        summary="Fine.",
        overall_assessment="Fine.",
        additional_issues=[],
        recommendations=[AIRecommendation(title="Rec A", description="Do the thing.")],
        improved_code=None,
    )

    class _FakeProvider:
        def review(self, *, code, language, findings):
            return fake_result

    monkeypatch.setattr(analysis_service, "get_ai_provider", lambda settings: _FakeProvider())

    headers = auth_headers()
    project = client.post("/api/projects", json={"name": "AI project"}, headers=headers).json()

    resp = client.post(
        "/api/analyze",
        json={
            "code": sample_code.PYTHON_CLEAN,
            "language": "python",
            "project_id": project["id"],
            "include_ai_review": True,
        },
        headers=headers,
    )
    analysis_id = resp.json()["analysis_id"]

    detail = client.get(f"/api/analysis/{analysis_id}", headers=headers).json()
    assert detail["ai_review"]["recommendations"] == [{"title": "Rec A", "description": "Do the thing."}]
