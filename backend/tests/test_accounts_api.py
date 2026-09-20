from tests import sample_code


# --- Auth ---

def test_register_and_login(client):
    resp = client.post("/api/auth/register", json={"email": "a@example.com", "password": "correct-horse-battery"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "a@example.com"
    assert "hashed_password" not in body  # never leak the hash

    resp = client.post("/api/auth/login", json={"email": "a@example.com", "password": "correct-horse-battery"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_register_rejects_duplicate_email(client):
    payload = {"email": "dup@example.com", "password": "correct-horse-battery"}
    client.post("/api/auth/register", json=payload)
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 409


def test_login_rejects_wrong_password(client):
    client.post("/api/auth/register", json={"email": "b@example.com", "password": "correct-horse-battery"})
    resp = client.post("/api/auth/login", json={"email": "b@example.com", "password": "wrong-password"})
    assert resp.status_code == 401


def test_login_rejects_unknown_email(client):
    resp = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever123"})
    assert resp.status_code == 401


def test_users_me_requires_auth(client):
    resp = client.get("/api/users/me")
    assert resp.status_code == 401


def test_users_me_returns_profile(client, auth_headers):
    headers = auth_headers()
    resp = client.get("/api/users/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "dev@example.com"


def test_register_rejects_short_password(client):
    resp = client.post("/api/auth/register", json={"email": "short@example.com", "password": "short"})
    assert resp.status_code == 422


# --- Projects ---

def test_projects_require_auth(client):
    assert client.get("/api/projects").status_code == 401
    assert client.post("/api/projects", json={"name": "x"}).status_code == 401


def test_create_and_list_projects(client, auth_headers):
    headers = auth_headers()
    resp = client.post("/api/projects", json={"name": "My Project", "description": "test"}, headers=headers)
    assert resp.status_code == 201
    project = resp.json()
    assert project["name"] == "My Project"
    assert project["file_count"] == 0

    resp = client.get("/api/projects", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_cannot_see_another_users_project(client, auth_headers):
    headers_a = auth_headers("owner@example.com")
    headers_b = auth_headers("intruder@example.com")

    project = client.post("/api/projects", json={"name": "Private"}, headers=headers_a).json()

    resp = client.get(f"/api/projects/{project['id']}", headers=headers_b)
    assert resp.status_code == 404  # not 403 -- never confirm the id exists

    resp = client.delete(f"/api/projects/{project['id']}", headers=headers_b)
    assert resp.status_code == 404


def test_delete_project(client, auth_headers):
    headers = auth_headers()
    project = client.post("/api/projects", json={"name": "Temp"}, headers=headers).json()
    resp = client.delete(f"/api/projects/{project['id']}", headers=headers)
    assert resp.status_code == 204
    assert client.get(f"/api/projects/{project['id']}", headers=headers).status_code == 404


# --- Analysis persistence + history ---

def test_analyze_without_project_id_is_not_persisted(client, auth_headers):
    headers = auth_headers()
    resp = client.post(
        "/api/analyze",
        json={"code": sample_code.PYTHON_CLEAN, "language": "python"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["analysis_id"] is None

    history = client.get("/api/analysis/history", headers=headers)
    assert history.json() == []


def test_analyze_with_project_id_is_persisted_and_retrievable(client, auth_headers):
    headers = auth_headers()
    project = client.post("/api/projects", json={"name": "Saved runs"}, headers=headers).json()

    resp = client.post(
        "/api/analyze",
        json={
            "code": sample_code.PYTHON_MUTABLE_DEFAULT,
            "language": "python",
            "filename": "utils.py",
            "project_id": project["id"],
        },
        headers=headers,
    )
    assert resp.status_code == 200
    analysis_id = resp.json()["analysis_id"]
    assert analysis_id is not None

    # Appears in history
    history = client.get("/api/analysis/history", headers=headers).json()
    assert len(history) == 1
    assert history[0]["id"] == analysis_id
    assert history[0]["filename"] == "utils.py"

    # Full detail round-trips the same findings and score
    detail = client.get(f"/api/analysis/{analysis_id}", headers=headers)
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["filename"] == "utils.py"
    assert detail_body["project_id"] == project["id"]
    assert detail_body["findings"] == resp.json()["findings"]
    assert detail_body["score"] == resp.json()["score"]

    # The project's file_count now reflects the saved file
    project_after = client.get(f"/api/projects/{project['id']}", headers=headers).json()
    assert project_after["file_count"] == 1


def test_analyze_with_project_id_requires_auth(client):
    resp = client.post(
        "/api/analyze",
        json={"code": sample_code.PYTHON_CLEAN, "language": "python", "project_id": 1},
    )
    assert resp.status_code == 401


def test_analyze_rejects_project_id_owned_by_someone_else(client, auth_headers):
    headers_a = auth_headers("owner2@example.com")
    headers_b = auth_headers("intruder2@example.com")
    project = client.post("/api/projects", json={"name": "Not yours"}, headers=headers_a).json()

    resp = client.post(
        "/api/analyze",
        json={"code": sample_code.PYTHON_CLEAN, "language": "python", "project_id": project["id"]},
        headers=headers_b,
    )
    assert resp.status_code == 404


def test_cannot_view_another_users_analysis_run(client, auth_headers):
    headers_a = auth_headers("owner3@example.com")
    headers_b = auth_headers("intruder3@example.com")
    project = client.post("/api/projects", json={"name": "Secret"}, headers=headers_a).json()
    run = client.post(
        "/api/analyze",
        json={"code": sample_code.PYTHON_CLEAN, "language": "python", "project_id": project["id"]},
        headers=headers_a,
    ).json()

    resp = client.get(f"/api/analysis/{run['analysis_id']}", headers=headers_b)
    assert resp.status_code == 404


def test_history_filters_by_project(client, auth_headers):
    headers = auth_headers()
    project_1 = client.post("/api/projects", json={"name": "P1"}, headers=headers).json()
    project_2 = client.post("/api/projects", json={"name": "P2"}, headers=headers).json()

    client.post(
        "/api/analyze",
        json={"code": sample_code.PYTHON_CLEAN, "language": "python", "project_id": project_1["id"]},
        headers=headers,
    )
    client.post(
        "/api/analyze",
        json={"code": sample_code.PYTHON_CLEAN, "language": "python", "project_id": project_2["id"]},
        headers=headers,
    )

    all_history = client.get("/api/analysis/history", headers=headers).json()
    assert len(all_history) == 2

    filtered = client.get(f"/api/analysis/history?project_id={project_1['id']}", headers=headers).json()
    assert len(filtered) == 1


def test_analysis_history_requires_auth(client):
    assert client.get("/api/analysis/history").status_code == 401


def test_get_analysis_requires_auth(client):
    assert client.get("/api/analysis/1").status_code == 401
