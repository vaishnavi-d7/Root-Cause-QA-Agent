"""Git analysis tools interacting with the repository via the git CLI."""
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def git(repo: Path | str, *args: str) -> str:
    """Execute git command in the target repository and return stripped stdout."""
    res = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return res.stdout.strip()


def blame_line(repo: Path | str, file: str, line: int) -> Dict[str, str]:
    """Inspect line author and commit details using git blame --porcelain."""
    output = git(repo, "blame", "--porcelain", f"-L{line},{line}", "--", file)
    lines = output.splitlines()
    sha = lines[0].split()[0] if lines else ""
    author = "Unknown"
    date_str = ""
    summary = ""

    for l in lines[1:]:
        if l.startswith("author "):
            author = l[7:].strip()
        elif l.startswith("author-time "):
            try:
                ts = int(l[12:].strip())
                date_str = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, OSError):
                date_str = l[12:].strip()
        elif l.startswith("summary "):
            summary = l[8:].strip()

    return {
        "sha": sha,
        "author": author,
        "date": date_str,
        "summary": summary,
    }


def show_commit(repo: Path | str, sha: str, max_chars: int = 5000) -> str:
    """Return git show commit details truncated to max_chars."""
    out = git(repo, "show", "--stat", "-p", sha)
    return out[:max_chars]


def line_history(repo: Path | str, file: str, start: int, end: int) -> str:
    """Extract line history across commits using git log -L."""
    file_path = Path(repo) / file
    total_lines = 1
    if file_path.exists():
        total_lines = max(1, len(file_path.read_text(encoding="utf-8", errors="replace").splitlines()))

    start_clamped = max(1, min(start, total_lines))
    end_clamped = max(start_clamped, min(end, total_lines))

    return git(repo, "log", f"-L{start_clamped},{end_clamped}:{file}")


def file_log(repo: Path | str, file: str, limit: int = 30) -> str:
    """Return recent commits touching the given file."""
    return git(repo, "log", f"-n{limit}", "--oneline", "--", file)


def numbered_context(repo: Path | str, file: str, center: int, radius: int = 10) -> str:
    """Return source code lines surrounding center with the failing line marked with '>'."""
    file_path = Path(repo) / file
    if not file_path.exists():
        return ""

    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    total = len(lines)
    start_idx = max(0, center - radius - 1)
    end_idx = min(total, center + radius)

    context_lines = []
    for idx in range(start_idx, end_idx):
        line_num = idx + 1
        marker = ">" if line_num == center else " "
        context_lines.append(f"{marker} {line_num:4d}: {lines[idx]}")

    return "\n".join(context_lines)


def resolve_commit(repo: Path | str, ref: str) -> Optional[str]:
    """Resolve a git reference or short SHA to full SHA, returning None if unknown."""
    if not ref or not ref.strip():
        return None
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--verify", f"{ref.strip()}^{{commit}}"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if res.returncode == 0:
            return res.stdout.strip()
        return None
    except Exception:
        return None


def patch_applies(repo: Path | str, patch: str) -> bool:
    """Check if unified diff patch applies cleanly against repository HEAD."""
    if not patch or not patch.strip():
        return False
    try:
        res = subprocess.run(
            ["git", "apply", "--check", "--recount", "-"],
            input=patch,
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return res.returncode == 0
    except Exception:
        return False
