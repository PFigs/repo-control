from pathlib import Path

from conftest import commit, run, sha

from repo_control import git, state
from repo_control.__main__ import _acquire_lock, _release_lock, _sync_stack_repo


def _setup_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A repo-control-style repo dir with `n-main` cloned from a bare remote.

    Returns (repo_dir, main_path). `origin/feat` exists; `feat` is not local.
    """
    remote = tmp_path / "remote.git"
    run(["git", "init", "--bare", "-b", "main", str(remote)], tmp_path)
    repo_dir = tmp_path / "n"
    repo_dir.mkdir()
    main = repo_dir / "n-main"
    run(["git", "clone", str(remote), str(main)], tmp_path)
    run(["git", "config", "user.email", "test@example.com"], main)
    run(["git", "config", "user.name", "test"], main)
    commit(main, "c1")
    run(["git", "push", "-u", "origin", "main"], main)
    run(["git", "switch", "-c", "feat"], main)
    commit(main, "feat-c1")
    run(["git", "push", "-u", "origin", "feat"], main)
    run(["git", "switch", "main"], main)
    run(["git", "branch", "-D", "feat"], main)
    git.fetch(repo_path=main)
    return repo_dir, main


def test_sync_stack_reconciles_sidecar(tmp_path: Path):
    repo_dir, main = _setup_repo(tmp_path)
    wt = repo_dir / "n-1-feat"
    git.worktree_add_sidecar(
        repo_path=main,
        target=wt,
        real_branch="feat",
        sidecar_branch="claude/feat",
        start_point="origin/feat",
    )
    commit(wt, "sidecar-work")

    repo = state.RepoDir(owner="o", name="n", path=repo_dir, main_path=main)
    notes = _sync_stack_repo(repo=repo)

    # outbound: the real branch fast-forwarded to the sidecar's committed HEAD
    assert sha(main, "feat") == sha(wt, "HEAD")
    assert any("outbound" in line for line in notes)
    assert any("inbound" in line for line in notes)


def test_sync_stack_no_sidecars(tmp_path: Path):
    repo_dir, main = _setup_repo(tmp_path)
    repo = state.RepoDir(owner="o", name="n", path=repo_dir, main_path=main)
    notes = _sync_stack_repo(repo=repo)
    assert any("no sidecar worktrees" in line for line in notes)


def test_sync_stack_lock_is_exclusive(tmp_path: Path):
    lock = tmp_path / ".repo-control" / ".sync-stack.lock"
    held = _acquire_lock(path=lock)
    assert held is not None
    assert _acquire_lock(path=lock) is None
    _release_lock(handle=held)
    again = _acquire_lock(path=lock)
    assert again is not None
    _release_lock(handle=again)
