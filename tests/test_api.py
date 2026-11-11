"""Unit tests for FastAPI endpoints: health, config, concurrency lock, traversal guards, and secrets."""
import json
import sys
from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from qa_agent.explorer import safe_rmtree
from server.main import app
import server.runs as runs_module


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Provide FastAPI TestClient."""
    with TestClient(app) as test_client:
        yield test_client


def test_api_health(client: TestClient) -> None:
    """Verify GET /api/health returns 200 and ok: True."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_api_config(client: TestClient) -> None:
    """Verify GET /api/config returns provider presets and default RCA mode."""
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    assert "llm_available" in data
    assert "default_rca_mode" in data

    provider_names = [p["name"] for p in data["providers"]]
    assert "anthropic" in provider_names
    assert "gemini" in provider_names
    assert "groq" in provider_names
    assert "ollama" in provider_names


def test_api_concurrency_409_on_second_run(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify POST /api/runs returns HTTP 409 Conflict when another run is already active."""
    # Simulate an active run lock
    monkeypatch.setattr(runs_module, "_active_run_id", "20261022-active-run")

    payload = {"rca": "baseline", "provider": None, "reseed": False}
    resp = client.post("/api/runs", json=payload)
    assert resp.status_code == 409
    assert "already in progress" in resp.json()["detail"].lower()


def test_media_path_traversal_returns_404(client: TestClient) -> None:
    """Verify media endpoint strictly rejects directory traversal attacks with 404."""
    test_run_id = "test-traversal-guard-run"
    run_dir = runs_module.RUNS_DIR / test_run_id
    videos_dir = run_dir / "videos"
    screenshots_dir = run_dir / "screenshots"

    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        videos_dir.mkdir(parents=True, exist_ok=True)
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        # Place legitimate media and a sensitive meta file
        meta_file = run_dir / "meta.json"
        meta_file.write_text('{"secret_config": "do-not-leak"}', encoding="utf-8")

        test_video = videos_dir / "step1.webm"
        test_video.write_bytes(b"dummy video data")

        test_shot = screenshots_dir / "step1.png"
        test_shot.write_bytes(b"dummy image data")

        # 1. Valid media requests should succeed
        resp_v = client.get(f"/api/runs/{test_run_id}/media/videos/step1.webm")
        assert resp_v.status_code == 200

        resp_s = client.get(f"/api/runs/{test_run_id}/media/screenshots/step1.png")
        assert resp_s.status_code == 200

        # 2. Path traversal attempts to access meta.json outside media dirs must return 404
        resp_t1 = client.get(f"/api/runs/{test_run_id}/media/../meta.json")
        assert resp_t1.status_code == 404

        resp_t2 = client.get(f"/api/runs/{test_run_id}/media/videos/../../meta.json")
        assert resp_t2.status_code == 404

        resp_t3 = client.get(f"/api/runs/{test_run_id}/media/../../server/main.py")
        assert resp_t3.status_code == 404
    finally:
        if run_dir.exists():
            safe_rmtree(run_dir)


def test_posted_api_key_never_stored_in_meta_or_response(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that user-supplied api_key is never persisted in meta.json or returned in any API response."""
    created_runs: list[str] = []

    def mock_worker(run_id: str, *args: Any, **kwargs: Any) -> None:
        runs_module._active_run_id = None

    monkeypatch.setattr(runs_module, "_background_worker", mock_worker)
    monkeypatch.setattr(runs_module, "_active_run_id", None)

    secret_key = "sk-super-secret-production-token-xyz-12345"
    payload = {
        "rca": "baseline",
        "provider": None,
        "reseed": False,
        "api_key": secret_key,
    }

    resp = client.post("/api/runs", json=payload)
    assert resp.status_code == 202
    resp_data = resp.json()
    assert "run_id" in resp_data
    run_id = resp_data["run_id"]
    created_runs.append(run_id)

    # 1. Response body must not contain the secret key
    assert secret_key not in resp.text

    # 2. meta.json on disk must not contain the secret key
    run_dir = runs_module.RUNS_DIR / run_id
    meta_path = run_dir / "meta.json"
    assert meta_path.exists()
    meta_content = meta_path.read_text(encoding="utf-8")
    assert secret_key not in meta_content

    # 3. GET /api/runs/{run_id} response must not contain the secret key
    get_resp = client.get(f"/api/runs/{run_id}")
    assert get_resp.status_code == 200
    assert secret_key not in get_resp.text

    # Cleanup
    for r_id in created_runs:
        r_path = runs_module.RUNS_DIR / r_id
        if r_path.exists():
            safe_rmtree(r_path)

