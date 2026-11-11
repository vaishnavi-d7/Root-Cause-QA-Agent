"""
Capture script for design review:
Takes screenshots of all required pages and states at 1440, 1024, 768, and 390 px widths.
Usage: python tests/capture_screenshots.py [before|after]
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PORT = 8000
BASE_URL = f"http://127.0.0.1:{PORT}"

VIEWPORTS = [
    ("1440px", {"width": 1440, "height": 900}),
    ("1024px", {"width": 1024, "height": 768}),
    ("768px", {"width": 768, "height": 1024}),
    ("390px", {"width": 390, "height": 844}),
]


def wait_for_server(timeout=15.0):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def capture_all(target_folder="before"):
    out_dir = ROOT_DIR / "docs" / "screenshots" / target_folder
    out_dir.mkdir(parents=True, exist_ok=True)

    server_log = open(ROOT_DIR / "tests" / "server_capture.log", "w", encoding="utf-8")
    server_env = os.environ.copy()
    server_env["PORT"] = str(PORT)

    server_proc = subprocess.Popen(
        [sys.executable, "run_server.py"],
        cwd=str(ROOT_DIR),
        env=server_env,
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    try:
        assert wait_for_server(), "Server failed to start"
        print(f"Server is up at {BASE_URL}. Capturing {target_folder} screenshots...")

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for vp_name, vp_dims in VIEWPORTS:
                print(f"\n--- Viewport {vp_name} ---")
                context = browser.new_context(viewport=vp_dims)
                page = context.new_page()

                # 1. runs_populated
                page.goto(f"{BASE_URL}/#/", wait_until="networkidle")
                page.wait_for_timeout(600)
                page.screenshot(path=str(out_dir / f"runs_populated_{vp_name}.png"), full_page=True)

                # 2. runs_empty (intercept /api/runs)
                def mock_empty_runs(route):
                    route.fulfill(status=200, content_type="application/json", body="[]")
                page.route("**/api/runs", mock_empty_runs)
                page.goto(f"{BASE_URL}/#/", wait_until="networkidle")
                page.wait_for_timeout(600)
                page.screenshot(path=str(out_dir / f"runs_empty_{vp_name}.png"), full_page=True)
                page.unroute("**/api/runs")

                # 3. new_run_llm_available
                page.goto(f"{BASE_URL}/#/new", wait_until="networkidle")
                page.wait_for_timeout(600)
                page.screenshot(path=str(out_dir / f"new_run_llm_available_{vp_name}.png"), full_page=True)

                # 4. new_run_llm_unavailable (intercept /api/config)
                def mock_no_llm(route):
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({
                            "providers": [
                                {"name": "gemini", "key_env": "GEMINI_API_KEY", "default_model": "gemini-2.5-flash", "configured": False, "needs_key": True},
                                {"name": "groq", "key_env": "GROQ_API_KEY", "default_model": "llama-3.3-70b-versatile", "configured": False, "needs_key": True}
                            ],
                            "llm_available": False,
                            "default_rca_mode": "baseline"
                        })
                    )
                page.route("**/api/config", mock_no_llm)
                page.goto(f"{BASE_URL}/#/new", wait_until="networkidle")
                page.wait_for_timeout(600)
                page.screenshot(path=str(out_dir / f"new_run_llm_unavailable_{vp_name}.png"), full_page=True)
                page.unroute("**/api/config")

                # 5. run_done (20261022-141432-498f)
                page.goto(f"{BASE_URL}/#/run/20261022-141432-498f", wait_until="networkidle")
                page.wait_for_timeout(600)
                page.screenshot(path=str(out_dir / f"run_done_{vp_name}.png"), full_page=True)

                # 6. run_running (mock-running-run)
                page.goto(f"{BASE_URL}/#/run/mock-running-run", wait_until="networkidle")
                page.wait_for_timeout(600)
                page.screenshot(path=str(out_dir / f"run_running_{vp_name}.png"), full_page=True)

                # 7. run_invalid_llm (mock-invalid-llm-run)
                page.goto(f"{BASE_URL}/#/run/mock-invalid-llm-run", wait_until="networkidle")
                page.wait_for_timeout(600)
                page.screenshot(path=str(out_dir / f"run_invalid_llm_{vp_name}.png"), full_page=True)

                # 8. finding_b4 (F03 on /search)
                page.goto(f"{BASE_URL}/#/run/20261022-141432-498f/finding/F03", wait_until="networkidle")
                page.wait_for_timeout(600)
                page.screenshot(path=str(out_dir / f"finding_b4_{vp_name}.png"), full_page=True)

                # 9. finding_normal (F01 on /checkout)
                page.goto(f"{BASE_URL}/#/run/20261022-141432-498f/finding/F01", wait_until="networkidle")
                page.wait_for_timeout(600)
                page.screenshot(path=str(out_dir / f"finding_normal_{vp_name}.png"), full_page=True)

                # 10. benchmark_tab
                page.goto(f"{BASE_URL}/#/run/20261022-141432-498f", wait_until="networkidle")
                page.wait_for_timeout(400)
                page.locator('[data-tab="benchmark"]').click()
                page.wait_for_timeout(400)
                page.screenshot(path=str(out_dir / f"benchmark_tab_{vp_name}.png"), full_page=True)

                # 11. report_tab
                page.locator('[data-tab="report"]').click()
                page.wait_for_timeout(400)
                page.screenshot(path=str(out_dir / f"report_tab_{vp_name}.png"), full_page=True)

                # 12. about
                page.goto(f"{BASE_URL}/#/about", wait_until="networkidle")
                page.wait_for_timeout(600)
                page.screenshot(path=str(out_dir / f"about_{vp_name}.png"), full_page=True)

                # 13. error_state
                page.goto(f"{BASE_URL}/#/run/nonexistent-run-id", wait_until="networkidle")
                page.wait_for_timeout(600)
                page.screenshot(path=str(out_dir / f"error_state_{vp_name}.png"), full_page=True)

                context.close()
                print(f"Captured all 13 states for {vp_name}")

            browser.close()

        print(f"\nCompleted capture for {target_folder}!")

    finally:
        server_proc.terminate()
        server_proc.wait()
        server_log.close()


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "before"
    capture_all(folder)
