"""
AI service abstraction (Phase 4).

The AI is an *explanation/reasoning layer on top of* deterministic static
analysis -- never a replacement for it (see README "Overview"). This
module's only job is: given code + the findings static analysis already
produced, ask the model for (a) a plain-language summary, (b) additional
issues static analysis might have missed, (c) refactoring/best-practice
recommendations, and (d) an improved version of the code -- as *validated*
JSON, never free text trusted as-is.

Provider selection is a small factory (`get_ai_provider`) so swapping
providers later doesn't touch any calling code. If no API key is
configured, or the call/parse/validation fails for any reason, callers get
an `AIServiceError` and are expected to degrade gracefully (see
app/services/analysis_service.py) -- this module never fabricates a
result.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import List

from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.ai_review import AIReviewResult
from app.schemas.analysis import Finding

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a senior software engineer performing a code review.

You are given source code and a list of issues a deterministic static \
analyzer already found. Do not repeat those. Your job is strictly additive:
1. A short, plain-language summary of the code's overall quality.
2. An overall assessment (1-2 sentences).
3. Additional issues the static analyzer likely missed -- logic bugs, \
readability problems, missed edge cases. Only include issues you are \
reasonably confident about; this is a suggestion layer, not a guarantee.
4. Concrete, actionable recommendations (refactoring, best practices).
5. Optionally, an improved version of the code addressing the most \
important issues (omit if the code needs no changes).

Respond with ONLY a single JSON object, no markdown code fences, no text \
before or after it, matching exactly this shape:
{
  "summary": "string",
  "overall_assessment": "string",
  "additional_issues": [
    {"title": "string", "category": "bug|security|performance|code_smell|maintainability|complexity|style", \
"severity": "critical|high|medium|low|info", "line": null_or_int, "explanation": "string", \
"suggestion": "string or null"}
  ],
  "recommendations": [
    {"title": "string", "description": "string"}
  ],
  "improved_code": "string or null"
}
"""


class AIServiceError(Exception):
    """Raised whenever the AI layer can't produce a usable, validated
    result -- no API key configured, a network/API failure, or a response
    that didn't parse/validate. Callers must catch this and degrade
    gracefully; it is never allowed to fail the whole /api/analyze request.
    """


class BaseAIProvider(ABC):
    @abstractmethod
    def review(self, *, code: str, language: str, findings: List[Finding]) -> AIReviewResult:
        raise NotImplementedError


class NullAIProvider(BaseAIProvider):
    """Used when no AI provider is configured. Fails fast with no network
    call, so the analysis pipeline stays fast and fully functional without
    an API key (see README "Installation" -- AI review is optional).
    """

    def review(self, *, code: str, language: str, findings: List[Finding]) -> AIReviewResult:
        raise AIServiceError("No AI provider is configured (set ANTHROPIC_API_KEY to enable AI review).")


class AnthropicAIProvider(BaseAIProvider):
    def __init__(self, api_key: str, model: str, timeout_seconds: int, max_output_tokens: int) -> None:
        import anthropic  # imported lazily so the package is only required when this provider is used

        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_seconds)
        self._model = model
        self._max_output_tokens = max_output_tokens

    def review(self, *, code: str, language: str, findings: List[Finding]) -> AIReviewResult:
        import anthropic

        findings_summary = self._summarize_findings(findings)
        user_prompt = (
            f"Language: {language}\n\n"
            f"Static analysis already found:\n{findings_summary or '(no issues found)'}\n\n"
            f"Code:\n```{language}\n{code}\n```"
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_output_tokens,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.APIStatusError as exc:
            logger.warning("Anthropic API returned an error status: %s", exc.status_code)
            raise AIServiceError(f"AI provider returned an error (status {exc.status_code}).") from exc
        except anthropic.APITimeoutError as exc:
            logger.warning("Anthropic API call timed out")
            raise AIServiceError("AI provider timed out.") from exc
        except anthropic.APIConnectionError as exc:
            logger.warning("Could not reach the Anthropic API: %s", exc)
            raise AIServiceError("Could not reach the AI provider.") from exc

        return self._parse_response(response)

    @staticmethod
    def _summarize_findings(findings: List[Finding]) -> str:
        # Keep the prompt small: rule id + one-line message is enough context
        # for the model to avoid repeating what's already been found.
        return "\n".join(f"- [{f.severity.value}] {f.rule_id}: {f.message}" for f in findings[:30])

    @staticmethod
    def _parse_response(response) -> AIReviewResult:
        text_blocks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        raw_text = "".join(text_blocks).strip()

        # The model is instructed not to wrap the JSON in code fences, but
        # strip them defensively rather than fail a response that's
        # otherwise perfectly usable.
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.lower().startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            logger.warning("AI response was not valid JSON: %s", raw_text[:500])
            raise AIServiceError("AI provider returned a response that wasn't valid JSON.") from exc

        try:
            return AIReviewResult.model_validate(payload)
        except ValidationError as exc:
            logger.warning("AI response JSON didn't match the expected schema: %s", exc)
            raise AIServiceError("AI provider returned JSON that didn't match the expected shape.") from exc


def get_ai_provider(settings: Settings) -> BaseAIProvider:
    """Factory: returns the configured provider, or NullAIProvider if none
    is usable. Keeps provider selection out of calling code entirely.
    """
    if settings.AI_PROVIDER == "anthropic" and settings.ANTHROPIC_API_KEY:
        return AnthropicAIProvider(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.AI_MODEL,
            timeout_seconds=settings.AI_TIMEOUT_SECONDS,
            max_output_tokens=settings.AI_MAX_OUTPUT_TOKENS,
        )
    return NullAIProvider()
