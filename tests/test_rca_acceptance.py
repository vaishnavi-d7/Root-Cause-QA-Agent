"""Acceptance test runner for Task 3 RCA Agent."""
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

from qa_agent.explorer import Explorer
from rca_agent.analyzer import analyze
from rca_agent.log_parser import parse_server_log

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
    """Run explorer with server log redirection, perform baseline RCA, and verify against ground truth."""
    repo_dir = ROOT_DIR / "testapp" / "repo"
    out_dir = ROOT_DIR / "artifacts_test"
    gt_file = ROOT_DIR / "testapp" / "ground_truth.json"
    server_log_file = out_dir / "server.log"

    out_dir.mkdir(parents=True, exist_ok=True)

    app_url = "http://127.0.0.1:5055"
    server_proc = None

    try:
        print("Starting testapp/repo/app.py with server log redirection...")
        log_handle = open(server_log_file, "w", encoding="utf-8", errors="replace")
        env = os.environ.copy()
        env["PORT"] = "5055"
        server_proc = subprocess.Popen(
            [sys.executable, "app.py"],
            cwd=repo_dir,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        assert wait_until_ready(f"{app_url}/"), "Seeded app failed to start"

        print("Running Explorer to find defects...")
        explorer = Explorer(app_url, out_dir=out_dir, use_llm=False)
        findings = explorer.run()

        # Allow logs to flush
        time.sleep(0.5)

    finally:
        if server_proc:
            server_proc.terminate()
            server_proc.wait()
        log_handle.close()

    print("\nParsing server logs...")
    log_text = server_log_file.read_text(encoding="utf-8", errors="replace")
    traces = parse_server_log(log_text)
    print(f"Captured {len(traces)} server traces from log.")

    ground_truth = json.loads(gt_file.read_text(encoding="utf-8"))
    gt_by_route = {item["route"]: item for item in ground_truth}

    print("\n" + "=" * 94)
    print(
        f"{'Bug ID':<7} | {'Route':<14} | {'Finding':<8} | {'Blamed SHA':<10} | {'True Culprit':<12} | Baseline Assessment"
    )
    print("-" * 94)

    for finding in findings:
        res = analyze(finding, repo_dir, traces, mode="baseline")
        gt_item = gt_by_route.get(finding.route)
        assert gt_item is not None, f"No ground truth for route {finding.route}"

        bug_id = gt_item["bug_id"]
        true_culprit = gt_item["culprit_commit"]
        masked_by = gt_item.get("masked_by_commit")
        blamed_sha = res.suspected_commit or ""

        if bug_id == "B4":
            # For B4, baseline git blame points to the blame-trap commit
            assert blamed_sha == masked_by, f"B4 expected masked commit {masked_by}, got {blamed_sha}"
            status_desc = "BLAME-TRAP (Masked by style commit)"
        else:
            # For B1, B2, B3, B5, baseline git blame points directly to the true culprit commit
            assert blamed_sha == true_culprit, f"{bug_id} expected culprit {true_culprit}, got {blamed_sha}"
            status_desc = "TRUE CULPRIT IDENTIFIED"

        print(
            f"{bug_id:<7} | {finding.route:<14} | {finding.id:<8} | {blamed_sha[:7]:<10} | "
            f"{true_culprit[:7]:<12} | {status_desc}"
        )

    print("=" * 94)
    print("\n>>> ALL TASK 3 BASELINE ACCEPTANCE CHECKS PASSED! <<<\n")


if __name__ == "__main__":
    main()
