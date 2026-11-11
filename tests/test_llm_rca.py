"""Unit tests for llm_rca handling short SHAs, malformed JSON, and non-existent commits."""
import json
import sys
from pathlib import Path
from typing import Any, Dict
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import llm_client
from qa_agent.models import Finding
from rca_agent.analyzer import Evidence, analyze, llm_rca
from rca_agent.log_parser import Frame, ServerTrace


@pytest.fixture
def sample_finding_and_evidence() -> tuple[Path, Finding, Evidence]:
    """Provide a valid Finding, Evidence, and repo directory for RCA tests."""
    repo_dir = ROOT_DIR / "testapp" / "repo"
    gt_file = ROOT_DIR / "testapp" / "ground_truth.json"

    if not gt_file.exists() or not repo_dir.exists():
        from testapp.seed_history import seed_history

        seed_history()

    finding = Finding(
        id="F01",
        kind="http_500",
        method="GET",
        url="http://127.0.0.1:5055/discount?code=NOPE",
        route="/discount",
        status=500,
        summary="HTTP 500 on /discount",
        steps=[],
        console=[],
        reproduced=True,
    )

    evidence = Evidence(
        finding=finding,
        trace=ServerTrace(
            method="GET",
            path="/discount",
            exception="KeyError: 'NOPE'",
            frames=[
                Frame(
                    file=str(repo_dir / "app.py"),
                    line=111,
                    func="discount",
                    code="rate = DISCOUNTS[code.upper()]",
                )
            ],
            raw="Traceback...",
        ),
        file="app.py",
        line=111,
        code_context="> 111: rate = DISCOUNTS[code.upper()]",
        blame={"sha": "dummy", "author": "Tester", "date": "2026-10-22", "summary": "commit"},
        line_history="commit history...",
        blamed_commit="diff content...",
        file_log="file log content...",
    )

    return repo_dir, finding, evidence


def test_llm_rca_resolves_short_sha(
    sample_finding_and_evidence: tuple[Path, Finding, Evidence],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a short commit SHA returned by LLM is resolved to full 40-char SHA."""
    repo_dir, finding, evidence = sample_finding_and_evidence
    gt_file = ROOT_DIR / "testapp" / "ground_truth.json"
    gt = json.loads(gt_file.read_text(encoding="utf-8"))

    # Pick a real commit SHA from ground truth
    b1_info = next(item for item in gt if item["bug_id"] == "B1")
    full_sha = b1_info["culprit_commit"]
    short_sha = full_sha[:7]

    mock_response = json.dumps(
        {
            "suspected_commit": short_sha,
            "root_cause": "Unchecked dictionary lookup in discount calculation.",
            "reasoning": [f"Commit {short_sha} removed safe dict lookup."],
            "confidence": 0.95,
            "fix_patch": "",
        }
    )

    monkeypatch.setattr(llm_client, "chat", lambda system, user, **kwargs: mock_response)

    result = llm_rca(finding, repo_dir, evidence)
    assert result.suspected_commit == full_sha
    assert result.mode == "llm"
    assert result.confidence == 0.95
    assert len(result.reasoning) >= 1


def test_llm_rca_handles_bad_json(
    sample_finding_and_evidence: tuple[Path, Finding, Evidence],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that malformed JSON from LLM raises ValueError or produces a failed RCAResult."""
    repo_dir, finding, evidence = sample_finding_and_evidence

    # 1. Non-JSON string causes llm_rca to raise ValueError
    monkeypatch.setattr(llm_client, "chat", lambda system, user, **kwargs: "I cannot analyze this.")
    with pytest.raises(ValueError):
        llm_rca(finding, repo_dir, evidence)

    # 2. analyze(mode='llm') captures the exception gracefully into RCAResult
    res = analyze(finding, repo_dir, [evidence.trace] if evidence.trace else [], mode="llm")
    assert res.mode == "llm"
    assert res.suspected_commit is None
    assert res.confidence == 0.0
    assert "LLM analysis failed" in res.root_cause

    # 3. Truncated / malformed JSON inside braces
    monkeypatch.setattr(llm_client, "chat", lambda system, user, **kwargs: '{"suspected_commit": "abc", broken json')
    with pytest.raises(ValueError):
        llm_rca(finding, repo_dir, evidence)


def test_llm_rca_handles_nonexistent_sha(
    sample_finding_and_evidence: tuple[Path, Finding, Evidence],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that an unresolvable commit SHA sets suspected_commit to None and appends reasoning."""
    repo_dir, finding, evidence = sample_finding_and_evidence

    fake_sha = "deadbeef1234567890abcdef"
    mock_response = json.dumps(
        {
            "suspected_commit": fake_sha,
            "root_cause": "Suspected phantom commit.",
            "reasoning": ["Commit was deduced by hallucination."],
            "confidence": 0.7,
            "fix_patch": "",
        }
    )

    monkeypatch.setattr(llm_client, "chat", lambda system, user, **kwargs: mock_response)

    result = llm_rca(finding, repo_dir, evidence)
    assert result.suspected_commit is None
    assert any("could not be resolved in git history" in r for r in result.reasoning)
