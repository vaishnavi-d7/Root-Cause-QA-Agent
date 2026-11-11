"""Unit tests for git CLI wrapper tools."""
import subprocess
from pathlib import Path
from typing import Generator
import pytest

from qa_agent.explorer import safe_rmtree
from rca_agent.git_tools import blame_line, line_history, patch_applies, resolve_commit


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary git repository with two commits on a sample file."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    env = {
        "GIT_AUTHOR_NAME": "Test Author",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test Author",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }

    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=str(repo_dir), check=True, capture_output=True)

    test_file = repo_dir / "sample.py"
    test_file.write_text("line 1: initial\nline 2: initial\nline 3: initial\n", encoding="utf-8")
    subprocess.run(["git", "add", "sample.py"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-m", "initial commit"],
        cwd=str(repo_dir),
        env={**subprocess.os.environ, **env},
        check=True,
        capture_output=True,
    )

    test_file.write_text("line 1: initial\nline 2: modified\nline 3: initial\n", encoding="utf-8")
    subprocess.run(["git", "add", "sample.py"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-m", "second commit: modify line 2"],
        cwd=str(repo_dir),
        env={**subprocess.os.environ, **env},
        check=True,
        capture_output=True,
    )

    yield repo_dir

    # Cleanup with read-only safe rmtree handler for Windows / OneDrive
    safe_rmtree(repo_dir)


def test_blame_line(temp_git_repo: Path) -> None:
    """Verify blame_line retrieves sha, author, and commit summary."""
    blame = blame_line(temp_git_repo, "sample.py", 2)
    assert blame["author"] == "Test Author"
    assert blame["summary"] == "second commit: modify line 2"
    assert len(blame["sha"]) == 40


def test_line_history(temp_git_repo: Path) -> None:
    """Verify line_history retrieves git log -L history across commits."""
    history = line_history(temp_git_repo, "sample.py", 2, 2)
    assert "second commit: modify line 2" in history
    assert "initial commit" in history


def test_resolve_commit(temp_git_repo: Path) -> None:
    """Verify resolve_commit handles full SHA, short SHA, and unknown references."""
    # Obtain valid full SHA from HEAD
    res = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(temp_git_repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    full_sha = res.stdout.strip()
    short_sha = full_sha[:7]

    # Valid full SHA
    assert resolve_commit(temp_git_repo, full_sha) == full_sha

    # Valid short SHA
    assert resolve_commit(temp_git_repo, short_sha) == full_sha

    # Unknown reference
    assert resolve_commit(temp_git_repo, "nonexistent123") is None
    assert resolve_commit(temp_git_repo, "") is None


def test_patch_applies(temp_git_repo: Path) -> None:
    """Verify patch_applies correctly validates valid, wrong, and empty patches."""
    # Empty patch
    assert patch_applies(temp_git_repo, "") is False
    assert patch_applies(temp_git_repo, "   \n") is False

    # Valid patch against line 1
    valid_patch = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -1,3 +1,3 @@
-line 1: initial
+line 1: patched
 line 2: modified
 line 3: initial
"""
    assert patch_applies(temp_git_repo, valid_patch) is True

    # Wrong patch with non-matching context
    wrong_patch = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -1,3 +1,3 @@
-nonexistent line
+patched
 line 2: modified
 line 3: initial
"""
    assert patch_applies(temp_git_repo, wrong_patch) is False

