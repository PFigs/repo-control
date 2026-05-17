import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class Worktree:
    path: Path
    branch: str | None  # None for detached HEAD


@dataclass(frozen=True)
class DirtySummary:
    modified: int
    added: int
    deleted: int
    untracked: int
    ahead: int  # commits ahead of upstream tracking branch (0 if no upstream)
    unmerged: int  # commits on HEAD not patch-equivalent to anything on origin/<default>
    stashes: int
    porcelain: tuple[str, ...]  # raw `git status --porcelain` lines


def _run(
    args: list[str], *, cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess:
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


def clone_bare(*, owner: str, name: str, git_dir: Path) -> None:
    git_dir.parent.mkdir(parents=True, exist_ok=True)
    _run(["gh", "repo", "clone", f"{owner}/{name}", str(git_dir), "--", "--bare"])
    _run(
        ["git", "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*"],
        cwd=git_dir,
    )
    _run(["git", "fetch", "origin", "--prune"], cwd=git_dir)
    _run(["git", "remote", "set-head", "origin", "--auto"], cwd=git_dir)


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


def remote_url(*, repo_path: Path) -> str | None:
    result = _run(
        ["git", "config", "--get", "remote.origin.url"],
        cwd=repo_path,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def parse_owner_repo(*, url: str) -> tuple[str, str] | None:
    cleaned = url.removesuffix(".git").rstrip("/")
    for marker in ("github.com:", "github.com/"):
        idx = cleaned.find(marker)
        if idx == -1:
            continue
        tail = cleaned[idx + len(marker) :]
        parts = tail.split("/")
        if len(parts) < 2:
            return None
        return parts[0], parts[1]
    return None


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
    bare = False
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            if current_path is not None and not bare:
                out.append(Worktree(path=current_path, branch=None if detached else current_branch))
            current_path = Path(line.removeprefix("worktree ").strip())
            current_branch = None
            detached = False
            bare = False
            continue
        if line.startswith("branch "):
            current_branch = line.removeprefix("branch ").strip().removeprefix("refs/heads/")
            continue
        if line.startswith("detached"):
            detached = True
            continue
        if line == "bare":
            bare = True
            continue
    if current_path is not None and not bare:
        out.append(Worktree(path=current_path, branch=None if detached else current_branch))
    return out


def worktree_add(*, repo_path: Path, target: Path, branch: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    _run(
        ["git", "worktree", "add", str(target), branch],
        cwd=repo_path,
    )


def worktree_add_tracking(
    *, repo_path: Path, target: Path, local_branch: str, upstream: str
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    exists = _run(
        ["git", "rev-parse", "--verify", f"refs/heads/{local_branch}"],
        cwd=repo_path,
        check=False,
    )
    if exists.returncode == 0:
        _run(["git", "worktree", "add", str(target), local_branch], cwd=repo_path)
    else:
        _run(
            ["git", "worktree", "add", "-b", local_branch, str(target), upstream],
            cwd=repo_path,
        )
    _run(
        ["git", "branch", f"--set-upstream-to={upstream}", local_branch],
        cwd=repo_path,
    )


def worktree_remove(*, repo_path: Path, target: Path, force: bool = False) -> None:
    args = ["git", "worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(target))
    _run(args, cwd=repo_path)


def worktree_move(*, repo_path: Path, source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    _run(
        ["git", "worktree", "move", str(source), str(target)],
        cwd=repo_path,
    )


def delete_branch(*, repo_path: Path, branch: str) -> None:
    _run(["git", "branch", "-D", branch], cwd=repo_path, check=False)


def is_clean(*, worktree_path: Path) -> bool:
    status = _run(["git", "status", "--porcelain"], cwd=worktree_path)
    if status.stdout.strip():
        return False
    head = _run(["git", "symbolic-ref", "--short", "HEAD"], cwd=worktree_path, check=False)
    if head.returncode != 0:
        return True
    branch = head.stdout.strip()
    if _has_stash_for_branch(worktree_path=worktree_path, branch=branch):
        return False
    upstream = _run(
        ["git", "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"],
        cwd=worktree_path,
        check=False,
    )
    if upstream.returncode != 0:
        return _all_commits_merged(worktree_path=worktree_path)
    ahead = _run(
        ["git", "rev-list", "--count", f"{upstream.stdout.strip()}..{branch}"],
        cwd=worktree_path,
        check=False,
    )
    if ahead.returncode != 0:
        return True
    if ahead.stdout.strip() == "0":
        return True
    return _all_commits_merged(worktree_path=worktree_path)


def dirty_summary(*, worktree_path: Path) -> DirtySummary:
    """Per-worktree snapshot used by `vacuum` to show what's dirty."""
    status = _run(["git", "status", "--porcelain"], cwd=worktree_path, check=False)
    lines: list[str] = (
        [line for line in status.stdout.splitlines() if line] if status.returncode == 0 else []
    )
    modified = added = deleted = untracked = 0
    for line in lines:
        code = line[:2]
        if code == "??":
            untracked += 1
            continue
        x, y = code[0], code[1]
        if "A" in (x, y):
            added += 1
        elif "D" in (x, y):
            deleted += 1
        else:
            modified += 1

    head = _run(["git", "symbolic-ref", "--short", "HEAD"], cwd=worktree_path, check=False)
    ahead = 0
    unmerged = 0
    stashes = 0
    if head.returncode == 0:
        branch = head.stdout.strip()
        upstream = _run(
            ["git", "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"],
            cwd=worktree_path,
            check=False,
        )
        if upstream.returncode == 0:
            count = _run(
                ["git", "rev-list", "--count", f"{upstream.stdout.strip()}..{branch}"],
                cwd=worktree_path,
                check=False,
            )
            if count.returncode == 0 and count.stdout.strip().isdigit():
                ahead = int(count.stdout.strip())
        try:
            default = default_branch(repo_path=worktree_path)
        except GitError:
            default = None
        if default is not None:
            cherry = _run(
                ["git", "cherry", f"origin/{default}", "HEAD"],
                cwd=worktree_path,
                check=False,
            )
            if cherry.returncode == 0:
                unmerged = sum(1 for line in cherry.stdout.splitlines() if line.startswith("+"))
        stash = _run(["git", "stash", "list", "--format=%gs"], cwd=worktree_path, check=False)
        if stash.returncode == 0 and stash.stdout.strip():
            for subject in stash.stdout.splitlines():
                subject = subject.strip()
                for prefix in ("WIP on ", "On "):
                    if subject.startswith(prefix):
                        if subject.removeprefix(prefix).split(":", 1)[0] == branch:
                            stashes += 1
                        break
    return DirtySummary(
        modified=modified,
        added=added,
        deleted=deleted,
        untracked=untracked,
        ahead=ahead,
        unmerged=unmerged,
        stashes=stashes,
        porcelain=tuple(lines),
    )


def _has_stash_for_branch(*, worktree_path: Path, branch: str) -> bool:
    # `git stash list` shows stashes from every worktree sharing this .git;
    # filter to the ones recorded against this branch so unrelated stashes
    # on `main` don't make every feature worktree look dirty.
    result = _run(
        ["git", "stash", "list", "--format=%gs"],
        cwd=worktree_path,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return False
    for subject in result.stdout.splitlines():
        subject = subject.strip()
        for prefix in ("WIP on ", "On "):
            if subject.startswith(prefix):
                stash_branch = subject.removeprefix(prefix).split(":", 1)[0]
                if stash_branch == branch:
                    return True
                break
    return False


def _all_commits_merged(*, worktree_path: Path) -> bool:
    # True when every commit reachable from HEAD is patch-equivalent to a
    # commit on the default branch — covers squash/rebase merges where
    # `@{upstream}` is gone or hashes diverge but the work is on main.
    try:
        default = default_branch(repo_path=worktree_path)
    except GitError:
        return False
    result = _run(
        ["git", "cherry", f"origin/{default}", "HEAD"],
        cwd=worktree_path,
        check=False,
    )
    if result.returncode != 0:
        return False
    return not any(line.startswith("+") for line in result.stdout.splitlines())
