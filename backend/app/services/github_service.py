"""
Fetches supported source files from a public (or, with GITHUB_TOKEN, private)
GitHub repository for repository-level analysis (Phase 6).

Uses the real GitHub REST API (Git Trees API to list files, raw.githubusercontent.com
to fetch content) -- no scraping, no git clone (keeps the container's
filesystem untouched by arbitrary repo contents; only the specific files we
decide to analyze are ever pulled, and only their text content, never
executed).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Tuple

import httpx

from app.core.config import Settings
from app.schemas.enums import Language

logger = logging.getLogger(__name__)

_EXTENSION_LANGUAGE: dict[str, Language] = {
    ".cpp": Language.CPP, ".cc": Language.CPP, ".cxx": Language.CPP,
    ".h": Language.CPP, ".hpp": Language.CPP,
    ".py": Language.PYTHON,
    ".js": Language.JAVASCRIPT, ".jsx": Language.JAVASCRIPT, ".mjs": Language.JAVASCRIPT,
    ".java": Language.JAVA,
}

_REPO_URL_RE = re.compile(
    r"^(?:https?://github\.com/)?(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git|/)?$"
)


class GitHubServiceError(Exception):
    """Raised for any GitHub API failure (not found, rate-limited, network
    error, etc). Callers convert this into a clean, safe error message --
    never a raw traceback.
    """


@dataclass
class RepoFile:
    path: str
    language: Language
    content: str


@dataclass
class RepoFetchResult:
    owner: str
    repo: str
    default_branch: str
    files: List[RepoFile]
    files_skipped: int  # unsupported extension, or over the per-file size cap
    truncated: bool  # GitHub's tree API itself truncated (repo too large to list fully)


def parse_repo_slug(repo_url_or_slug: str) -> Tuple[str, str]:
    """Accepts "https://github.com/owner/repo", "github.com/owner/repo", or
    "owner/repo" and returns (owner, repo).
    """
    match = _REPO_URL_RE.match(repo_url_or_slug.strip())
    if not match:
        raise GitHubServiceError(
            f"'{repo_url_or_slug}' doesn't look like a GitHub repository "
            "(expected 'owner/repo' or a github.com URL)."
        )
    return match.group("owner"), match.group("repo")


def _headers(settings: Settings) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "codeinsight-ai",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
    return headers


def fetch_repo_files(repo_url_or_slug: str, settings: Settings) -> RepoFetchResult:
    owner, repo = parse_repo_slug(repo_url_or_slug)
    headers = _headers(settings)
    timeout = settings.GITHUB_API_TIMEOUT_SECONDS

    with httpx.Client(timeout=timeout, headers=headers) as client:
        try:
            repo_resp = client.get(f"https://api.github.com/repos/{owner}/{repo}")
        except httpx.HTTPError as exc:
            raise GitHubServiceError(f"Could not reach GitHub: {exc}") from exc

        if repo_resp.status_code == 404:
            raise GitHubServiceError(f"Repository '{owner}/{repo}' was not found (or is private without a token).")
        if repo_resp.status_code == 403:
            raise GitHubServiceError("GitHub API rate limit exceeded. Try again later or configure GITHUB_TOKEN.")
        if repo_resp.status_code != 200:
            raise GitHubServiceError(f"GitHub API returned an unexpected status ({repo_resp.status_code}).")

        default_branch = repo_resp.json().get("default_branch", "main")

        try:
            tree_resp = client.get(
                f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}",
                params={"recursive": "1"},
            )
        except httpx.HTTPError as exc:
            raise GitHubServiceError(f"Could not reach GitHub: {exc}") from exc

        if tree_resp.status_code != 200:
            raise GitHubServiceError(f"Could not list repository files (status {tree_resp.status_code}).")

        tree_data = tree_resp.json()
        truncated = bool(tree_data.get("truncated", False))

        candidates = []
        for entry in tree_data.get("tree", []):
            if entry.get("type") != "blob":
                continue
            path = entry["path"]
            ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
            language = _EXTENSION_LANGUAGE.get(ext.lower())
            if language is None:
                continue
            if entry.get("size", 0) > settings.GITHUB_MAX_FILE_SIZE_BYTES:
                continue
            candidates.append((path, language))

        files_skipped = max(0, len(candidates) - settings.GITHUB_MAX_FILES)
        selected = candidates[: settings.GITHUB_MAX_FILES]

        files: List[RepoFile] = []
        for path, language in selected:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{default_branch}/{path}"
            try:
                content_resp = client.get(raw_url)
            except httpx.HTTPError as exc:
                logger.warning("Failed to fetch %s from %s/%s: %s", path, owner, repo, exc)
                files_skipped += 1
                continue
            if content_resp.status_code != 200:
                logger.warning("Unexpected status %s fetching %s", content_resp.status_code, path)
                files_skipped += 1
                continue
            files.append(RepoFile(path=path, language=language, content=content_resp.text))

    return RepoFetchResult(
        owner=owner,
        repo=repo,
        default_branch=default_branch,
        files=files,
        files_skipped=files_skipped,
        truncated=truncated,
    )
