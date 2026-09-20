"""
JavaScript static analyzer.

Wraps a real, standalone ESLint installation (see
`backend/tools/js-lint/`) rather than hand-rolling a JS parser -- per
project rule: "prefer using an existing linter/compiler where one already
exists". The fixed ruleset lives in `tools/js-lint/eslint.config.mjs` and
covers unused variables, `==` vs `===`, dangerous `eval`, promise-executor
misuse, and a few other categories called out in the spec.

Security note: submitted code is piped to ESLint over stdin (never written
to a path ESLint could treat as part of a real project, and never executed
-- ESLint only parses/lints, it does not run the code).
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import List

from app.analyzers.base import BaseAnalyzer
from app.schemas.analysis import Category, Finding, FindingSource, Severity

logger = logging.getLogger(__name__)

_TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools" / "js-lint"
_CONFIG_PATH = _TOOLS_DIR / "eslint.config.mjs"
_ESLINT_BIN = _TOOLS_DIR / "node_modules" / ".bin" / "eslint"

# ESLint reports 1 = warning, 2 = error.
_ESLINT_SEVERITY = {1: Severity.LOW, 2: Severity.MEDIUM}

# A handful of rules that indicate something more serious than their
# default ESLint severity suggests, given this project's own severity
# vocabulary (CRITICAL/HIGH/MEDIUM/LOW/INFO).
_RULE_SEVERITY_OVERRIDE = {
    "no-eval": Severity.HIGH,
    "no-implied-eval": Severity.HIGH,
    "no-new-func": Severity.HIGH,
    "no-script-url": Severity.HIGH,
    "eqeqeq": Severity.MEDIUM,
    "no-async-promise-executor": Severity.MEDIUM,
    "no-unreachable": Severity.MEDIUM,
}

_RULE_CATEGORY = {
    "no-eval": Category.SECURITY,
    "no-implied-eval": Category.SECURITY,
    "no-new-func": Category.SECURITY,
    "no-script-url": Category.SECURITY,
    "no-unused-vars": Category.CODE_SMELL,
    "no-var": Category.STYLE,
    "eqeqeq": Category.BUG,
    "no-cond-assign": Category.BUG,
    "no-undef": Category.BUG,
    "no-unsafe-optional-chaining": Category.BUG,
    "no-unsafe-negation": Category.BUG,
    "no-async-promise-executor": Category.BUG,
    "no-promise-executor-return": Category.BUG,
    "require-atomic-updates": Category.BUG,
    "no-fallthrough": Category.BUG,
    "no-unreachable": Category.BUG,
}

_EXPLANATIONS = {
    "no-eval": "eval() executes arbitrary strings as code, which is a code-injection risk if any part of the string is influenced by user input.",
    "eqeqeq": "'==' performs type coercion before comparing, which produces surprising results (e.g. '' == 0 is true).",
    "no-unused-vars": "A declared variable is never read anywhere in its scope.",
    "no-async-promise-executor": "An async executor can throw asynchronously in a way the Promise constructor cannot catch, silently swallowing the rejection.",
    "no-undef": "The identifier is used without being declared or imported, which will throw a ReferenceError at runtime.",
}


class JavaScriptAnalyzer(BaseAnalyzer):
    language = "javascript"

    def __init__(self, timeout_seconds: int = 10) -> None:
        self.timeout_seconds = timeout_seconds
        self._node_path = shutil.which("node")

    def analyze(self, code: str, filename: str = "submitted_code.js") -> List[Finding]:
        if self._node_path is None or not _ESLINT_BIN.exists():
            logger.warning(
                "Node/ESLint not available (node=%s, eslint_bin_exists=%s)",
                self._node_path, _ESLINT_BIN.exists(),
            )
            return [
                Finding(
                    rule_id="analyzer-unavailable",
                    category=Category.MAINTAINABILITY,
                    severity=Severity.INFO,
                    message=(
                        "ESLint is not installed on this server "
                        "(run `npm install` in backend/tools/js-lint); "
                        "static analysis was skipped."
                    ),
                    source=FindingSource.STATIC_ANALYSIS,
                )
            ]

        safe_name = filename or "submitted_code.js"
        if not safe_name.lower().endswith((".js", ".jsx", ".mjs")):
            safe_name = f"{safe_name}.js"

        try:
            result = subprocess.run(
                [
                    self._node_path,
                    str(_ESLINT_BIN),
                    "--no-config-lookup",
                    "--config", str(_CONFIG_PATH),
                    "--format", "json",
                    "--stdin",
                    "--stdin-filename", safe_name,
                ],
                input=code,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                cwd=str(_TOOLS_DIR),
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning("eslint timed out after %ss", self.timeout_seconds)
            return [
                Finding(
                    rule_id="analyzer-timeout",
                    category=Category.MAINTAINABILITY,
                    severity=Severity.INFO,
                    message="Static analysis timed out and was skipped for this submission.",
                    source=FindingSource.STATIC_ANALYSIS,
                )
            ]

        return self._parse_eslint_json(result.stdout, safe_name)

    @staticmethod
    def _parse_eslint_json(stdout: str, filename: str) -> List[Finding]:
        if not stdout.strip():
            return []
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            logger.exception("Failed to parse ESLint JSON output")
            return []

        findings: List[Finding] = []
        for file_result in payload:
            for msg in file_result.get("messages", []):
                rule_id = msg.get("ruleId")
                if rule_id is None and not msg.get("fatal"):
                    # Meta-messages like "File ignored..." rather than a lint finding.
                    continue

                severity = _RULE_SEVERITY_OVERRIDE.get(
                    rule_id, _ESLINT_SEVERITY.get(msg.get("severity"), Severity.LOW)
                )
                # A syntax error surfaces with ruleId None and fatal=True;
                # always treat that as critical regardless of the mapping above.
                if msg.get("fatal"):
                    severity = Severity.CRITICAL

                findings.append(
                    Finding(
                        rule_id=rule_id or "syntax-error",
                        category=Category.BUG if msg.get("fatal") else _RULE_CATEGORY.get(rule_id, Category.STYLE),
                        severity=severity,
                        message=msg.get("message", "Unspecified issue"),
                        file=filename,
                        line=msg.get("line"),
                        column=msg.get("column"),
                        explanation=_EXPLANATIONS.get(rule_id),
                        source=FindingSource.STATIC_ANALYSIS,
                    )
                )
        return findings
