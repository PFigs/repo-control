import subprocess
from pathlib import Path

import pytest


def run(args: list[str], cwd: Path) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def commit(repo: Path, msg: str) -> None:
    (repo / f"{msg}.txt").write_text(msg)
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-m", msg], repo)


def sha(repo: Path, ref: str) -> str:
    return run(["git", "rev-parse", ref], repo)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo on `main` with a single commit."""
    root = tmp_path / "r"
    root.mkdir()
    run(["git", "init", "-b", "main"], root)
    run(["git", "config", "user.email", "test@example.com"], root)
    run(["git", "config", "user.name", "test"], root)
    commit(root, "c1")
    return root
