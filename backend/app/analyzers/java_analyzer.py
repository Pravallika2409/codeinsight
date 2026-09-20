"""
Java static analyzer.

Combines two real, existing tools rather than a hand-rolled parser
(per project rule: "prefer using an existing linter/compiler where one
already exists"):

1. `javac` (the real Java compiler, invoked with `-Xlint:all`) for genuine
   compilation errors and compiler warnings (unchecked casts, deprecation,
   fallthrough, resource-related lint warnings, etc).
2. `javalang` -- a real Java parser -- for a small set of additional
   deterministic AST-based checks javac does not perform: empty catch
   blocks, overly broad exception catching, resources that are never
   closed, and best-effort unused local variable detection.

Security note: submitted code is written to a private temp file and
compiled with `javac` (never through a shell); this compiles the code but
never executes it. `-proc:none` disables annotation processing so nothing
resembling generated/executed code runs during analysis.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from app.analyzers.base import BaseAnalyzer
from app.schemas.analysis import Category, Finding, FindingSource, Severity

logger = logging.getLogger(__name__)

try:
    import javalang
    from javalang.parser import JavaSyntaxError
except ImportError:  # pragma: no cover - guarded at runtime, exercised in CI via requirements
    javalang = None
    JavaSyntaxError = Exception

_PUBLIC_CLASS_RE = re.compile(r"\bpublic\s+(?:final\s+|abstract\s+)?(?:class|interface|enum|record)\s+(\w+)")

# javac's own diagnostic kind maps onto our normalized severities.
_KIND_SEVERITY = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
}

# A handful of resource types where "declared but never in a
# try-with-resources block and never explicitly closed" is a genuine,
# well-known leak pattern.
_CLOSEABLE_TYPES = {
    "FileReader", "FileWriter", "BufferedReader", "BufferedWriter",
    "FileInputStream", "FileOutputStream", "Scanner", "Socket",
    "ServerSocket", "Connection", "Statement", "PreparedStatement",
    "ResultSet", "RandomAccessFile", "ZipFile", "InputStreamReader",
    "OutputStreamWriter",
}

_BROAD_EXCEPTION_TYPES = {"Exception", "Throwable", "RuntimeException"}

_CREDENTIAL_RE = re.compile(
    r'\b(?:password|passwd|secret|api[_-]?key|access[_-]?key)\s*=\s*"[^"]{3,}"',
    re.IGNORECASE,
)
_WEAK_HASH_RE = re.compile(r'MessageDigest\.getInstance\(\s*"(MD5|SHA-?1)"\s*\)', re.IGNORECASE)


class JavaAnalyzer(BaseAnalyzer):
    language = "java"

    def __init__(self, timeout_seconds: int = 15) -> None:
        self.timeout_seconds = timeout_seconds
        self._javac_path = shutil.which("javac")

    def analyze(self, code: str, filename: str = "Submission.java") -> List[Finding]:
        findings: List[Finding] = []
        findings.extend(self._run_javac(code, filename))
        findings.extend(self._run_ast_checks(code, filename))
        return findings

    # --- javac (real compiler) ---

    def _run_javac(self, code: str, filename: str) -> List[Finding]:
        if self._javac_path is None:
            logger.warning("javac binary not found on PATH")
            return [
                Finding(
                    rule_id="analyzer-unavailable",
                    category=Category.MAINTAINABILITY,
                    severity=Severity.INFO,
                    message="A JDK (javac) is not installed on this server; compiler diagnostics were skipped.",
                    source=FindingSource.STATIC_ANALYSIS,
                )
            ]

        class_name = self._detect_public_type_name(code)
        safe_name = f"{class_name}.java" if class_name else (filename or "Submission.java")
        if not safe_name.lower().endswith(".java"):
            safe_name = f"{safe_name}.java"

        with tempfile.TemporaryDirectory() as tmp_dir:
            src_path = Path(tmp_dir) / safe_name
            src_path.write_text(code, encoding="utf-8")

            try:
                result = subprocess.run(
                    [
                        self._javac_path,
                        "-Xlint:all",
                        "-proc:none",
                        "-d", tmp_dir,
                        str(src_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                logger.warning("javac timed out after %ss", self.timeout_seconds)
                return [
                    Finding(
                        rule_id="analyzer-timeout",
                        category=Category.MAINTAINABILITY,
                        severity=Severity.INFO,
                        message="Compilation timed out and was skipped for this submission.",
                        source=FindingSource.STATIC_ANALYSIS,
                    )
                ]

            return self._parse_javac_output(result.stderr, safe_name)

    @staticmethod
    def _detect_public_type_name(code: str) -> Optional[str]:
        match = _PUBLIC_CLASS_RE.search(code)
        return match.group(1) if match else None

    @staticmethod
    def _parse_javac_output(stderr: str, filename: str) -> List[Finding]:
        findings: List[Finding] = []
        # javac diagnostic lines look like:
        #   Submission.java:5: warning: [unchecked] unchecked call to ...
        #   Submission.java:9: error: cannot find symbol
        pattern = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+):\s*(?P<kind>error|warning):\s*(?P<msg>.*)$")
        for raw_line in stderr.splitlines():
            m = pattern.match(raw_line.strip())
            if not m:
                continue
            kind = m.group("kind")
            message = m.group("msg").strip()
            lint_tag_match = re.match(r"\[(\w[\w-]*)\]\s*(.*)", message)
            rule_id = f"javac-{lint_tag_match.group(1)}" if lint_tag_match else f"javac-{kind}"

            findings.append(
                Finding(
                    rule_id=rule_id,
                    category=Category.BUG if kind == "error" else Category.MAINTAINABILITY,
                    severity=_KIND_SEVERITY.get(kind, Severity.LOW),
                    message=message,
                    file=filename,
                    line=int(m.group("line")),
                    source=FindingSource.COMPILER,
                )
            )
        return findings

    # --- javalang AST-based checks ---

    def _run_ast_checks(self, code: str, filename: str) -> List[Finding]:
        if javalang is None:
            return []
        try:
            tree = javalang.parse.parse(code)
        except (JavaSyntaxError, Exception):
            # Already reported (or will be) by javac above; javalang's
            # grammar also lags newer Java syntax, so a parse failure here
            # is not itself reported as a separate finding.
            return []

        findings: List[Finding] = []
        for _, method in tree.filter(javalang.tree.MethodDeclaration):
            findings.extend(self._check_unused_locals(method, filename))
            findings.extend(self._check_unclosed_resources(method, filename))
        for _, try_stmt in tree.filter(javalang.tree.TryStatement):
            try_line = getattr(try_stmt, "position", None) and try_stmt.position.line
            for clause in try_stmt.catches or []:
                findings.extend(self._check_catch_clause(clause, filename, try_line))
        findings.extend(self._check_credentials_and_hashing(code, filename))
        return findings

    @staticmethod
    def _check_unused_locals(method, filename: str) -> List[Finding]:
        used_names = {ref.member for _, ref in method.filter(javalang.tree.MemberReference)}
        findings = []
        for _, decl_node in method.filter(javalang.tree.LocalVariableDeclaration):
            for declarator in decl_node.declarators:
                if declarator.name not in used_names:
                    findings.append(
                        Finding(
                            rule_id="unused-local-variable",
                            category=Category.CODE_SMELL,
                            severity=Severity.LOW,
                            message=f"Local variable '{declarator.name}' is declared but never used.",
                            file=filename,
                            line=getattr(decl_node, "position", None) and decl_node.position.line,
                            explanation="A best-effort check based on whether the variable's name appears anywhere else in the method body.",
                            suggestion="Remove the variable, or use it if it was meant to be used.",
                            source=FindingSource.STATIC_ANALYSIS,
                        )
                    )
        return findings

    @staticmethod
    def _check_unclosed_resources(method, filename: str) -> List[Finding]:
        try_resource_names = set()
        for _, try_stmt in method.filter(javalang.tree.TryStatement):
            for resource in try_stmt.resources or []:
                if hasattr(resource, "name"):
                    try_resource_names.add(resource.name)
        closed_names = {
            inv.qualifier
            for _, inv in method.filter(javalang.tree.MethodInvocation)
            if inv.member == "close" and inv.qualifier
        }

        findings = []
        for _, decl_node in method.filter(javalang.tree.LocalVariableDeclaration):
            type_name = getattr(decl_node.type, "name", None)
            if type_name not in _CLOSEABLE_TYPES:
                continue
            for declarator in decl_node.declarators:
                if declarator.name in try_resource_names or declarator.name in closed_names:
                    continue
                findings.append(
                    Finding(
                        rule_id="resource-not-closed",
                        category=Category.BUG,
                        severity=Severity.HIGH,
                        message=f"'{declarator.name}' ({type_name}) is never closed or used in try-with-resources.",
                        file=filename,
                        line=getattr(decl_node, "position", None) and decl_node.position.line,
                        explanation=f"{type_name} holds an OS resource (file handle, socket, etc.) that must be released.",
                        why_it_matters="Leaving resources open leaks file descriptors/handles and can exhaust system limits under load.",
                        suggestion=f"Declare '{declarator.name}' in a try-with-resources statement, e.g. `try ({type_name} {declarator.name} = ...) {{ ... }}`.",
                        source=FindingSource.STATIC_ANALYSIS,
                    )
                )
        return findings

    @staticmethod
    def _check_catch_clause(clause, filename: str, fallback_line: Optional[int]) -> List[Finding]:
        findings = []
        line = (getattr(clause, "position", None) and clause.position.line) or fallback_line
        if not clause.block:
            findings.append(
                Finding(
                    rule_id="empty-catch-block",
                    category=Category.CODE_SMELL,
                    severity=Severity.MEDIUM,
                    message="Catch block is empty -- the exception is silently swallowed.",
                    file=filename,
                    line=line,
                    why_it_matters="Silently discarding exceptions hides real failures and makes bugs very hard to diagnose later.",
                    suggestion="At minimum, log the exception; ideally handle it or rethrow a more specific error.",
                    source=FindingSource.STATIC_ANALYSIS,
                )
            )
        if any(t in _BROAD_EXCEPTION_TYPES for t in clause.parameter.types):
            findings.append(
                Finding(
                    rule_id="broad-exception-catch",
                    category=Category.CODE_SMELL,
                    severity=Severity.LOW,
                    message=f"Catching '{'/'.join(clause.parameter.types)}' is broader than usually necessary.",
                    file=filename,
                    line=line,
                    suggestion="Catch the most specific exception type(s) the code can actually throw.",
                    source=FindingSource.STATIC_ANALYSIS,
                )
            )
        return findings

    @staticmethod
    def _check_credentials_and_hashing(code: str, filename: str) -> List[Finding]:
        findings = []
        for match in _CREDENTIAL_RE.finditer(code):
            line = code.count("\n", 0, match.start()) + 1
            findings.append(
                Finding(
                    rule_id="hardcoded-credential",
                    category=Category.SECURITY,
                    severity=Severity.CRITICAL,
                    message="A password/secret/API key appears to be hardcoded as a string literal.",
                    file=filename,
                    line=line,
                    why_it_matters="Hardcoded secrets end up in version control and compiled artifacts, where they are easy to extract.",
                    suggestion="Load credentials from environment variables or a secrets manager instead.",
                    source=FindingSource.STATIC_ANALYSIS,
                )
            )
        for match in _WEAK_HASH_RE.finditer(code):
            line = code.count("\n", 0, match.start()) + 1
            findings.append(
                Finding(
                    rule_id="weak-hash-algorithm",
                    category=Category.SECURITY,
                    severity=Severity.MEDIUM,
                    message=f"'{match.group(1)}' is a cryptographically weak hash algorithm.",
                    file=filename,
                    line=line,
                    suggestion="Use SHA-256 or stronger for anything security-sensitive.",
                    source=FindingSource.STATIC_ANALYSIS,
                )
            )
        return findings
