from tests import sample_code


# --- parse_repo_slug ---

def test_parse_repo_slug_accepts_various_formats():
    from app.services.github_service import parse_repo_slug

    assert parse_repo_slug("owner/repo") == ("owner", "repo")
    assert parse_repo_slug("https://github.com/owner/repo") == ("owner", "repo")
    assert parse_repo_slug("https://github.com/owner/repo/") == ("owner", "repo")
    assert parse_repo_slug("https://github.com/owner/repo.git") == ("owner", "repo")


def test_parse_repo_slug_rejects_garbage():
    from app.services.github_service import GitHubServiceError, parse_repo_slug

    import pytest
    with pytest.raises(GitHubServiceError):
        parse_repo_slug("not a repo at all !!")


# --- GitHub analysis endpoint (mocked fetch -- real network verified manually, see README) ---

def _fake_fetch_result(owner="octo", repo="demo"):
    from app.services.github_service import RepoFetchResult, RepoFile
    from app.schemas.enums import Language

    return RepoFetchResult(
        owner=owner,
        repo=repo,
        default_branch="main",
        files=[
            RepoFile(path="utils.py", language=Language.PYTHON, content=sample_code.PYTHON_MUTABLE_DEFAULT),
            RepoFile(path="clean.py", language=Language.PYTHON, content=sample_code.PYTHON_CLEAN),
        ],
        files_skipped=1,
        truncated=False,
    )


def test_github_analyze_requires_auth(client):
    resp = client.post("/api/github/analyze", json={"repo_url": "octo/demo", "project_id": 1})
    assert resp.status_code == 401


def test_github_analyze_enqueues_and_completes(client, auth_headers, monkeypatch):
    from app.tasks import github_tasks

    monkeypatch.setattr(github_tasks, "fetch_repo_files", lambda repo_url, settings: _fake_fetch_result())

    headers = auth_headers()
    project = client.post("/api/projects", json={"name": "Repo import"}, headers=headers).json()

    resp = client.post(
        "/api/github/analyze",
        json={"repo_url": "octo/demo", "project_id": project["id"]},
        headers=headers,
    )
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]

    status_resp = client.get(f"/api/github/analyze/{task_id}", headers=headers)
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] == "success"
    report = body["result"]
    assert report["repo"] == "octo/demo"
    assert report["files_analyzed"] == 2
    assert report["files_skipped"] == 1
    assert len(report["files"]) == 2
    assert any(f["path"] == "utils.py" for f in report["files"])

    # Each file was persisted as its own analysis run under the project.
    history = client.get(f"/api/analysis/history?project_id={project['id']}", headers=headers).json()
    assert len(history) == 2
    filenames = {h["filename"] for h in history}
    assert filenames == {"utils.py", "clean.py"}

    project_after = client.get(f"/api/projects/{project['id']}", headers=headers).json()
    assert project_after["file_count"] == 2


def test_github_analyze_rejects_project_not_owned(client, auth_headers, monkeypatch):
    from app.tasks import github_tasks

    monkeypatch.setattr(github_tasks, "fetch_repo_files", lambda repo_url, settings: _fake_fetch_result())

    headers_a = auth_headers("repoowner@example.com")
    headers_b = auth_headers("repointruder@example.com")
    project = client.post("/api/projects", json={"name": "Not yours"}, headers=headers_a).json()

    resp = client.post(
        "/api/github/analyze",
        json={"repo_url": "octo/demo", "project_id": project["id"]},
        headers=headers_b,
    )
    task_id = resp.json()["task_id"]
    status_resp = client.get(f"/api/github/analyze/{task_id}", headers=headers_b)
    assert status_resp.json()["status"] == "failure"


def test_github_analyze_reports_fetch_error_gracefully(client, auth_headers, monkeypatch):
    from app.tasks import github_tasks
    from app.services.github_service import GitHubServiceError

    def _raise(repo_url, settings):
        raise GitHubServiceError("Repository 'nope/nope' was not found (or is private without a token).")

    monkeypatch.setattr(github_tasks, "fetch_repo_files", _raise)

    headers = auth_headers()
    project = client.post("/api/projects", json={"name": "Bad repo"}, headers=headers).json()
    resp = client.post(
        "/api/github/analyze",
        json={"repo_url": "nope/nope", "project_id": project["id"]},
        headers=headers,
    )
    task_id = resp.json()["task_id"]
    status_resp = client.get(f"/api/github/analyze/{task_id}", headers=headers)
    body = status_resp.json()
    assert body["status"] == "failure"
    assert "not found" in body["error"]


# --- Project analytics ---

def test_analytics_requires_auth(client):
    assert client.get("/api/projects/1/analytics").status_code == 401


def test_analytics_for_empty_project(client, auth_headers):
    headers = auth_headers()
    project = client.post("/api/projects", json={"name": "Empty"}, headers=headers).json()
    resp = client.get(f"/api/projects/{project['id']}/analytics", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_runs"] == 0
    assert body["average_score"] is None


def test_analytics_aggregates_multiple_runs(client, auth_headers):
    headers = auth_headers()
    project = client.post("/api/projects", json={"name": "Analytics"}, headers=headers).json()

    client.post(
        "/api/analyze",
        json={"code": sample_code.PYTHON_MUTABLE_DEFAULT, "language": "python", "filename": "a.py", "project_id": project["id"]},
        headers=headers,
    )
    client.post(
        "/api/analyze",
        json={"code": sample_code.PYTHON_CLEAN, "language": "python", "filename": "b.py", "project_id": project["id"]},
        headers=headers,
    )

    resp = client.get(f"/api/projects/{project['id']}/analytics", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_runs"] == 2
    assert body["average_score"] is not None
    assert body["language_breakdown"] == {"python": 2}
    assert len(body["score_trend"]) == 2
    assert len(body["worst_files"]) <= 2
    assert any(rf["rule_id"] == "mutable-default-argument" for rf in body["top_rule_ids"])


def test_analytics_for_project_not_owned_is_404(client, auth_headers):
    headers_a = auth_headers("analyticsowner@example.com")
    headers_b = auth_headers("analyticsintruder@example.com")
    project = client.post("/api/projects", json={"name": "Private analytics"}, headers=headers_a).json()

    resp = client.get(f"/api/projects/{project['id']}/analytics", headers=headers_b)
    assert resp.status_code == 404
