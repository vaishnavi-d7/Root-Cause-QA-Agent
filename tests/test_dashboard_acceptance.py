"""
Task 6 Acceptance Runner:
Tests all 5 web dashboard routes at 1440px and 390px viewports with real Chromium browser.
Verifies:
1. Zero browser console errors across all routes.
2. Only allowed external network requests are Google Fonts (fonts.googleapis.com / fonts.gstatic.com).
3. Banned pattern check in web/ finds none of: prefers-color-scheme, gradient, #000, #fff as a background, 'dark'.
4. Finding B4 (F03) displays the blame-trap callout, blame chip on style commit, and truth chip on feature commit.
5. Captures full-page screenshots at 1440px and 390px widths.
"""
import json
import os
import re
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

SCREENSHOT_DIR = ROOT_DIR / "tests" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

SERVER_PORT = 8000
BASE_URL = f"http://127.0.0.1:{SERVER_PORT}"


def wait_for_server(timeout=15.0):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def test_banned_terms():
    print("\n--- 1. Testing Banned Words and Styles in web/ ---")
    terms = ['prefers-color-scheme', 'gradient', '#000', 'dark']
    found = []

    for root, dirs, files in os.walk(ROOT_DIR / "web"):
        for f in files:
            path = Path(root) / f
            text = path.read_text(encoding="utf-8", errors="replace")
            for t in terms:
                if re.search(r'\b' + re.escape(t) + r'\b', text, re.IGNORECASE) or t in text:
                    found.append((str(path.relative_to(ROOT_DIR)), t))
            if re.search(r'background(?:-color)?\s*:[^;]*#fff', text, re.IGNORECASE):
                found.append((str(path.relative_to(ROOT_DIR)), "#fff as a background"))

    if found:
        print(f"FAILED: Found banned terms: {found}")
        assert False, f"Banned terms found in web/: {found}"
    print("PASS: Clean grep of web/! No prefers-color-scheme, gradient, #000, #fff background, or 'dark'.")


def main():
    test_banned_terms()

    print("\n--- 2. Starting Server and Preparing Finished Run ---")
    server_env = os.environ.copy()
    server_env["PORT"] = str(SERVER_PORT)

    server_log = open(ROOT_DIR / "tests" / "server_web_test.log", "w", encoding="utf-8")
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
        assert wait_for_server(), "Server failed to start on port 8000"
        print(f"Server running at {BASE_URL}")

        # Ensure run 20261022-141432-498f or another completed run exists
        with urllib.request.urlopen(f"{BASE_URL}/api/runs") as r:
            runs = json.loads(r.read().decode("utf-8"))
        assert len(runs) > 0, "No runs found on server"
        run_id = next((r["id"] for r in runs if r.get("status") == "done" and "20261022" in r["id"]), runs[0]["id"])
        print(f"Testing against finished run: {run_id}")

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            routes = [
                ("runs", f"{BASE_URL}/#/"),
                ("new_run", f"{BASE_URL}/#/new"),
                ("run_detail", f"{BASE_URL}/#/run/{run_id}"),
                ("finding_b4", f"{BASE_URL}/#/run/{run_id}/finding/F03"),
                ("about", f"{BASE_URL}/#/about"),
            ]

            viewports = [
                ("1440px", {"width": 1440, "height": 900}),
                ("390px", {"width": 390, "height": 844}),
            ]

            console_errors = []
            external_requests = []

            for vp_name, vp_dims in viewports:
                print(f"\n--- Testing Viewport: {vp_name} ({vp_dims['width']}x{vp_dims['height']}) ---")
                context = browser.new_context(viewport=vp_dims)
                page = context.new_page()

                def on_console(msg):
                    if msg.type == "error":
                        console_errors.append((vp_name, msg.text))
                        print(f"  [Browser Console Error] {msg.text}")

                def on_request(req):
                    url = req.url
                    if url.startswith("http") and not url.startswith(f"http://127.0.0.1:{SERVER_PORT}") and not url.startswith("http://localhost"):
                        external_requests.append(url)
                        # Verify it is Google Fonts
                        is_google_font = "fonts.googleapis.com" in url or "fonts.gstatic.com" in url
                        if not is_google_font:
                            print(f"  [DISALLOWED External Request] {url}")

                page.on("console", on_console)
                page.on("request", on_request)

                for route_name, route_url in routes:
                    print(f"  Navigating to {route_name}: {route_url}")
                    page.goto(route_url, wait_until="networkidle")
                    page.wait_for_timeout(800)  # Allow fade transitions and DOM render

                    # Capture screenshot
                    shot_path = SCREENSHOT_DIR / f"{route_name}_{vp_name}.png"
                    page.screenshot(path=str(shot_path), full_page=True)
                    print(f"    Saved screenshot: {shot_path.name}")

                    # Route-specific validation on 1440px
                    if route_name == "finding_b4" and vp_name == "1440px":
                        print("    Validating B4 Finding Timeline and Blame Trap...")
                        callout_text = page.locator(".callout-blame-trap").inner_text()
                        print(f"    Callout text: {callout_text.strip()}")
                        assert "Blame trap: git blame points at a formatting commit" in callout_text

                        # Check chips
                        blame_wrong = page.locator(".chip-blame-wrong")
                        assert blame_wrong.count() >= 1, "Expected .chip-blame-wrong chip"
                        truth_chip = page.locator(".chip-truth")
                        assert truth_chip.count() >= 1, "Expected .chip-truth chip"

                        # Check blamed commit subject & truth commit subject
                        blamed_parent = page.locator(".timeline-node.blamed")
                        assert "style: wrap long SQL line" in blamed_parent.inner_text()
                        truth_parent = page.locator(".timeline-node.truth")
                        assert "feat: let search match substrings" in truth_parent.inner_text()
                        print("    PASS: B4 Finding verified with correct commit attribution and blame-trap callout!")

                    elif route_name == "runs" and vp_name == "1440px":
                        hero_title = page.locator("#hero-title").inner_text()
                        assert "Find the bug. Prove it. Name the commit." in hero_title
                        print("    PASS: Runs page hero verified.")

                    elif route_name == "about" and vp_name == "1440px":
                        svg_count = page.locator(".diagram-container svg").count()
                        assert svg_count >= 1, "Expected diagram SVG on about page"
                        print("    PASS: About page diagram verified.")

                context.close()

            browser.close()

        print("\n--- 3. Verifying Console Errors and External Requests ---")
        print(f"Total Console Errors: {len(console_errors)}")
        assert len(console_errors) == 0, f"Console errors detected: {console_errors}"
        print("PASS: Zero console errors!")

        non_font_external = [
            u for u in external_requests
            if not ("fonts.googleapis.com" in u or "fonts.gstatic.com" in u)
        ]
        print(f"Total External Requests: {len(external_requests)}")
        print(f"Non-Google Font External Requests: {len(non_font_external)}")
        assert len(non_font_external) == 0, f"Disallowed external requests found: {non_font_external}"
        print("PASS: Only Google Fonts requested externally!")

        print("\n>>> ALL TASK 6 ACCEPTANCE CRITERIA PASSED! <<<\n")

    finally:
        server_proc.terminate()
        server_proc.wait()
        server_log.close()


if __name__ == "__main__":
    main()
