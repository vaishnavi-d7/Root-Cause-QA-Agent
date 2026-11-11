"""Verify HTTP status codes for testapp/repo/app.py and testapp/app_clean.py."""
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def check_status(url: str, method: str = "GET", data: bytes = None) -> int:
    """Request URL and return HTTP status code even on error."""
    req = urllib.request.Request(url, method=method, data=data)
    if data is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def run_checks(port: int) -> Dict[str, int]:
    """Execute acceptance endpoint checks against running instance."""
    base = f"http://127.0.0.1:{port}"
    return {
        "/discount?code=NOPE": check_status(f"{base}/discount?code=NOPE"),
        "/profile/999": check_status(f"{base}/profile/999"),
        "/checkout (empty)": check_status(f"{base}/checkout"),
        "/search?q=%27": check_status(f"{base}/search?q=%27"),
        "POST /cart/add (qty=)": check_status(
            f"{base}/cart/add",
            method="POST",
            data=b"product_id=1&qty=",
        ),
        "/": check_status(f"{base}/"),
    }


def wait_until_ready(port: int, max_retries: int = 25) -> bool:
    """Wait for server to respond at root."""
    for _ in range(max_retries):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1):
                return True
        except Exception:
            time.sleep(0.2)
    return False


def main() -> None:
    """Start each app, run acceptance checks, and print status table."""
    root_dir = Path(__file__).resolve().parent.parent
    repo_dir = root_dir / "testapp" / "repo"
    clean_app_path = root_dir / "testapp" / "app_clean.py"

    # 1. Test testapp/repo/app.py (Buggy repo)
    print("\n--- Testing testapp/repo/app.py (port 5055) ---")
    env_repo = os.environ.copy()
    env_repo["PORT"] = "5055"
    proc_repo = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=str(repo_dir),
        env=env_repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert wait_until_ready(5055), "repo/app.py failed to start on port 5055"
        repo_results = run_checks(5055)
        for ep, status in repo_results.items():
            print(f"  {ep:<26} -> {status}")
    finally:
        proc_repo.terminate()
        proc_repo.wait()

    # 2. Test testapp/app_clean.py (Clean reference)
    print("\n--- Testing testapp/app_clean.py (port 5056) ---")
    env_clean = os.environ.copy()
    env_clean["PORT"] = "5056"
    proc_clean = subprocess.Popen(
        [sys.executable, str(clean_app_path)],
        cwd=str(root_dir),
        env=env_clean,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert wait_until_ready(5056), "app_clean.py failed to start on port 5056"
        clean_results = run_checks(5056)
        for ep, status in clean_results.items():
            print(f"  {ep:<26} -> {status}")
    finally:
        proc_clean.terminate()
        proc_clean.wait()

    # Verify expectations
    expected_repo = {
        "/discount?code=NOPE": 500,
        "/profile/999": 500,
        "/checkout (empty)": 500,
        "/search?q=%27": 500,
        "POST /cart/add (qty=)": 500,
        "/": 200,
    }
    expected_clean = {
        "/discount?code=NOPE": 404,
        "/profile/999": 404,
        "/checkout (empty)": 200,
        "/search?q=%27": 200,
        "POST /cart/add (qty=)": 400,
        "/": 200,
    }
    assert repo_results == expected_repo, f"Mismatch in repo results: {repo_results} != {expected_repo}"
    assert clean_results == expected_clean, f"Mismatch in clean results: {clean_results} != {expected_clean}"
    print("\nALL ACCEPTANCE STATUS CODE CHECKS PASSED!\n")


if __name__ == "__main__":
    main()
