"""Root-cause analysis engine supporting both baseline git-blame and LLM reasoning."""
import json
import os
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import llm_client
from qa_agent.models import Finding
from rca_agent.git_tools import (
    blame_line,
    file_log,
    line_history,
    numbered_context,
    patch_applies,
    resolve_commit,
    show_commit,
)
from rca_agent.log_parser import ServerTrace


@dataclass
class Evidence:
    """Collected forensic evidence for a specific finding and its server traceback."""

    finding: Finding
    trace: Optional[ServerTrace]
    file: str
    line: int
    code_context: str
    blame: Dict[str, str]
    line_history: str
    blamed_commit: str
    file_log: str


@dataclass
class RCAResult:
    """Structured conclusion of root-cause analysis."""

    finding_id: str
    mode: str
    suspected_commit: Optional[str]
    root_cause: str
    confidence: float
    reasoning: List[str]
    fix_patch: str
    patch_applies: bool
    exception: Optional[str]
    location: Optional[str]
    blame: Optional[Dict[str, str]]
    traceback: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert RCA result to a serializable dictionary."""
        return {
            "finding_id": self.finding_id,
            "mode": self.mode,
            "suspected_commit": self.suspected_commit,
            "root_cause": self.root_cause,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "fix_patch": self.fix_patch,
            "patch_applies": self.patch_applies,
            "exception": self.exception,
            "location": self.location,
            "blame": self.blame,
            "traceback": self.traceback,
        }


def collect_evidence(
    finding: Finding,
    repo: Path | str,
    traces: List[ServerTrace],
) -> Optional[Evidence]:
    """Match server traceback to finding and gather git blame, history, and context."""
    req_path = urllib.parse.urlparse(finding.url).path
    matched_trace: Optional[ServerTrace] = None

    for trace in reversed(traces):
        if trace.path == req_path and trace.method == finding.method:
            matched_trace = trace
            break

    if not matched_trace:
        return None

    app_fr = matched_trace.app_frame(repo)
    if not app_fr:
        return None

    file_rel = os.path.relpath(app_fr.file, str(repo)).replace("\\", "/")
    blame_info = blame_line(repo, file_rel, app_fr.line)
    hist = line_history(repo, file_rel, max(1, app_fr.line - 2), app_fr.line + 2)
    blamed_diff = show_commit(repo, blame_info["sha"])
    flog = file_log(repo, file_rel, limit=30)
    context = numbered_context(repo, file_rel, app_fr.line, radius=10)

    return Evidence(
        finding=finding,
        trace=matched_trace,
        file=file_rel,
        line=app_fr.line,
        code_context=context,
        blame=blame_info,
        line_history=hist,
        blamed_commit=blamed_diff,
        file_log=flog,
    )


def baseline_rca(
    finding: Finding,
    repo: Path | str,
    evidence: Optional[Evidence],
) -> RCAResult:
    """Identify culprit commit directly from git blame on the failing line."""
    if not evidence or not evidence.trace:
        return RCAResult(
            finding_id=finding.id,
            mode="baseline",
            suspected_commit=None,
            root_cause="No server traceback found to identify failing source line.",
            confidence=0.0,
            reasoning=["No unhandled server exception trace matched this finding."],
            fix_patch="",
            patch_applies=False,
            exception=None,
            location=None,
            blame=None,
            traceback=None,
        )

    sha = evidence.blame["sha"]
    summary = evidence.blame["summary"]
    root_cause = (
        f"Git blame attributes failing line {evidence.line} of {evidence.file} "
        f"to commit {sha[:7]} ('{summary}')."
    )
    reasoning = [
        f"Git blame on {evidence.file}:{evidence.line} points to {sha[:7]} by {evidence.blame['author']}.",
        f"Commit message: {summary}.",
    ]

    return RCAResult(
        finding_id=finding.id,
        mode="baseline",
        suspected_commit=sha,
        root_cause=root_cause,
        confidence=0.5,
        reasoning=reasoning,
        fix_patch="",
        patch_applies=False,
        exception=evidence.trace.exception,
        location=f"{evidence.file}:{evidence.line}",
        blame=evidence.blame,
        traceback=evidence.trace.raw,
    )


def llm_rca(
    finding: Finding,
    repo: Path | str,
    evidence: Optional[Evidence],
) -> RCAResult:
    """Query LLM to trace behavioural regression through line history and diffs."""
    if not evidence or not evidence.trace:
        return RCAResult(
            finding_id=finding.id,
            mode="llm",
            suspected_commit=None,
            root_cause="No server traceback available for analysis.",
            confidence=0.0,
            reasoning=["Missing traceback."],
            fix_patch="",
            patch_applies=False,
            exception=None,
            location=None,
            blame=None,
            traceback=None,
        )

    system_prompt = (
        "you are a senior engineer doing root-cause analysis on a regression; "
        "identify the commit that INTRODUCED the faulty behaviour; "
        "the commit git blame names may only be cosmetic (formatting, rename, refactor), "
        "so use the line history and diffs to find the commit that changed behaviour. "
        "Reply with ONE JSON object: suspected_commit, root_cause (2-3 sentences), "
        "reasoning (list of short evidence bullets citing short SHAs), confidence (0-1), "
        "fix_patch (a unified diff against HEAD with a/ and b/ headers, or \"\")."
    )

    user_prompt = (
        f"Bug Finding: {finding.method} {finding.url} ({finding.route})\n"
        f"Status: {finding.status}\n"
        f"Exception: {evidence.trace.exception}\n"
        f"Failing Location: {evidence.file}:{evidence.line}\n\n"
        f"Code Context around Line {evidence.line}:\n{evidence.code_context}\n\n"
        f"Git Blame for Line {evidence.line}:\n"
        f"SHA: {evidence.blame['sha']}\nAuthor: {evidence.blame['author']}\n"
        f"Summary: {evidence.blame['summary']}\n\n"
        f"Line History (`git log -L` around line {evidence.line}):\n"
        f"{evidence.line_history}\n\n"
        f"Diff of Blamed Commit ({evidence.blame['sha'][:7]}):\n"
        f"{evidence.blamed_commit[:2500]}\n\n"
        f"Recent File Commits:\n{evidence.file_log}\n\n"
        "Analyze the regression and return ONE JSON object."
    )

    resp_text = llm_client.chat(system=system_prompt, user=user_prompt)

    start = resp_text.find("{")
    end = resp_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No valid JSON object found in LLM response: {resp_text[:300]}")

    json_str = resp_text[start : end + 1]
    parsed = json.loads(json_str, strict=False)

    raw_suspect = str(parsed.get("suspected_commit", "")).strip()
    reasoning = [str(r) for r in parsed.get("reasoning", [])]

    resolved = resolve_commit(repo, raw_suspect) if raw_suspect else None
    if not resolved:
        suspected_commit = None
        reasoning.append(f"Suspected commit '{raw_suspect}' could not be resolved in git history.")
    else:
        suspected_commit = resolved

    fix_patch = str(parsed.get("fix_patch", "")).strip()
    applies = patch_applies(repo, fix_patch) if fix_patch else False

    return RCAResult(
        finding_id=finding.id,
        mode="llm",
        suspected_commit=suspected_commit,
        root_cause=str(parsed.get("root_cause", "")),
        confidence=float(parsed.get("confidence", 0.0)),
        reasoning=reasoning,
        fix_patch=fix_patch,
        patch_applies=applies,
        exception=evidence.trace.exception,
        location=f"{evidence.file}:{evidence.line}",
        blame=evidence.blame,
        traceback=evidence.trace.raw,
    )


def analyze(
    finding: Finding,
    repo: Path | str,
    traces: List[ServerTrace],
    mode: str = "baseline",
) -> RCAResult:
    """Analyze finding using baseline git-blame or LLM reasoning without silent fallback."""
    evidence = collect_evidence(finding, repo, traces)
    if mode == "baseline":
        return baseline_rca(finding, repo, evidence)
    elif mode == "llm":
        try:
            return llm_rca(finding, repo, evidence)
        except Exception as exc:
            return RCAResult(
                finding_id=finding.id,
                mode="llm",
                suspected_commit=None,
                root_cause=f"LLM analysis failed: {exc}",
                confidence=0.0,
                reasoning=[f"Error during LLM analysis: {exc}"],
                fix_patch="",
                patch_applies=False,
                exception=evidence.trace.exception if (evidence and evidence.trace) else None,
                location=f"{evidence.file}:{evidence.line}" if evidence else None,
                blame=evidence.blame if evidence else None,
                traceback=evidence.trace.raw if (evidence and evidence.trace) else None,
            )
    else:
        raise ValueError(f"Unknown analysis mode: {mode}")
