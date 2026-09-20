"""
Time/space complexity estimation.

This is a heuristic, static estimator based on loop-nesting depth and a
few recognizable patterns (binary search, common sort calls). It cannot
"prove" complexity the way a human reviewer reasoning about an algorithm
can, so every result is explicitly labeled as an estimate — this module
must never present a guess as a guaranteed fact.
"""
from __future__ import annotations

import ast
import re

from app.schemas.analysis import ComplexityEstimate, Language

_BIG_O_BY_DEPTH = {0: "O(1)", 1: "O(n)", 2: "O(n\u00b2)", 3: "O(n\u00b3)"}


def estimate_complexity(code: str, language: Language) -> ComplexityEstimate:
    if language == Language.PYTHON:
        return _estimate_python(code)
    return _estimate_by_brace_heuristic(code)


def _estimate_python(code: str) -> ComplexityEstimate:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ComplexityEstimate(
            time_complexity=None,
            space_complexity=None,
            is_estimated=True,
            notes="Complexity could not be estimated because the code does not parse.",
        )

    max_depth = _max_loop_depth(tree)
    time_complexity = _label_for_depth(max_depth)

    if _uses_binary_search_pattern(code):
        time_complexity = "O(log n)"
    elif re.search(r"\.sort\(|sorted\(", code):
        time_complexity = "O(n log n)" if max_depth <= 1 else time_complexity

    space_complexity = "O(n)" if re.search(r"=\s*\[.*for .* in .*\]|\.append\(", code) else "O(1)"

    return ComplexityEstimate(
        time_complexity=time_complexity,
        space_complexity=space_complexity,
        is_estimated=True,
        notes="Estimated from loop-nesting depth and recognizable patterns; not a formal proof.",
    )


def _max_loop_depth(tree: ast.AST, current: int = 0) -> int:
    max_depth = current
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.For, ast.While)):
            depth = _max_loop_depth(node, current + 1)
        else:
            depth = _max_loop_depth(node, current)
        max_depth = max(max_depth, depth)
    return max_depth


def _uses_binary_search_pattern(code: str) -> bool:
    lowered = code.lower()
    return "while" in lowered and ("mid" in lowered) and ("low" in lowered or "left" in lowered)


def _label_for_depth(depth: int) -> str:
    return _BIG_O_BY_DEPTH.get(depth, f"O(n^{depth})")


def _estimate_by_brace_heuristic(code: str) -> ComplexityEstimate:
    """Fallback for C-family languages: track nested for/while loop depth
    via a simple brace-aware scan. Deliberately conservative."""
    max_depth = 0
    depth = 0
    loop_stack = []
    for line in code.splitlines():
        stripped = line.strip()
        if re.match(r"(for|while)\s*\(", stripped):
            loop_stack.append(depth)
        depth += stripped.count("{") - stripped.count("}")
        if loop_stack:
            max_depth = max(max_depth, len(loop_stack))
        # Pop finished loop scopes once brace depth returns to/below entry.
        loop_stack = [d for d in loop_stack if depth > d]

    return ComplexityEstimate(
        time_complexity=_label_for_depth(min(max_depth, 3)),
        space_complexity="O(1)" if "new " not in code and "malloc(" not in code else "O(n)",
        is_estimated=True,
        notes="Estimated from loop-nesting depth via static scanning; not a formal proof.",
    )
