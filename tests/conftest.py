"""Pytest configuration and session fixtures for RootCause-QA test suite."""
import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from testapp.seed_history import seed_history


@pytest.fixture(scope="session", autouse=True)
def ensure_seeded_repo() -> None:
    """Ensure testapp/repo with .git folder exists before running any tests."""
    repo_dir = ROOT_DIR / "testapp" / "repo"
    git_dir = repo_dir / ".git"

    if not repo_dir.exists() or not git_dir.exists():
        seed_history()
