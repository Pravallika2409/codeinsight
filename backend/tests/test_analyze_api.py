from tests import sample_code


def test_health_check(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "cpp" in body["analyzers"]
    assert "python" in body["analyzers"]
    assert "javascript" in body["analyzers"]
    assert "java" in body["analyzers"]


def test_analyze_cpp_array_out_of_bounds(client):
    resp = client.post("/api/analyze", json={
        "code": sample_code.CPP_ARRAY_OOB,
        "language": "cpp",
        "filename": "test.cpp",
    })
    assert resp.status_code == 200
    body = resp.json()
    rule_ids = {f["rule_id"] for f in body["findings"]}
    assert "arrayIndexOutOfBounds" in rule_ids
    assert body["critical_count"] >= 1
    assert body["score"]["total"] < 100


def test_analyze_cpp_null_dereference(client):
    resp = client.post("/api/analyze", json={
        "code": sample_code.CPP_NULL_DEREF,
        "language": "cpp",
    })
    body = resp.json()
    rule_ids = {f["rule_id"] for f in body["findings"]}
    assert "nullPointer" in rule_ids


def test_analyze_cpp_clean_code_has_no_critical_findings(client):
    resp = client.post("/api/analyze", json={
        "code": sample_code.CPP_CLEAN,
        "language": "cpp",
    })
    body = resp.json()
    assert body["critical_count"] == 0
    assert body["score"]["total"] >= 80


def test_analyze_python_mutable_default_argument(client):
    resp = client.post("/api/analyze", json={
        "code": sample_code.PYTHON_MUTABLE_DEFAULT,
        "language": "python",
    })
    body = resp.json()
    rule_ids = {f["rule_id"] for f in body["findings"]}
    assert "mutable-default-argument" in rule_ids


def test_analyze_python_eval_and_bare_except(client):
    resp = client.post("/api/analyze", json={
        "code": sample_code.PYTHON_BARE_EXCEPT_AND_EVAL,
        "language": "python",
    })
    body = resp.json()
    rule_ids = {f["rule_id"] for f in body["findings"]}
    assert "dangerous-eval" in rule_ids
    assert "bare-except" in rule_ids
    security_findings = [f for f in body["findings"] if f["category"] == "security"]
    assert len(security_findings) >= 1


def test_analyze_python_undefined_name(client):
    resp = client.post("/api/analyze", json={
        "code": sample_code.PYTHON_UNDEFINED_NAME,
        "language": "python",
    })
    body = resp.json()
    messages = " ".join(f["message"] for f in body["findings"])
    assert "undefined_variable" in messages


def test_analyze_python_syntax_error_reported_as_critical(client):
    resp = client.post("/api/analyze", json={
        "code": sample_code.PYTHON_SYNTAX_ERROR,
        "language": "python",
    })
    body = resp.json()
    assert body["critical_count"] >= 1


def test_analyze_python_nested_loops_complexity(client):
    resp = client.post("/api/analyze", json={
        "code": sample_code.PYTHON_NESTED_LOOPS,
        "language": "python",
    })
    body = resp.json()
    assert body["complexity"]["time_complexity"] == "O(n\u00b2)"
    assert body["complexity"]["is_estimated"] is True


def test_analyze_clean_python_scores_highly(client):
    resp = client.post("/api/analyze", json={
        "code": sample_code.PYTHON_CLEAN,
        "language": "python",
    })
    body = resp.json()
    assert body["score"]["total"] >= 90


def test_analyze_rejects_empty_code(client):
    resp = client.post("/api/analyze", json={"code": "   ", "language": "python"})
    assert resp.status_code == 422


def test_analyze_rejects_invalid_language(client):
    resp = client.post("/api/analyze", json={"code": "print(1)", "language": "rust"})
    assert resp.status_code == 422


def test_analyze_javascript_eval_and_loose_equality(client):
    resp = client.post("/api/analyze", json={
        "code": sample_code.JS_EVAL_AND_LOOSE_EQUALITY,
        "language": "javascript",
    })
    assert resp.status_code == 200
    body = resp.json()
    rule_ids = {f["rule_id"] for f in body["findings"]}
    assert "no-eval" in rule_ids
    assert "eqeqeq" in rule_ids
    security_findings = [f for f in body["findings"] if f["category"] == "security"]
    assert len(security_findings) >= 1


def test_analyze_javascript_unused_var_and_async_promise_executor(client):
    resp = client.post("/api/analyze", json={
        "code": sample_code.JS_UNUSED_VAR_AND_ASYNC_PROMISE_EXECUTOR,
        "language": "javascript",
    })
    body = resp.json()
    rule_ids = {f["rule_id"] for f in body["findings"]}
    assert "no-unused-vars" in rule_ids
    assert "no-async-promise-executor" in rule_ids


def test_analyze_javascript_clean_code_scores_highly(client):
    resp = client.post("/api/analyze", json={
        "code": sample_code.JS_CLEAN,
        "language": "javascript",
    })
    body = resp.json()
    assert body["critical_count"] == 0
    assert body["score"]["total"] >= 90


def test_analyze_javascript_syntax_error_reported_as_critical(client):
    resp = client.post("/api/analyze", json={
        "code": sample_code.JS_SYNTAX_ERROR,
        "language": "javascript",
    })
    body = resp.json()
    assert body["critical_count"] >= 1


def test_analyze_java_empty_catch_and_resource_leak(client):
    resp = client.post("/api/analyze", json={
        "code": sample_code.JAVA_EMPTY_CATCH_AND_RESOURCE_LEAK,
        "language": "java",
    })
    assert resp.status_code == 200
    body = resp.json()
    rule_ids = {f["rule_id"] for f in body["findings"]}
    assert "empty-catch-block" in rule_ids
    assert "resource-not-closed" in rule_ids


def test_analyze_java_hardcoded_credential(client):
    resp = client.post("/api/analyze", json={
        "code": sample_code.JAVA_HARDCODED_CREDENTIAL,
        "language": "java",
    })
    body = resp.json()
    rule_ids = {f["rule_id"] for f in body["findings"]}
    assert "hardcoded-credential" in rule_ids
    assert body["critical_count"] >= 1


def test_analyze_java_clean_code_scores_highly(client):
    resp = client.post("/api/analyze", json={
        "code": sample_code.JAVA_CLEAN,
        "language": "java",
    })
    body = resp.json()
    assert body["critical_count"] == 0
    assert body["score"]["total"] >= 90


def test_analyze_java_compile_error_reported(client):
    resp = client.post("/api/analyze", json={
        "code": sample_code.JAVA_COMPILE_ERROR,
        "language": "java",
    })
    body = resp.json()
    compiler_findings = [f for f in body["findings"] if f["source"] == "compiler"]
    assert len(compiler_findings) >= 1
    assert any(f["severity"] == "high" for f in compiler_findings)


def test_analyze_rejects_oversized_payload(client, monkeypatch):
    from app.api import analyze as analyze_module
    monkeypatch.setattr(analyze_module.settings, "MAX_CODE_SIZE_BYTES", 10)
    resp = client.post("/api/analyze", json={"code": "print('hello world')", "language": "python"})
    assert resp.status_code == 413


def test_response_never_leaks_stack_trace_on_internal_error(client, monkeypatch):
    from app.services import analysis_service

    def boom(request):
        raise RuntimeError("simulated analyzer crash")

    monkeypatch.setattr(analysis_service, "run_analysis", boom)
    from app.api import analyze as analyze_module
    monkeypatch.setattr(analyze_module, "run_analysis", boom)

    resp = client.post("/api/analyze", json={"code": "print(1)", "language": "python"})
    assert resp.status_code == 500
    assert "Traceback" not in resp.text
    assert resp.json()["detail"] == "Analysis failed unexpectedly. Please try again."
