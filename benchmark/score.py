"""Benchmark evaluation against ground truth culprit commits."""
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import llm_client
from qa_agent.models import Finding
from rca_agent.analyzer import RCAResult


def get_commit_subject(sha: str, repo: Optional[Union[Path, str]] = None) -> str:
    """Get commit subject line using git log -1 --format=%s in testapp/repo."""
    if not sha:
        return ""
    repo_dir = Path(repo) if repo else (Path(__file__).resolve().parent.parent / "testapp" / "repo")
    if not repo_dir.exists():
        return ""
    try:
        res = subprocess.run(
            ["git", "log", "-1", "--format=%s", sha],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return ""


def score(
    findings: List[Finding],
    results: Union[Dict[str, List[RCAResult]], List[RCAResult]],
    truth: List[Dict[str, Any]],
    repo: Optional[Union[Path, str]] = None,
) -> Tuple[Dict[str, Any], str]:
    """Score findings and RCA results against ground truth, returning summary dict and markdown."""
    # Organize findings by route
    findings_by_route: Dict[str, Any] = {
        (f.route if hasattr(f, "route") else f["route"]): f for f in findings
    }

    # Organize results by mode and finding_id
    results_by_mode: Dict[str, Dict[str, Any]] = {}
    if isinstance(results, dict):
        for mode, r_list in results.items():
            results_by_mode[mode] = {
                (r.finding_id if hasattr(r, "finding_id") else r["finding_id"]): r
                for r in r_list
            }
    elif isinstance(results, list):
        for r in results:
            r_mode = r.mode if hasattr(r, "mode") else r["mode"]
            r_fid = r.finding_id if hasattr(r, "finding_id") else r["finding_id"]
            if r_mode not in results_by_mode:
                results_by_mode[r_mode] = {}
            results_by_mode[r_mode][r_fid] = r

    # Determine ordered modes
    preferred_order = ["baseline", "llm"]
    modes = [m for m in preferred_order if m in results_by_mode]
    for m in results_by_mode:
        if m not in modes:
            modes.append(m)

    total_bugs = len(truth)
    detected_count = 0
    reproduced_count = 0

    mode_correct_counts: Dict[str, int] = {m: 0 for m in modes}
    llm_invalid = False
    llm_failed_count = 0
    llm_first_error = ""

    if "llm" in results_by_mode:
        llm_list = list(results_by_mode["llm"].values())
        failed_calls = [
            r
            for r in llm_list
            if (
                r.root_cause if hasattr(r, "root_cause") else r.get("root_cause", "")
            ).startswith("LLM analysis failed")
        ]
        if failed_calls:
            llm_invalid = True
            llm_failed_count = len(failed_calls)
            first_rc = (
                failed_calls[0].root_cause
                if hasattr(failed_calls[0], "root_cause")
                else failed_calls[0].get("root_cause", "")
            )
            llm_first_error = first_rc.removeprefix("LLM analysis failed: ")

    # Compute row details
    rows: List[Dict[str, Any]] = []
    for bug in truth:
        b_id = bug["bug_id"]
        b_route = bug["route"]
        culprit = bug["culprit_commit"]
        masked = bug.get("masked_by_commit")

        f = findings_by_route.get(b_route)
        is_detected = f is not None
        is_repro = bool(
            (f.reproduced if hasattr(f, "reproduced") else f.get("reproduced"))
            if f
            else False
        )

        if is_detected:
            detected_count += 1
        if is_repro:
            reproduced_count += 1

        f_id = (f.id if hasattr(f, "id") else f["id"]) if f else None
        row_mode_status: Dict[str, str] = {}
        for m in modes:
            if m == "llm" and llm_invalid:
                row_mode_status[m] = "invalid"
                continue

            r = results_by_mode[m].get(f_id) if f_id else None
            r_suspect = (
                r.suspected_commit
                if hasattr(r, "suspected_commit")
                else (r.get("suspected_commit") if r else None)
            )
            if r and r_suspect and r_suspect == culprit:
                mode_correct_counts[m] += 1
                row_mode_status[m] = "CORRECT"
            else:
                row_mode_status[m] = "MISS"

        rows.append(
            {
                "bug_id": b_id,
                "route": b_route,
                "detected": is_detected,
                "reproduced": is_repro,
                "is_trap": bool(masked),
                "modes": row_mode_status,
            }
        )

    # Build Markdown Table
    mode_headers = " | ".join(f"{'LLM' if m.lower() == 'llm' else m.capitalize()}" for m in modes)
    sep_headers = " | ".join(["---"] * len(modes))
    table_header = f"| Bug | Route | Detected | Reproduced | {mode_headers} |"
    table_sep = f"|-----|-------|----------|------------|{sep_headers}|"

    md_lines: List[str] = [
        "# RootCause-QA Benchmark Score",
        "",
        table_header,
        table_sep,
    ]

    for row in rows:
        trap_label = " (blame-trap)" if row["is_trap"] else ""
        bug_label = f"`{row['bug_id']}`{trap_label}"
        det_val = "Yes" if row["detected"] else "No"
        rep_val = "Yes" if row["reproduced"] else "No"
        mode_vals = " | ".join(f"`{row['modes'].get(m, 'n/a')}`" for m in modes)
        md_lines.append(f"| {bug_label} | `{row['route']}` | {det_val} | {rep_val} | {mode_vals} |")

    md_lines.append("")
    md_lines.append("## Summary")
    md_lines.append(f"- **Detected:** {detected_count}/{total_bugs}")
    md_lines.append(f"- **Reproduced:** {reproduced_count}/{total_bugs}")

    for m in modes:
        if m == "llm" and llm_invalid:
            md_lines.append(
                f"- **LLM agent:** INVALID, {llm_failed_count} of {len(results_by_mode['llm'])} "
                f"calls failed (first error: {llm_first_error}). This is not a measured score."
            )
        else:
            md_lines.append(f"- **{m.capitalize()}:** {mode_correct_counts[m]}/{total_bugs} correct culprit commits")

    if "llm" in modes:
        md_lines.append(f"- **LLM Configuration:** {llm_client.describe()}")

    md_lines.append("")
    trap_bug = next((b for b in truth if b.get("masked_by_commit")), None)
    if trap_bug:
        c_sha = trap_bug.get("culprit_commit", "")
        m_sha = trap_bug.get("masked_by_commit", "")
        c_short = c_sha[:7] if c_sha else ""
        m_short = m_sha[:7] if m_sha else ""

        c_subject = get_commit_subject(c_sha, repo) or trap_bug.get("culprit_message", "")
        m_subject = get_commit_subject(m_sha, repo) or trap_bug.get("masked_message", "")

        md_lines.append(
            f"*{trap_bug['bug_id']} was introduced in {c_short} (\"{c_subject}\") "
            f"but masked by cosmetic commit {m_short} (\"{m_subject}\"). "
            "Plain git blame points at the cosmetic commit.*"
        )
    md_lines.append("")

    summary_dict = {
        "total_bugs": total_bugs,
        "detected": detected_count,
        "reproduced": reproduced_count,
        "modes": {
            m: {
                "correct": mode_correct_counts[m],
                "valid": not (m == "llm" and llm_invalid),
                "status": "invalid" if (m == "llm" and llm_invalid) else "valid",
                "errors": [llm_first_error] if (m == "llm" and llm_invalid and llm_first_error) else [],
                "total": total_bugs,
            }
            for m in modes
        },
        "llm_described": llm_client.describe() if "llm" in modes else None,
    }

    return summary_dict, "\n".join(md_lines)
