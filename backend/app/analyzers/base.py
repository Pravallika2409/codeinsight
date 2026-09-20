"""
Base interface that every language analyzer must implement.

Keeping this abstraction thin makes it straightforward to add new languages
(JavaScript, Java, ...) without touching the API layer.
"""
from abc import ABC, abstractmethod
from typing import List

from app.schemas.analysis import Finding


class BaseAnalyzer(ABC):
    """A language-specific static analyzer."""

    language: str

    @abstractmethod
    def analyze(self, code: str, filename: str) -> List[Finding]:
        """Run static analysis on `code` and return normalized findings.

        Implementations must never raise on malformed input — they should
        catch analyzer-specific errors and surface them as an INFO-level
        finding instead, so one bad submission can't crash the pipeline.
        """
        raise NotImplementedError
