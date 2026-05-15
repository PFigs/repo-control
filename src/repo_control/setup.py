import os
import shutil
import subprocess
from pathlib import Path

HOOKS_DIR = ".repo-control"


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


def run_post_create(*, repo_path: Path, worktree_path: Path, ctx: dict) -> list[str]:
    """Run the per-repo post-create hook, if present. Returns list of steps."""
    return _run_hook(name="post-create", repo_path=repo_path, worktree_path=worktree_path, ctx=ctx)


def run_post_sync(*, repo_path: Path, worktree_path: Path, ctx: dict) -> list[str]:
    """Run the per-repo post-sync hook, if present. Returns list of steps."""
    return _run_hook(name="post-sync", repo_path=repo_path, worktree_path=worktree_path, ctx=ctx)


def _run_hook(*, name: str, repo_path: Path, worktree_path: Path, ctx: dict) -> list[str]:
    hook = repo_path / HOOKS_DIR / name
    if not hook.is_file():
        return []
    if not os.access(hook, os.X_OK):
        print(f"  warning: {hook} is not executable; skipping (chmod +x to enable)")
        return []
    env = {
        **os.environ,
        "REPO_CONTROL_EVENT": name,
        "REPO_CONTROL_WORKTREE": str(worktree_path),
        "REPO_CONTROL_REPO_PATH": str(repo_path),
        "REPO_CONTROL_OWNER": ctx["owner"],
        "REPO_CONTROL_REPO": ctx["name"],
        "REPO_CONTROL_PR_NUMBER": str(ctx["pr_number"]),
        "REPO_CONTROL_BRANCH": ctx["branch"],
    }
    result = subprocess.run([str(hook)], cwd=worktree_path, env=env, check=False)
    label = f"hook:{name}"
    if result.returncode != 0:
        return [f"{label} FAILED rc={result.returncode}"]
    return [label]
