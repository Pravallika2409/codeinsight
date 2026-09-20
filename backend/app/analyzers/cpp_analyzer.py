"""
C++ static analyzer.

Wraps the `cppcheck` command-line tool rather than hand-rolling a fragile
C++ parser (per project rule: "prefer using an existing linter/compiler
where one already exists"). cppcheck is a real, widely used static
analyzer, so findings here are genuine tool output, not fabricated data.

Security note: submitted code is written to a private temp file and passed
to cppcheck as a *file argument* (never through a shell), with a hard
subprocess timeout. cppcheck itself does not execute the submitted code.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

from app.analyzers.base import BaseAnalyzer
from app.schemas.analysis import Category, Finding, FindingSource, Severity

logger = logging.getLogger(__name__)

# Maps cppcheck's own severity vocabulary onto our normalized levels.
_SEVERITY_MAP = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "style": Severity.LOW,
    "performance": Severity.MEDIUM,
    "portability": Severity.LOW,
    "information": Severity.INFO,
}

# A handful of cppcheck rule ids that indicate genuinely dangerous patterns
# get bumped to CRITICAL regardless of cppcheck's own severity label.
_CRITICAL_RULE_IDS = {
    "arrayIndexOutOfBounds",
    "nullPointer",
    "uninitvar",
    "doubleFree",
    "memleak",
    "bufferAccessOutOfBounds",
}

_EXPLANATIONS = {
    "arrayIndexOutOfBounds": "The code accesses an array index that may be outside its valid bounds.",
    "nullPointer": "A pointer that may be null is dereferenced.",
    "uninitvar": "A variable is used before it has been assigned a value.",
    "doubleFree": "Memory is freed more than once, which causes undefined behavior.",
    "memleak": "Allocated memory is never released, causing a memory leak.",
    "bufferAccessOutOfBounds": "A buffer is accessed outside of its allocated size.",
}


class CppAnalyzer(BaseAnalyzer):
    language = "cpp"

    def __init__(self, timeout_seconds: int = 10) -> None:
        self.timeout_seconds = timeout_seconds
        self._cppcheck_path = shutil.which("cppcheck")

    def analyze(self, code: str, filename: str = "submitted_code.cpp") -> List[Finding]:
        if self._cppcheck_path is None:
            logger.warning("cppcheck binary not found on PATH")
            return [
                Finding(
                    rule_id="analyzer-unavailable",
                    category=Category.MAINTAINABILITY,
                    severity=Severity.INFO,
                    message="cppcheck is not installed on this server; static analysis was skipped.",
                    source=FindingSource.STATIC_ANALYSIS,
                )
            ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            safe_name = filename or "submitted_code.cpp"
            # cppcheck infers the language from the file extension, not from
            # content -- without a recognized C/C++ suffix it silently
            # misparses the file and reports a bogus syntaxError instead of
            # real findings. Force a .cpp extension whenever the caller's
            # filename doesn't already have one cppcheck recognizes.
            if not safe_name.lower().endswith((".cpp", ".cc", ".cxx", ".c", ".h", ".hpp")):
                safe_name = f"{safe_name}.cpp"
            src_path = Path(tmp_dir) / safe_name
            src_path.write_text(code, encoding="utf-8")

            try:
                result = subprocess.run(
                    [
                        self._cppcheck_path,
                        "--enable=warning,style,performance,portability",
                        "--inline-suppr",
                        "--xml",
                        "--xml-version=2",
                        str(src_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                logger.warning("cppcheck timed out after %ss", self.timeout_seconds)
                return [
                    Finding(
                        rule_id="analyzer-timeout",
                        category=Category.MAINTAINABILITY,
                        severity=Severity.INFO,
                        message="Static analysis timed out and was skipped for this submission.",
                        source=FindingSource.STATIC_ANALYSIS,
                    )
                ]

            return self._parse_xml(result.stderr, filename)

    def _parse_xml(self, xml_output: str, filename: str) -> List[Finding]:
        findings: List[Finding] = []
        if not xml_output.strip():
            return findings

        try:
            root = ET.fromstring(xml_output)
        except ET.ParseError:
            logger.exception("Failed to parse cppcheck XML output")
            return findings

        for error in root.iter("error"):
            rule_id = error.get("id", "unknown")
            cppcheck_severity = error.get("severity", "style")
            message = error.get("verbose") or error.get("msg") or "Unspecified issue"

            location = error.find("location")
            line = int(location.get("line")) if location is not None and location.get("line") else None
            column = int(location.get("column")) if location is not None and location.get("column") else None

            severity = _SEVERITY_MAP.get(cppcheck_severity, Severity.LOW)
            if rule_id in _CRITICAL_RULE_IDS:
                severity = Severity.CRITICAL

            category = Category.SECURITY if rule_id in _CRITICAL_RULE_IDS else (
                Category.PERFORMANCE if cppcheck_severity == "performance" else
                Category.BUG if cppcheck_severity in ("error", "warning") else
                Category.STYLE
            )

            findings.append(
                Finding(
                    rule_id=rule_id,
                    category=category,
                    severity=severity,
                    message=message,
                    file=filename,
                    line=line,
                    column=column,
                    explanation=_EXPLANATIONS.get(rule_id),
                    source=FindingSource.STATIC_ANALYSIS,
                )
            )

        return findings
