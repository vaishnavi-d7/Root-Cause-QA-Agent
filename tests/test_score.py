"""Unit tests for benchmark scoring and invalid LLM reporting."""
from pathlib import Path
from typing import Any, Dict, List

from benchmark.score import score
from qa_agent.models import Finding
from rca_agent.analyzer import RCAResult


def test_score_hand_made_findings_and_expected_table() -> None:
    """Verify score generates expected summary counts and markdown table for hand-made data."""
    truth: List[Dict[str, Any]] = [
        {
            "bug_id": "B1",
            "route": "/discount",
            "culprit_commit": "1111111111111111111111111111111111111111",
            "culprit_message": "feat: normalise discount codes",
            "masked_by_commit": None,
        },
        {
            "bug_id": "B2",
            "route": "/profile/<n>",
            "culprit_commit": "2222222222222222222222222222222222222222",
            "culprit_message": "perf: skip redundant user lookup",
            "masked_by_commit": None,
        },
        {
            "bug_id": "B3",
            "route": "/checkout",
            "culprit_commit": "3333333333333333333333333333333333333333",
            "culprit_message": "refactor: simplify checkout",
            "masked_by_commit": None,
        },
    ]

    findings = [
        Finding(
            id="F01",
            kind="http_500",
            method="GET",
            url="http://127.0.0.1:5055/discount?code=BAD",
            route="/discount",
            status=500,
            summary="HTTP 500 on /discount",
            steps=[],
            console=[],
            reproduced=True,
        ),
        Finding(
            id="F02",
            kind="http_500",
            method="GET",
            url="http://127.0.0.1:5055/profile/999",
            route="/profile/<n>",
            status=500,
            summary="HTTP 500 on /profile/<n>",
            steps=[],
            console=[],
            reproduced=True,
        ),
    ]

    results = {
        "baseline": [
            RCAResult(
                finding_id="F01",
                mode="baseline",
                suspected_commit="1111111111111111111111111111111111111111",  # Correct
                root_cause="blame on discount",
                confidence=0.5,
                reasoning=[],
                fix_patch="",
                patch_applies=False,
                exception=None,
                location=None,
                blame=None,
                traceback=None,
            ),
            RCAResult(
                finding_id="F02",
                mode="baseline",
                suspected_commit="9999999999999999999999999999999999999999",  # Wrong
                root_cause="blame on profile",
                confidence=0.5,
                reasoning=[],
                fix_patch="",
                patch_applies=False,
                exception=None,
                location=None,
                blame=None,
                traceback=None,
            ),
        ],
        "llm": [
            RCAResult(
                finding_id="F01",
                mode="llm",
                suspected_commit="1111111111111111111111111111111111111111",  # Correct
                root_cause="LLM semantic analysis discount",
                confidence=0.9,
                reasoning=["Evidence 1"],
                fix_patch="",
                patch_applies=True,
                exception=None,
                location=None,
                blame=None,
                traceback=None,
            ),
            RCAResult(
                finding_id="F02",
                mode="llm",
                suspected_commit="2222222222222222222222222222222222222222",  # Correct
                root_cause="LLM semantic analysis profile",
                confidence=0.95,
                reasoning=["Evidence 2"],
                fix_patch="",
                patch_applies=True,
                exception=None,
                location=None,
                blame=None,
                traceback=None,
            ),
        ],
    }

    summary, md_report = score(findings, results, truth)

    assert summary["total_bugs"] == 3
    assert summary["detected"] == 2
    assert summary["reproduced"] == 2
    assert summary["modes"]["baseline"]["correct"] == 1
    assert summary["modes"]["llm"]["correct"] == 2

    # Verify table headers and summary bullets in markdown
    assert "| Bug | Route | Detected | Reproduced | Baseline | LLM |" in md_report
    assert "- **Detected:** 2/3" in md_report
    assert "- **Reproduced:** 2/3" in md_report
    assert "- **Baseline:** 1/3 correct culprit commits" in md_report
    assert "- **Llm:** 2/3 correct culprit commits" in md_report


def test_score_invalid_llm_run_never_scored_zero() -> None:
    """Verify that when LLM calls fail, score reports INVALID and never 0/N measured score."""
    truth = [
        {
            "bug_id": "B1",
            "route": "/discount",
            "culprit_commit": "1111111111111111111111111111111111111111",
            "culprit_message": "feat: normalise discount codes",
            "masked_by_commit": None,
        }
    ]

    findings = [
        Finding(
            id="F01",
            kind="http_500",
            method="GET",
            url="http://127.0.0.1:5055/discount",
            route="/discount",
            status=500,
            summary="HTTP 500 on /discount",
            steps=[],
            console=[],
            reproduced=True,
        )
    ]

    # LLM failed call with explicit "LLM analysis failed: ..."
    results = {
        "llm": [
            RCAResult(
                finding_id="F01",
                mode="llm",
                suspected_commit=None,
                root_cause="LLM analysis failed: Provider quota exceeded (429)",
                confidence=0.0,
                reasoning=["Error during LLM analysis: 429 quota"],
                fix_patch="",
                patch_applies=False,
                exception=None,
                location=None,
                blame=None,
                traceback=None,
            )
        ]
    }

    summary, md_report = score(findings, results, truth)

    # The mode must be flagged invalid, not valid with 0 score
    assert summary["modes"]["llm"]["valid"] is False
    assert summary["modes"]["llm"]["status"] == "invalid"
    assert "Provider quota exceeded (429)" in summary["modes"]["llm"]["errors"][0]

    # The report must explicitly state INVALID and that it is not a measured score
    assert "INVALID" in md_report
    assert "This is not a measured score." in md_report
    assert "- **Llm:** 0/1 correct culprit commits" not in md_report
