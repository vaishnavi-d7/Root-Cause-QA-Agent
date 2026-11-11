"""Build seeded git history with 5 realistic bugs for RootCause-QA benchmark."""
import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

AUTHORS = {
    "Asha": ("Asha Dev", "asha@example.com"),
    "Ravi": ("Ravi Kumar", "ravi@example.com"),
    "Meena": ("Meena S", "meena@example.com"),
}


def safe_rmtree(target_dir: Path) -> None:
    """Safely remove directory tree clearing read-only flags on Windows."""
    if not target_dir.exists():
        return

    def _clear_readonly(func, path, exc):
        try:
            os.chmod(path, stat.S_IWRITE)
        except OSError:
            pass
        func(path)

    if sys.version_info >= (3, 12):
        shutil.rmtree(target_dir, onexc=_clear_readonly)
    else:
        shutil.rmtree(
            target_dir,
            onerror=lambda f, p, e: _clear_readonly(f, p, None),
        )


def apply_edit(file_path: Path, target: str, replacement: str) -> None:
    """Replace target text in file, asserting presence and uniqueness."""
    content = file_path.read_text(encoding="utf-8")
    assert target in content, f"Target text not found in {file_path}:\n{target}"
    assert content.count(target) == 1, (
        f"Target text occurs multiple times ({content.count(target)}) in {file_path}:\n{target}"
    )
    new_content = content.replace(target, replacement, 1)
    file_path.write_text(new_content, encoding="utf-8")


def run_git(args: List[str], cwd: Path, env: Dict[str, str]) -> str:
    """Execute git command and return stripped stdout."""
    res = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return res.stdout.strip()


def seed_history() -> List[Dict[str, Any]]:
    """Generate 10-commit git history with 5 bugs and blame-trap mask."""
    base_dir = Path(__file__).resolve().parent
    repo_dir = base_dir / "repo"
    app_clean_path = base_dir / "app_clean.py"
    ground_truth_path = base_dir / "ground_truth.json"

    assert app_clean_path.exists(), f"Reference app not found at {app_clean_path}"

    if repo_dir.exists():
        safe_rmtree(repo_dir)

    repo_dir.mkdir(parents=True, exist_ok=True)

    base_env = os.environ.copy()
    base_env["GIT_CONFIG_GLOBAL"] = ""
    base_env["GIT_CONFIG_SYSTEM"] = ""

    run_git(["-c", "init.defaultBranch=main", "init"], cwd=repo_dir, env=base_env)

    base_time = datetime.now(timezone.utc) - timedelta(days=40)
    commit_shas: List[str] = []

    def make_commit(
        index: int,
        author_key: str,
        message: str,
        file_paths: Optional[List[str]] = None,
    ) -> str:
        author_name, author_email = AUTHORS[author_key]
        commit_date = base_time + timedelta(days=3 * index, hours=index)
        date_str = commit_date.isoformat()

        env = base_env.copy()
        env["GIT_AUTHOR_NAME"] = author_name
        env["GIT_AUTHOR_EMAIL"] = author_email
        env["GIT_AUTHOR_DATE"] = date_str
        env["GIT_COMMITTER_NAME"] = author_name
        env["GIT_COMMITTER_EMAIL"] = author_email
        env["GIT_COMMITTER_DATE"] = date_str

        if file_paths:
            for p in file_paths:
                run_git(["add", p], cwd=repo_dir, env=env)
        else:
            run_git(["add", "-A"], cwd=repo_dir, env=env)

        run_git(["-c", "commit.gpgsign=false", "commit", "-m", message], cwd=repo_dir, env=env)
        sha = run_git(["rev-parse", "HEAD"], cwd=repo_dir, env=env)
        commit_shas.append(sha)
        return sha

    app_repo_path = repo_dir / "app.py"

    # Commit 0 (init): "Initial commit: Mini Shop" (Asha)
    app_repo_path.write_text(app_clean_path.read_text(encoding="utf-8"), encoding="utf-8")
    make_commit(0, "Asha", "Initial commit: Mini Shop", ["app.py"])

    # Commit 1 (noise): "docs: add README" (Asha)
    readme_path = repo_dir / "README.md"
    readme_path.write_text("# Mini Shop\n\nA lightweight shopping web application.\n", encoding="utf-8")
    make_commit(1, "Asha", "docs: add README", ["README.md"])

    # Commit 2 (BUG B1): "feat: normalise discount codes" (Ravi)
    target_b1 = (
        '    rate = DISCOUNTS.get(code.upper())\n'
        '    if rate is None:\n'
        '        return jsonify({"error": "invalid code"}), 404'
    )
    replace_b1 = '    rate = DISCOUNTS[code.upper()]'
    apply_edit(app_repo_path, target_b1, replace_b1)
    make_commit(2, "Ravi", "feat: normalise discount codes", ["app.py"])

    # Commit 3 (noise): "docs: explain cart_total" (Meena)
    target_noise_cart = 'def cart_total() -> float:'
    replace_noise_cart = (
        '# Calculate cart total based on items and products\n'
        'def cart_total() -> float:'
    )
    apply_edit(app_repo_path, target_noise_cart, replace_noise_cart)
    make_commit(3, "Meena", "docs: explain cart_total", ["app.py"])

    # Commit 4 (BUG B2): "perf: skip redundant user lookup in profile" (Meena)
    target_b2 = (
        '    user = USERS.get(user_id)\n'
        '    if user is None:\n'
        '        return jsonify({"error": "user not found"}), 404'
    )
    replace_b2 = '    user = USERS[user_id]'
    apply_edit(app_repo_path, target_b2, replace_b2)
    make_commit(4, "Meena", "perf: skip redundant user lookup in profile", ["app.py"])

    # Commit 5 (BUG B3): "refactor: simplify checkout summary" (Ravi)
    target_b3 = '    avg = total / len(CART) if CART else 0'
    replace_b3 = '    avg = total / len(CART)'
    apply_edit(app_repo_path, target_b3, replace_b3)
    make_commit(5, "Ravi", "refactor: simplify checkout summary", ["app.py"])

    # Commit 6 (noise): "chore: add .gitignore" (Asha)
    gitignore_path = repo_dir / ".gitignore"
    gitignore_path.write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    make_commit(6, "Asha", "chore: add .gitignore", [".gitignore"])

    # Commit 7 (BUG B4): "feat: let search match substrings" (Asha)
    target_b4 = (
        '    rows = conn.execute("SELECT id, name FROM products WHERE name LIKE ?", (f"%{q}%",)).fetchall()'
    )
    replace_b4 = (
        '    rows = conn.execute(f"SELECT id, name FROM products WHERE name LIKE \'%{q}%\'").fetchall()'
    )
    apply_edit(app_repo_path, target_b4, replace_b4)
    make_commit(7, "Asha", "feat: let search match substrings", ["app.py"])

    # Commit 8 (MASK for B4): "style: wrap long SQL line" (Meena)
    target_mask = (
        '    rows = conn.execute(f"SELECT id, name FROM products WHERE name LIKE \'%{q}%\'").fetchall()'
    )
    replace_mask = (
        '    rows = conn.execute(\n'
        '        f"SELECT id, name FROM products WHERE name LIKE \'%{q}%\'"\n'
        '    ).fetchall()'
    )
    apply_edit(app_repo_path, target_mask, replace_mask)
    make_commit(8, "Meena", "style: wrap long SQL line", ["app.py"])

    # Commit 9 (BUG B5): "cleanup: drop redundant try/except in cart add" (Ravi)
    target_b5 = (
        '    try:\n'
        '        product_id = int(data.get("product_id", ""))\n'
        '        qty = int(data.get("qty", ""))\n'
        '    except ValueError:\n'
        '        return jsonify({"error": "product_id and qty must be integers"}), 400'
    )
    replace_b5 = (
        '    product_id = int(data.get("product_id", ""))\n'
        '    qty = int(data.get("qty", ""))'
    )
    apply_edit(app_repo_path, target_b5, replace_b5)
    make_commit(9, "Ravi", "cleanup: drop redundant try/except in cart add", ["app.py"])

    assert len(commit_shas) == 10, f"Expected 10 commits, got {len(commit_shas)}"

    ground_truth = [
        {
            "bug_id": "B1",
            "route": "/discount",
            "exception": "KeyError",
            "description": "Unknown discount code raises unhandled KeyError instead of 404",
            "culprit_commit": commit_shas[2],
            "culprit_message": "feat: normalise discount codes",
            "file": "app.py",
            "masked_by_commit": None,
        },
        {
            "bug_id": "B2",
            "route": "/profile/<n>",
            "exception": "KeyError",
            "description": "Unknown user id raises unhandled KeyError instead of 404",
            "culprit_commit": commit_shas[4],
            "culprit_message": "perf: skip redundant user lookup in profile",
            "file": "app.py",
            "masked_by_commit": None,
        },
        {
            "bug_id": "B3",
            "route": "/checkout",
            "exception": "ZeroDivisionError",
            "description": "Checkout with empty cart raises ZeroDivisionError instead of returning average 0",
            "culprit_commit": commit_shas[5],
            "culprit_message": "refactor: simplify checkout summary",
            "file": "app.py",
            "masked_by_commit": None,
        },
        {
            "bug_id": "B4",
            "route": "/search",
            "exception": "OperationalError",
            "description": "Search query with single quote breaks unparameterised SQL query",
            "culprit_commit": commit_shas[7],
            "culprit_message": "feat: let search match substrings",
            "file": "app.py",
            "masked_by_commit": commit_shas[8],
        },
        {
            "bug_id": "B5",
            "route": "/cart/add",
            "exception": "ValueError",
            "description": "Empty or invalid quantity raises unhandled ValueError instead of 400",
            "culprit_commit": commit_shas[9],
            "culprit_message": "cleanup: drop redundant try/except in cart add",
            "file": "app.py",
            "masked_by_commit": None,
        },
    ]

    ground_truth_path.write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")

    print("=" * 86)
    print(f"{'Bug ID':<7} | {'Route':<14} | {'Short SHA':<9} | {'Message':<36} | Note")
    print("-" * 86)
    for bug in ground_truth:
        short_sha = bug["culprit_commit"][:7]
        note = "(blame-trap)" if bug["masked_by_commit"] else ""
        print(
            f"{bug['bug_id']:<7} | {bug['route']:<14} | {short_sha:<9} | {bug['culprit_message']:<36} | {note}"
        )
    print("=" * 86)

    return ground_truth


if __name__ == "__main__":
    seed_history()
