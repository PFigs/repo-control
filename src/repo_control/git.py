import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class Worktree:
    path: Path
    branch: str | None  # None for detached HEAD


def _run(args: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            check=check,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise GitError(f"{' '.join(args)} failed: {error.stderr.strip()}") from error


def clone(*, owner: str, name: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    _run(["gh", "repo", "clone", f"{owner}/{name}", str(target)])


def default_branch(*, repo_path: Path) -> str:
    result = _run(
        ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
        cwd=repo_path,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout.strip().removeprefix("origin/")
    for candidate in ("main", "master"):
        check = _run(
            ["git", "rev-parse", "--verify", f"refs/heads/{candidate}"],
            cwd=repo_path,
            check=False,
        )
        if check.returncode == 0:
            return candidate
    raise GitError(f"could not determine default branch for {repo_path}")


def fetch(*, repo_path: Path, refspec: str | None = None) -> None:
    args = ["git", "fetch", "origin", "--prune"]
    if refspec is not None:
        args.append(refspec)
    _run(args, cwd=repo_path)


def fetch_fork(*, repo_path: Path, fork_url: str, head_branch: str, local_branch: str) -> None:
    _run(
        [
            "git",
            "fetch",
            fork_url,
            f"+{head_branch}:refs/heads/{local_branch}",
        ],
        cwd=repo_path,
    )


def fast_forward(*, repo_path: Path, branch: str) -> bool:
    head = _run(["git", "symbolic-ref", "--short", "HEAD"], cwd=repo_path, check=False)
    on_branch = head.returncode == 0 and head.stdout.strip() == branch
    if not on_branch:
        return False
    if not is_clean(worktree_path=repo_path):
        return False
    result = _run(
        ["git", "merge", "--ff-only", f"origin/{branch}"],
        cwd=repo_path,
        check=False,
    )
    return result.returncode == 0


def list_worktrees(*, repo_path: Path) -> list[Worktree]:
    result = _run(["git", "worktree", "list", "--porcelain"], cwd=repo_path)
    out: list[Worktree] = []
    current_path: Path | None = None
    current_branch: str | None = None
    detached = False
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            if current_path is not None:
                out.append(Worktree(path=current_path, branch=None if detached else current_branch))
            current_path = Path(line.removeprefix("worktree ").strip())
            current_branch = None
            detached = False
            continue
        if line.startswith("branch "):
            current_branch = line.removeprefix("branch ").strip().removeprefix("refs/heads/")
            continue
        if line.startswith("detached"):
            detached = True
            continue
    if current_path is not None:
        out.append(Worktree(path=current_path, branch=None if detached else current_branch))
    return out


def worktree_add(*, repo_path: Path, target: Path, branch: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    _run(
        ["git", "worktree", "add", str(target), branch],
        cwd=repo_path,
    )


def worktree_remove(*, repo_path: Path, target: Path) -> None:
    _run(
        ["git", "worktree", "remove", str(target)],
        cwd=repo_path,
    )


def delete_branch(*, repo_path: Path, branch: str) -> None:
    _run(["git", "branch", "-D", branch], cwd=repo_path, check=False)


def is_clean(*, worktree_path: Path) -> bool:
    status = _run(["git", "status", "--porcelain"], cwd=worktree_path)
    if status.stdout.strip():
        return False
    stash = _run(["git", "stash", "list"], cwd=worktree_path)
    if stash.stdout.strip():
        return False
    head = _run(["git", "symbolic-ref", "--short", "HEAD"], cwd=worktree_path, check=False)
    if head.returncode != 0:
        return True
    branch = head.stdout.strip()
    upstream = _run(
        ["git", "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"],
        cwd=worktree_path,
        check=False,
    )
    if upstream.returncode != 0:
        return False
    ahead = _run(
        ["git", "rev-list", "--count", f"{upstream.stdout.strip()}..{branch}"],
        cwd=worktree_path,
        check=False,
    )
    if ahead.returncode != 0:
        return True
    return ahead.stdout.strip() == "0"
