"""
Python static analyzer.

Combines two real, existing tools rather than a hand-rolled parser:

1. `pyflakes` (via its public API) for undefined names, unused
   imports/variables, and syntax errors.
2. Python's own `ast` module for a small set of additional deterministic
   checks that pyflakes does not cover (mutable default arguments, bare
   `except:` clauses, use of `eval`).
"""
from __future__ import annotations

import ast
import io
import logging
from typing import List

from pyflakes.api import check
from pyflakes.reporter import Reporter

from app.analyzers.base import BaseAnalyzer
from app.schemas.analysis import Category, Finding, FindingSource, Severity

logger = logging.getLogger(__name__)


class PythonAnalyzer(BaseAnalyzer):
    language = "python"

    def analyze(self, code: str, filename: str = "submitted_code.py") -> List[Finding]:
        findings: List[Finding] = []
        findings.extend(self._run_pyflakes(code, filename))
        findings.extend(self._run_ast_checks(code, filename))
        return findings

    # --- pyflakes ---

    def _run_pyflakes(self, code: str, filename: str) -> List[Finding]:
        out, err = io.StringIO(), io.StringIO()
        reporter = Reporter(out, err)
        try:
            check(code, filename, reporter)
        except Exception:
            logger.exception("pyflakes crashed on submitted code")
            return []

        findings: List[Finding] = []
        for stream, is_syntax_error in ((err, True), (out, False)):
            for raw_line in stream.getvalue().splitlines():
                finding = self._parse_pyflakes_line(raw_line, filename, is_syntax_error)
                if finding:
                    findings.append(finding)
        return findings

    @staticmethod
    def _parse_pyflakes_line(raw_line: str, filename: str, is_syntax_error: bool) -> Finding | None:
        # pyflakes lines look like: "<filename>:<line>:<col>: <message>"
        parts = raw_line.split(":", 3)
        if len(parts) < 4:
            return None
        _, line_str, col_str, message = parts
        try:
            line = int(line_str)
        except ValueError:
            line = None
        try:
            column = int(col_str)
        except ValueError:
            column = None

        message = message.strip()
        rule_id = "syntax-error" if is_syntax_error else "pyflakes-" + message.split(" ")[0].lower().strip("'")

        return Finding(
            rule_id=rule_id,
            category=Category.BUG,
            severity=Severity.CRITICAL if is_syntax_error else Severity.MEDIUM,
            message=message,
            file=filename,
            line=line,
            column=column,
            source=FindingSource.STATIC_ANALYSIS,
        )

    # --- AST-based checks ---

    def _run_ast_checks(self, code: str, filename: str) -> List[Finding]:
        try:
            tree = ast.parse(code, filename=filename)
        except SyntaxError:
            # Already reported by pyflakes above.
            return []

        findings: List[Finding] = []
        for node in ast.walk(tree):
            findings.extend(self._check_mutable_default(node, filename))
            findings.extend(self._check_bare_except(node, filename))
            findings.extend(self._check_eval_usage(node, filename))
        return findings

    @staticmethod
    def _check_mutable_default(node: ast.AST, filename: str) -> List[Finding]:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return []
        findings = []
        for default in list(node.args.defaults) + list(node.args.kw_defaults):
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                findings.append(
                    Finding(
                        rule_id="mutable-default-argument",
                        category=Category.BUG,
                        severity=Severity.MEDIUM,
                        message=f"Function '{node.name}' uses a mutable default argument.",
                        file=filename,
                        line=node.lineno,
                        explanation=(
                            "Mutable default arguments (lists, dicts, sets) are created once "
                            "at function-definition time and shared across all calls."
                        ),
                        why_it_matters=(
                            "Mutating the default in one call silently leaks state into every "
                            "future call of the function, producing hard-to-reproduce bugs."
                        ),
                        suggestion="Use `None` as the default and create the mutable object inside the function body.",
                        source=FindingSource.STATIC_ANALYSIS,
                    )
                )
        return findings

    @staticmethod
    def _check_bare_except(node: ast.AST, filename: str) -> List[Finding]:
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            return [
                Finding(
                    rule_id="bare-except",
                    category=Category.CODE_SMELL,
                    severity=Severity.MEDIUM,
                    message="Bare 'except:' clause catches all exceptions, including SystemExit and KeyboardInterrupt.",
                    file=filename,
                    line=node.lineno,
                    suggestion="Catch a specific exception type, e.g. `except ValueError:`.",
                    source=FindingSource.STATIC_ANALYSIS,
                )
            ]
        return []

    @staticmethod
    def _check_eval_usage(node: ast.AST, filename: str) -> List[Finding]:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
            return [
                Finding(
                    rule_id="dangerous-eval",
                    category=Category.SECURITY,
                    severity=Severity.HIGH,
                    message=f"Use of '{node.func.id}()' can execute arbitrary code.",
                    file=filename,
                    line=node.lineno,
                    why_it_matters="If any part of the evaluated string is influenced by user input, this is a code-injection vulnerability.",
                    suggestion="Avoid eval/exec; use safer alternatives such as ast.literal_eval for data parsing.",
                    source=FindingSource.STATIC_ANALYSIS,
                )
            ]
        return []
