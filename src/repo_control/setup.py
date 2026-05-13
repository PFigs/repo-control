import shutil
import subprocess
from pathlib import Path


def run_init(*, worktree_path: Path, cfg: dict) -> list[str]:
    """Run mise/uv/npm init for a freshly-created worktree. Returns list of steps run."""
    steps: list[str] = []
    if not cfg.get("auto_install", True):
        return steps
    if (worktree_path / "mise.toml").exists() and shutil.which("mise"):
        if cfg.get("auto_trust_mise", True):
            subprocess.run(["mise", "trust"], cwd=worktree_path, check=False)
        subprocess.run(["mise", "install"], cwd=worktree_path, check=False)
        steps.append("mise install")
    if (worktree_path / "pyproject.toml").exists() and shutil.which("uv"):
        subprocess.run(["uv", "sync"], cwd=worktree_path, check=False)
        steps.append("uv sync")
    if (worktree_path / "package.json").exists() and shutil.which("npm"):
        subprocess.run(["npm", "install"], cwd=worktree_path, check=False)
        steps.append("npm install")
    return steps
