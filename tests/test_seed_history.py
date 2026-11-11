"""Unit tests for testapp seed_history generation and ground truth alignment."""
import json
import subprocess
from pathlib import Path

from benchmark.score import score
from qa_agent.models import Finding
from testapp.seed_history import seed_history

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_seed_history_and_ground_truth_alignment() -> None:
    """Verify seed_history creates 10 commits, 5 ground-truth entries, and B4 blame-trap matches."""
    # Run seed_history to generate repo and ground truth
    ground_truth = seed_history()
    repo_dir = ROOT_DIR / "testapp" / "repo"
    gt_file = ROOT_DIR / "testapp" / "ground_truth.json"

    assert repo_dir.exists(), "testapp/repo directory must exist"
    assert gt_file.exists(), "testapp/ground_truth.json must exist"

    # Verify exactly 10 commits were created
    res = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    commit_count = int(res.stdout.strip())
    assert commit_count == 10, f"Expected 10 commits in testapp/repo, found {commit_count}"

    # Read ground truth from disk
    gt_data = json.loads(gt_file.read_text(encoding="utf-8"))
    assert len(gt_data) == 5, f"Expected 5 ground truth bugs, found {len(gt_data)}"

    # Check bug IDs B1 through B5 exist
    bug_ids = [b["bug_id"] for b in gt_data]
    assert bug_ids == ["B1", "B2", "B3", "B4", "B5"]

    # Verify B4 has masked_by_commit (the blame trap)
    b4 = next(b for b in gt_data if b["bug_id"] == "B4")
    assert b4["culprit_commit"] is not None
    assert b4["masked_by_commit"] is not None
    assert b4["culprit_commit"] != b4["masked_by_commit"]

    # Verify that the B4 note in the benchmark score output names the same commits recorded in ground_truth.json
    mock_findings = [
        Finding(
            id="F03",
            kind="http_500",
            method="GET",
            url="http://127.0.0.1:5055/search?q=%27",
            route="/search",
            status=500,
            summary="HTTP 500 on /search",
            steps=[],
            console=[],
            reproduced=True,
        )
    ]
    summary, markdown_report = score(mock_findings, {}, gt_data)

    expected_culprit_short = b4["culprit_commit"][:7]
    expected_masked_short = b4["masked_by_commit"][:7]

    assert expected_culprit_short in markdown_report, (
        f"Benchmark report did not mention B4 culprit short SHA {expected_culprit_short}:\n{markdown_report}"
    )
    assert expected_masked_short in markdown_report, (
        f"Benchmark report did not mention B4 masked short SHA {expected_masked_short}:\n{markdown_report}"
    )

    # Verify that the two commit subjects in the note are different and match git log
    res_c = subprocess.run(
        ["git", "log", "-1", "--format=%s", b4["culprit_commit"]],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    culprit_subject = res_c.stdout.strip()

    res_m = subprocess.run(
        ["git", "log", "-1", "--format=%s", b4["masked_by_commit"]],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    masked_subject = res_m.stdout.strip()

    assert culprit_subject != masked_subject, (
        f"Expected distinct culprit and masking subjects, but both were: {culprit_subject}"
    )
    assert culprit_subject in markdown_report, (
        f"Culprit subject '{culprit_subject}' missing from benchmark note:\n{markdown_report}"
    )
    assert masked_subject in markdown_report, (
        f"Masked subject '{masked_subject}' missing from benchmark note:\n{markdown_report}"
    )

    expected_note = (
        f"B4 was introduced in {expected_culprit_short} (\"{culprit_subject}\") "
        f"but masked by cosmetic commit {expected_masked_short} (\"{masked_subject}\"). "
        "Plain git blame points at the cosmetic commit."
    )
    assert expected_note in markdown_report, (
        f"Expected note not found in benchmark report.\nExpected:\n{expected_note}\n\nReport:\n{markdown_report}"
    )

