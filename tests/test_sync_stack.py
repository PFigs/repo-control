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


def test_sync_stack_new_layout_main_is_repo_dir(tmp_path: Path):
    remote = tmp_path / "remote.git"
    run(["git", "init", "--bare", "-b", "main", str(remote)], tmp_path)
    repo_dir = tmp_path / "n"
    run(["git", "clone", str(remote), str(repo_dir)], tmp_path)
    run(["git", "config", "user.email", "test@example.com"], repo_dir)
    run(["git", "config", "user.name", "test"], repo_dir)
    commit(repo_dir, "c1")
    run(["git", "push", "-u", "origin", "main"], repo_dir)
    run(["git", "switch", "-c", "feat"], repo_dir)
    commit(repo_dir, "feat-c1")
    run(["git", "push", "-u", "origin", "feat"], repo_dir)
    run(["git", "switch", "main"], repo_dir)
    run(["git", "branch", "-D", "feat"], repo_dir)
    git.fetch(repo_path=repo_dir)

    git.worktree_add_sidecar(
        repo_path=repo_dir,
        target=repo_dir / ".worktrees" / "1-feat",
        real_branch="feat",
        sidecar_branch="claude/feat",
        start_point="origin/feat",
    )
    (repo_dir / ".repo-control").mkdir()
    (repo_dir / ".repo-control" / "state.json").write_text("{}")

    scratch = tmp_path / "scratch"
    run(["git", "clone", str(remote), str(scratch)], tmp_path)
    run(["git", "config", "user.email", "test@example.com"], scratch)
    run(["git", "config", "user.name", "test"], scratch)
    commit(scratch, "main-c2")
    run(["git", "push", "origin", "main"], scratch)

    repo = state.RepoDir(owner="o", name="n", path=repo_dir, main_path=repo_dir)
    notes = _sync_stack_repo(repo=repo)

    assert sha(repo_dir, "main") == sha(scratch, "HEAD")
    assert any("inbound: claude/feat rebased onto feat" in line for line in notes)
    exclude_lines = (repo_dir / ".git" / "info" / "exclude").read_text().splitlines()
    assert "/.worktrees/" in exclude_lines
    assert "/.repo-control/" in exclude_lines


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
