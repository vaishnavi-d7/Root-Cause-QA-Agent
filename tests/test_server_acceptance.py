"""Acceptance test runner for Task 5 FastAPI backend and launcher."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SERVER_PORT = 8000
BASE_URL = f"http://127.0.0.1:{SERVER_PORT}"


def wait_for_backend(timeout: float = 15.0) -> bool:
    """Poll /api/health until backend is up."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def request_json(path: str, method: str = "GET", data: dict = None, expected_status: int = 200) -> tuple:
    """Send HTTP request and return (status, parsed_json_or_text)."""
    url = f"{BASE_URL}{path}"
    req_data = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body)
            except Exception:
                return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except Exception:
            return exc.code, body


def main() -> None:
    """Run Task 5 acceptance suite."""
    print("--- Starting Server on Port 8000 ---")
    server_env = os.environ.copy()
    server_env["PORT"] = str(SERVER_PORT)

    server_log_path = ROOT_DIR / "tests" / "server_test.log"
    server_log_file = open(server_log_path, "w", encoding="utf-8")

    server_proc = subprocess.Popen(
        [sys.executable, "run_server.py"],
        cwd=str(ROOT_DIR),
        env=server_env,
        stdout=server_log_file,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    try:
        assert wait_for_backend(), "Server failed to start on port 8000"
        print("Server is responsive at http://127.0.0.1:8000\n")

        # Acceptance 1: Health & Static index
        print("=== Check 1: GET /api/health and GET / ===")
        code, health_resp = request_json("/api/health")
        print(f"GET /api/health -> Status: {code}, Response: {health_resp}")
        assert code == 200 and health_resp.get("ok") is True

        req = urllib.request.Request(f"{BASE_URL}/")
        with urllib.request.urlopen(req) as resp:
            index_content = resp.read().decode("utf-8")
        print(f"GET / -> Status: {resp.status}, Content contains 'RootCause-QA': {'RootCause-QA' in index_content}")
        assert "RootCause-QA" in index_content

        # Acceptance 2: POST /api/runs (202) and concurrent POST (409)
        print("\n=== Check 2: POST /api/runs (202) and concurrent run (409) ===")
        post_data = {"rca": "baseline", "reseed": False, "llm_payloads": False}
        code, run_resp = request_json("/api/runs", method="POST", data=post_data)
        print(f"First POST /api/runs -> Status: {code}, Response: {run_resp}")
        assert code == 202
        run_id = run_resp["run_id"]

        # Immediate second POST while it runs -> 409
        code_second, second_resp = request_json("/api/runs", method="POST", data=post_data)
        print(f"Second POST /api/runs (concurrent) -> Status: {code_second}, Detail: {second_resp}")
        assert code_second == 409

        # Acceptance 3: Stream SSE events until 'end'
        print("\n=== Check 3: SSE stream from /api/runs/{id}/events ===")
        events_url = f"{BASE_URL}/api/runs/{run_id}/events"
        sse_req = urllib.request.Request(events_url, headers={"Accept": "text/event-stream"})
        end_received = False
        event_types = []

        with urllib.request.urlopen(sse_req, timeout=120.0) as sse_stream:
            buffer = ""
            while True:
                line = sse_stream.readline().decode("utf-8", errors="replace")
                if not line:
                    break
                line = line.strip()
                if line.startswith("data: "):
                    payload = json.loads(line[6:])
                    evt_type = payload.get("type")
                    event_types.append(evt_type)
                    if evt_type == "stage":
                        print(f"  [SSE Stage] {payload.get('stage')} -> {payload.get('status')}")
                    elif evt_type == "end":
                        print(f"  [SSE End] Final status: {payload.get('status')}")
                        end_received = True
                        break

        assert end_received, "SSE stream did not yield an 'end' event"
        print(f"SSE successfully captured stages and ended: {set(event_types)}")

        # Acceptance 4: GET /api/runs/{id}
        print("\n=== Check 4: GET /api/runs/{id} details and benchmark summary ===")
        code, details = request_json(f"/api/runs/{run_id}")
        assert code == 200
        findings = details.get("findings", [])
        bench = details.get("benchmark", {})
        baseline_correct = bench.get("modes", {}).get("baseline", {}).get("correct")
        print(f"Findings Count: {len(findings)}")
        print(f"Detected: {bench.get('detected')}/5, Reproduced: {bench.get('reproduced')}/5, Baseline: {baseline_correct}/5")
        assert len(findings) == 5
        assert bench.get("detected") == 5
        assert bench.get("reproduced") == 5
        assert baseline_correct == 4

        # Acceptance 5: Media endpoint & path traversal guard
        print("\n=== Check 5: Media serving (video/webm) and path traversal defense (404) ===")
        first_video = findings[0].get("video")
        video_url = f"{BASE_URL}/api/runs/{run_id}/media/{first_video}"
        with urllib.request.urlopen(video_url) as v_resp:
            print(f"GET /media/{first_video} -> Status: {v_resp.status}, Content-Type: {v_resp.headers.get('Content-Type')}")
            assert v_resp.status == 200
            assert "video/webm" in v_resp.headers.get("Content-Type")

        traversal_url = f"{BASE_URL}/api/runs/{run_id}/media/../meta.json"
        try:
            with urllib.request.urlopen(traversal_url) as t_resp:
                traversal_code = t_resp.status
        except urllib.error.HTTPError as exc:
            traversal_code = exc.code
        print(f"GET /media/../meta.json (traversal) -> Status: {traversal_code} (expected 404)")
        assert traversal_code == 404

        # Acceptance 6: Secret leakage test
        print("\n=== Check 6: Secret leakage check (POST fake api_key) ===")
        fake_secret = "SUPER_SECRET_TOKEN_XYZ_999"
        code, secret_run_resp = request_json(
            "/api/runs",
            method="POST",
            data={"rca": "baseline", "reseed": False, "api_key": fake_secret},
        )
        assert code == 202
        secret_run_id = secret_run_resp["run_id"]
        # Wait for this run to finish
        while True:
            c, det = request_json(f"/api/runs/{secret_run_id}")
            if det.get("meta", {}).get("status") in ("done", "failed"):
                break
            time.sleep(1.0)

        # Grep runs/ folder for secret
        leak_found = False
        runs_dir = ROOT_DIR / "runs"
        for root, dirs, files in os.walk(runs_dir):
            for fname in files:
                fpath = Path(root) / fname
                try:
                    text = fpath.read_text(encoding="utf-8", errors="replace")
                    if fake_secret in text:
                        print(f"LEAK FOUND in {fpath}!")
                        leak_found = True
                except Exception:
                    pass

        print(f"Secret leakage in runs/ directory: {'FOUND (FAILED)' if leak_found else 'CLEAN (NONE)'}")
        assert not leak_found, "Secret key was leaked to disk!"

        # Acceptance 7: DELETE run folder on Windows
        print("\n=== Check 7: DELETE /api/runs/{id} on Windows ===")
        code, del_resp = request_json(f"/api/runs/{run_id}", method="DELETE")
        print(f"DELETE /api/runs/{run_id} -> Status: {code}, Response: {del_resp}")
        assert code == 200
        run_folder = runs_dir / run_id
        assert not run_folder.exists(), "Run folder was not deleted"
        print("Run folder successfully deleted without PermissionError!")

        print("\n>>> ALL TASK 5 ACCEPTANCE CRITERIA PASSED! <<<\n")

    finally:
        server_proc.terminate()
        server_proc.wait()
        server_log_file.close()


if __name__ == "__main__":
    main()
