import shutil
import subprocess
from pathlib import Path


def run_init(*, worktree_path: Path) -> list[str]:
    """Run mise/uv/npm init for a freshly-created worktree. Returns list of steps run."""
    steps: list[str] = []
    if (worktree_path / "mise.toml").exists() and shutil.which("mise"):
        subprocess.run(["mise", "install"], cwd=worktree_path, check=False)
        steps.append("mise install")
    if (worktree_path / "pyproject.toml").exists() and shutil.which("uv"):
        subprocess.run(["uv", "sync"], cwd=worktree_path, check=False)
        steps.append("uv sync")
    if (worktree_path / "package.json").exists() and shutil.which("npm"):
        subprocess.run(["npm", "install"], cwd=worktree_path, check=False)
        steps.append("npm install")
    return steps
