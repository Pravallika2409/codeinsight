"""
Language identification.

Phase 1 keeps this deliberately simple: the frontend lets the user pick a
language explicitly (this is more reliable than guessing), and this module
just validates that choice and offers a best-effort heuristic fallback for
callers that only supply a filename.
"""
from __future__ import annotations

from app.schemas.analysis import Language

_EXTENSION_MAP = {
    ".cpp": Language.CPP,
    ".cc": Language.CPP,
    ".cxx": Language.CPP,
    ".hpp": Language.CPP,
    ".h": Language.CPP,
    ".py": Language.PYTHON,
    ".js": Language.JAVASCRIPT,
    ".jsx": Language.JAVASCRIPT,
    ".java": Language.JAVA,
}


def detect_from_filename(filename: str) -> Language | None:
    for ext, lang in _EXTENSION_MAP.items():
        if filename.lower().endswith(ext):
            return lang
    return None
