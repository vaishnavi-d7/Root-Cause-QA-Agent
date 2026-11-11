"""Acceptance test runner for Task 2 Playwright QA Explorer."""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from qa_agent.explorer import Explorer, safe_rmtree

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def wait_until_ready(url: str, max_retries: int = 30) -> bool:
    """Poll URL until ready or retries expire."""
    for _ in range(max_retries):
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except Exception:
            time.sleep(0.2)
    return False


def main() -> None:
    """Run Explorer against seeded app and assert acceptance criteria."""
    root_dir = Path(__file__).resolve().parent.parent
    repo_dir = root_dir / "testapp" / "repo"
    out_dir = root_dir / "artifacts_test"

    if out_dir.exists():
        safe_rmtree(out_dir)

    server_proc = None
    app_url = "http://127.0.0.1:5055"

    try:
        # Check if already running or start seeded app on port 5055
        is_running = False
        try:
            with urllib.request.urlopen(f"{app_url}/", timeout=1):
                is_running = True
        except Exception:
            is_running = False

        if not is_running:
            print("Starting testapp/repo/app.py on port 5055...")
            env = os.environ.copy()
            env["PORT"] = "5055"
            server_proc = subprocess.Popen(
                [sys.executable, "app.py"],
                cwd=repo_dir,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            assert wait_until_ready(f"{app_url}/"), "Seeded app failed to start on port 5055"

        print("Executing Explorer...")
        explorer = Explorer(app_url, out_dir=out_dir, use_llm=False)
        findings = explorer.run()

        print("\n--- Verifying Acceptance Criteria ---")
        print(f"1. Total probes: {explorer.probe_count} (expected ~51)")
        assert 45 <= explorer.probe_count <= 55, f"Probe count {explorer.probe_count} out of range"

        print(f"2. Total distinct findings: {len(findings)} (expected 5)")
        assert len(findings) == 5, f"Expected 5 findings, got {len(findings)}"

        expected_routes = {"/checkout", "/profile/<n>", "/search", "/discount", "/cart/add"}
        found_routes = {f.route for f in findings}
        print(f"3. Discovered routes: {found_routes}")
        assert found_routes == expected_routes, f"Mismatch in routes: {found_routes} != {expected_routes}"

        for f in findings:
            print(f"   - Finding {f.id}: route={f.route:<14} kind={f.kind:<10} reproduced={f.reproduced}")
            assert f.kind == "http_500", f"Finding {f.id} kind is {f.kind}, expected http_500"
            assert f.reproduced is True, f"Finding {f.id} was not reproduced"
            assert f.video, f"Finding {f.id} missing video"
            video_file = out_dir / f.video
            assert video_file.exists(), f"Video file {video_file} does not exist"
            assert video_file.stat().st_size > 0, f"Video file {video_file} is empty"

        print("4. Verifying findings.json...")
        findings_json_file = out_dir / "findings.json"
        assert findings_json_file.exists(), "findings.json does not exist"
        data = json.loads(findings_json_file.read_text(encoding="utf-8"))
        assert len(data) == 5, f"findings.json contains {len(data)} items, expected 5"

        for item in data:
            if item.get("video"):
                assert not os.path.isabs(item["video"]), f"Video path {item['video']} is not relative"
            if item.get("screenshot"):
                assert not os.path.isabs(item["screenshot"]), f"Screenshot path {item['screenshot']} is not relative"

        print("\n>>> ALL TASK 2 ACCEPTANCE CRITERIA PASSED! <<<\n")

    finally:
        if server_proc:
            server_proc.terminate()
            server_proc.wait()


def test_explorer_acceptance() -> None:
    """Pytest test case for Explorer acceptance."""
    main()


if __name__ == "__main__":
    main()
