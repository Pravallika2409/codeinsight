from tests import sample_code


# --- Secure headers ---

def test_secure_headers_present_on_normal_response(client):
    resp = client.get("/api/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "content-security-policy" in resp.headers
    assert resp.headers["strict-transport-security"].startswith("max-age=")


def test_docs_page_has_no_strict_csp(client):
    resp = client.get("/docs")
    # Swagger UI needs to load its own JS/CSS; a strict default-src 'none'
    # CSP would break it, so /docs is deliberately excluded.
    assert "content-security-policy" not in resp.headers


def test_health_reports_redis_status(client):
    body = client.get("/api/health").json()
    assert body["redis"] == "available"  # fakeredis fixture is healthy by construction


# --- Caching ---

def test_identical_analyze_requests_are_served_from_cache(client, monkeypatch):
    from app.api import analyze as analyze_module

    call_count = {"n": 0}
    original = analyze_module.run_analysis

    def counting_run_analysis(request):
        call_count["n"] += 1
        return original(request)

    monkeypatch.setattr(analyze_module, "run_analysis", counting_run_analysis)

    payload = {"code": sample_code.PYTHON_MUTABLE_DEFAULT, "language": "python", "filename": "a.py"}
    first = client.post("/api/analyze", json=payload)
    second = client.post("/api/analyze", json=payload)

    assert first.status_code == second.status_code == 200
    assert call_count["n"] == 1  # second request was a cache hit, not recomputed
    assert first.json()["findings"] == second.json()["findings"]


def test_different_code_is_not_a_cache_hit(client, monkeypatch):
    from app.api import analyze as analyze_module

    call_count = {"n": 0}
    original = analyze_module.run_analysis

    def counting_run_analysis(request):
        call_count["n"] += 1
        return original(request)

    monkeypatch.setattr(analyze_module, "run_analysis", counting_run_analysis)

    client.post("/api/analyze", json={"code": sample_code.PYTHON_CLEAN, "language": "python"})
    client.post("/api/analyze", json={"code": sample_code.PYTHON_MUTABLE_DEFAULT, "language": "python"})
    assert call_count["n"] == 2


def test_cache_survives_a_redis_outage_by_failing_open(client, monkeypatch):
    import redis as redis_module

    class _BrokenRedis:
        def get(self, *a, **k):
            raise redis_module.RedisError("simulated outage")

        def setex(self, *a, **k):
            raise redis_module.RedisError("simulated outage")

        def incr(self, *a, **k):
            raise redis_module.RedisError("simulated outage")

    from app.core.redis_client import get_redis_client
    from app.main import app as fastapi_app

    fastapi_app.dependency_overrides[get_redis_client] = lambda: _BrokenRedis()
    try:
        resp = client.post("/api/analyze", json={"code": sample_code.PYTHON_CLEAN, "language": "python"})
        assert resp.status_code == 200  # never fails just because Redis is down
    finally:
        del fastapi_app.dependency_overrides[get_redis_client]


# --- Rate limiting ---

def test_analyze_rate_limit_returns_429_once_exceeded(client, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "RATE_LIMIT_ANALYZE_PER_MINUTE", 2)

    payload = {"code": sample_code.PYTHON_CLEAN, "language": "python"}
    r1 = client.post("/api/analyze", json=payload)
    r2 = client.post("/api/analyze", json=payload)
    r3 = client.post("/api/analyze", json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429


def test_login_rate_limit_returns_429_once_exceeded(client, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN_PER_MINUTE", 1)

    client.post("/api/auth/register", json={"email": "ratelimited@example.com", "password": "correct-horse-battery"})
    payload = {"email": "ratelimited@example.com", "password": "correct-horse-battery"}
    r1 = client.post("/api/auth/login", json=payload)
    r2 = client.post("/api/auth/login", json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 429


def test_rate_limiting_can_be_disabled(client, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "RATE_LIMIT_ANALYZE_PER_MINUTE", 1)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)

    payload = {"code": sample_code.PYTHON_CLEAN, "language": "python"}
    for _ in range(5):
        resp = client.post("/api/analyze", json=payload)
        assert resp.status_code == 200


# --- Async analysis via Celery (eager mode in tests -- see conftest.py) ---

def test_analyze_async_enqueues_and_completes(client):
    resp = client.post(
        "/api/analyze/async",
        json={"code": sample_code.PYTHON_MUTABLE_DEFAULT, "language": "python"},
    )
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]

    status_resp = client.get(f"/api/tasks/{task_id}")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] == "success"
    assert any(f["rule_id"] == "mutable-default-argument" for f in body["result"]["findings"])


def test_analyze_async_rejects_oversized_payload_before_enqueueing(client, monkeypatch):
    from app.api import tasks as tasks_module

    monkeypatch.setattr(tasks_module.settings, "MAX_CODE_SIZE_BYTES", 10)
    resp = client.post("/api/analyze/async", json={"code": "print('hello world')", "language": "python"})
    assert resp.status_code == 413


def test_analyze_async_with_project_id_requires_auth(client):
    resp = client.post(
        "/api/analyze/async",
        json={"code": sample_code.PYTHON_CLEAN, "language": "python", "project_id": 1},
    )
    assert resp.status_code == 401


def test_analyze_async_with_project_id_persists(client, auth_headers):
    headers = auth_headers()
    project = client.post("/api/projects", json={"name": "Async project"}, headers=headers).json()

    resp = client.post(
        "/api/analyze/async",
        json={
            "code": sample_code.PYTHON_CLEAN,
            "language": "python",
            "filename": "async.py",
            "project_id": project["id"],
        },
        headers=headers,
    )
    task_id = resp.json()["task_id"]
    status_resp = client.get(f"/api/tasks/{task_id}", headers=headers)
    result = status_resp.json()["result"]
    assert result["analysis_id"] is not None

    history = client.get("/api/analysis/history", headers=headers).json()
    assert len(history) == 1
    assert history[0]["filename"] == "async.py"


def test_task_status_for_unknown_id_is_pending(client):
    # A made-up id that was never enqueued looks like "pending" to Celery
    # (there's no record to say otherwise) -- documenting this rather than
    # treating it as a bug in our code.
    resp = client.get("/api/tasks/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"
