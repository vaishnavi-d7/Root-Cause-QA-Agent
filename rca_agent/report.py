"""Markdown investigation report generator synthesizing QA findings and RCA conclusions."""
from typing import Any, Dict, List, Optional, Union

from qa_agent.models import Finding, describe_steps
from rca_agent.analyzer import RCAResult


def _select_result(
    finding_id: str,
    results: Union[Dict[str, List[RCAResult]], List[RCAResult]],
) -> Optional[RCAResult]:
    """Select LLM result if it has a suspected commit; otherwise select baseline result."""
    llm_res: Optional[RCAResult] = None
    baseline_res: Optional[RCAResult] = None

    if isinstance(results, dict):
        llm_res = next((r for r in results.get("llm", []) if r.finding_id == finding_id), None)
        baseline_res = next((r for r in results.get("baseline", []) if r.finding_id == finding_id), None)
    elif isinstance(results, list):
        for r in results:
            if r.finding_id == finding_id:
                if r.mode == "llm":
                    llm_res = r
                elif r.mode == "baseline":
                    baseline_res = r

    if llm_res and llm_res.suspected_commit:
        return llm_res
    return baseline_res or llm_res


def render_report(
    findings: List[Finding],
    results: Union[Dict[str, List[RCAResult]], List[RCAResult]],
) -> str:
    """Render comprehensive markdown report covering findings, repro steps, and RCA."""
    lines: List[str] = [
        "# RootCause-QA Investigation Report",
        "",
        f"The QA agent found {len(findings)} distinct failure(s).",
        "",
        "## Executive Summary",
        "",
        "| ID | Failure | Reproduced | Suspected commit (7 chars) | Method |",
        "|----|---------|------------|----------------------------|--------|",
    ]

    for f in findings:
        res = _select_result(f.id, results)
        suspect = res.suspected_commit[:7] if (res and res.suspected_commit) else "none"
        repro_text = "Yes" if f.reproduced else "No"
        lines.append(f"| {f.id} | `{f.route}` ({f.kind}) | {repro_text} | `{suspect}` | {f.method} |")

    lines.append("")

    for f in findings:
        res = _select_result(f.id, results)
        lines.append(f"## Finding {f.id}: `{f.route}`")
        lines.append("")
        repro_val = "Yes" if f.reproduced else "No"
        lines.append(f"- **Kind:** `{f.kind}` | **Occurrences:** {f.occurrences}")
        lines.append(f"- **Reproduced:** {repro_val}")

        video_path = f.video or "n/a"
        screenshot_path = f.screenshot or "n/a"
        lines.append(f"- **Video:** [{video_path}]({video_path})")
        lines.append(f"- **Screenshot:** [{screenshot_path}]({screenshot_path})")
        lines.append("")

        lines.append("### Steps to Reproduce")
        step_sentences = describe_steps(f.steps)
        if step_sentences:
            for idx, sentence in enumerate(step_sentences, start=1):
                lines.append(f"{idx}. {sentence}")
        else:
            lines.append("No step actions recorded.")
        lines.append("")

        if res:
            lines.append("### Root Cause")
            lines.append(res.root_cause if res.root_cause else "No root cause narrative available.")
            lines.append("")

            loc_str = res.location or "unknown"
            exc_str = res.exception or "none"
            lines.append(f"- **Where:** `{loc_str}` ({exc_str})")

            commit_sha = f"`{res.suspected_commit[:7]}`" if res.suspected_commit else "None"
            lines.append(f"- **Suspected Commit:** {commit_sha} (Mode: `{res.mode}`, Confidence: {res.confidence:.2f})")

            if res.blame:
                b = res.blame
                blame_sha = b.get("sha", "")[:7]
                b_author = b.get("author", "unknown")
                b_date = b.get("date", "")
                b_summary = b.get("summary", "")
                lines.append(f"- **Git Blame:** `{blame_sha}` by {b_author} on {b_date} — \"{b_summary}\"")
            lines.append("")

            if res.reasoning:
                lines.append("### Evidence")
                for r in res.reasoning:
                    lines.append(f"- {r}")
                lines.append("")

            if res.traceback:
                lines.append("### Server Traceback")
                lines.append("```python")
                lines.append(res.traceback.strip())
                lines.append("```")
                lines.append("")

            if res.fix_patch:
                clean_status = "yes" if res.patch_applies else "no"
                lines.append("### Proposed Patch")
                lines.append(f"**Applies cleanly:** {clean_status}")
                lines.append("```diff")
                lines.append(res.fix_patch.strip())
                lines.append("```")
                lines.append("")
            else:
                lines.append("### Proposed Patch")
                lines.append("**Applies cleanly:** n/a")
                lines.append("")
        else:
            lines.append("### Root Cause")
            lines.append("No analysis result available for this finding.")
            lines.append("")

    return "\n".join(lines).strip() + "\n"
