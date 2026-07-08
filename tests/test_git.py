from pathlib import Path

from conftest import commit, run, sha

from repo_control import git


def _cloned_repo(tmp_path: Path, name: str = "clone") -> tuple[Path, Path]:
    """A bare remote plus a clone on `main` with one pushed commit."""
    remote = tmp_path / "remote.git"
    if not remote.exists():
        run(["git", "init", "--bare", "-b", "main", str(remote)], tmp_path)
    clone = tmp_path / name
    run(["git", "clone", str(remote), str(clone)], tmp_path)
    run(["git", "config", "user.email", "test@example.com"], clone)
    run(["git", "config", "user.name", "test"], clone)
    return remote, clone


def _feat_ahead_of_main(repo: Path) -> None:
    """Create `feat` one commit ahead of `main`, leaving HEAD detached."""
    git.create_branch(repo_path=repo, name="feat", start_point="main")
    run(["git", "switch", "feat"], repo)
    commit(repo, "c2")
    run(["git", "checkout", "--detach"], repo)


def test_branch_exists(repo: Path):
    assert git.branch_exists(repo_path=repo, branch="main") is True
    assert git.branch_exists(repo_path=repo, branch="missing") is False


def test_is_ancestor(repo: Path):
    _feat_ahead_of_main(repo)
    assert git.is_ancestor(repo_path=repo, ancestor="main", descendant="feat") is True
    assert git.is_ancestor(repo_path=repo, ancestor="feat", descendant="main") is False


def test_fast_forward_branch_moves_on_fast_forward(repo: Path):
    _feat_ahead_of_main(repo)
    moved = git.fast_forward_branch(repo_path=repo, branch="main", to_ref="feat")
    assert moved is True
    assert sha(repo, "main") == sha(repo, "feat")


def test_fast_forward_branch_noop_when_already_equal(repo: Path):
    git.create_branch(repo_path=repo, name="feat", start_point="main")
    run(["git", "checkout", "--detach"], repo)
    assert git.fast_forward_branch(repo_path=repo, branch="main", to_ref="feat") is False


def test_fast_forward_branch_noop_on_divergence(repo: Path):
    git.create_branch(repo_path=repo, name="feat", start_point="main")
    run(["git", "switch", "feat"], repo)
    commit(repo, "feat-only")
    run(["git", "switch", "main"], repo)
    commit(repo, "main-only")
    before = sha(repo, "main")
    run(["git", "checkout", "--detach"], repo)
    assert git.fast_forward_branch(repo_path=repo, branch="main", to_ref="feat") is False
    assert sha(repo, "main") == before


def test_current_branch(repo: Path):
    assert git.current_branch(worktree_path=repo) == "main"
    run(["git", "checkout", "--detach"], repo)
    assert git.current_branch(worktree_path=repo) is None


def test_has_graphite(repo: Path):
    assert git.has_graphite(repo_path=repo) is False
    git_dir = repo / run(["git", "rev-parse", "--git-dir"], repo)
    (git_dir / ".graphite_repo_config").write_text("{}")
    assert git.has_graphite(repo_path=repo) is True


def test_ensure_excluded_creates_file_and_is_idempotent(repo: Path):
    exclude = repo / ".git" / "info" / "exclude"
    if exclude.exists():
        exclude.unlink()
    git.ensure_excluded(worktree_path=repo, patterns=["/.worktrees/", "/.repo-control/"])
    assert exclude.read_text() == "/.worktrees/\n/.repo-control/\n"
    first = exclude.read_bytes()
    git.ensure_excluded(worktree_path=repo, patterns=["/.worktrees/", "/.repo-control/"])
    assert exclude.read_bytes() == first


def test_ensure_excluded_preserves_existing_lines(repo: Path):
    exclude = repo / ".git" / "info" / "exclude"
    exclude.parent.mkdir(exist_ok=True)
    exclude.write_text("foo.txt\n")
    git.ensure_excluded(worktree_path=repo, patterns=["/.worktrees/"])
    assert exclude.read_text() == "foo.txt\n/.worktrees/\n"


def test_ensure_excluded_noop_without_git_dir(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    git.ensure_excluded(worktree_path=plain, patterns=["/.worktrees/"])
    assert not (plain / ".git").exists()


def test_is_clean_untracked_dir_then_excluded(tmp_path: Path):
    _, clone = _cloned_repo(tmp_path)
    commit(clone, "c1")
    run(["git", "push", "-u", "origin", "main"], clone)
    assert git.is_clean(worktree_path=clone) is True
    (clone / ".worktrees").mkdir()
    (clone / ".worktrees" / "junk.txt").write_text("junk")
    assert git.is_clean(worktree_path=clone) is False
    git.ensure_excluded(worktree_path=clone, patterns=["/.worktrees/"])
    assert git.is_clean(worktree_path=clone) is True


def test_fast_forward_with_excluded_untracked_dirs(tmp_path: Path):
    _, main = _cloned_repo(tmp_path, name="main")
    commit(main, "c1")
    run(["git", "push", "-u", "origin", "main"], main)
    _, scratch = _cloned_repo(tmp_path, name="scratch")
    commit(scratch, "c2")
    run(["git", "push", "origin", "main"], scratch)

    (main / ".worktrees").mkdir()
    (main / ".worktrees" / "junk.txt").write_text("junk")
    (main / ".repo-control").mkdir()
    (main / ".repo-control" / "state.json").write_text("{}")
    git.ensure_excluded(worktree_path=main, patterns=["/.worktrees/", "/.repo-control/"])
    git.fetch(repo_path=main)
    assert git.fast_forward(repo_path=main, branch="main") is True
    assert sha(main, "HEAD") == sha(scratch, "HEAD")


def test_worktree_add_sidecar(repo: Path, tmp_path: Path):
    target = tmp_path / "wt"
    git.worktree_add_sidecar(
        repo_path=repo,
        target=target,
        real_branch="feat",
        sidecar_branch="claude/feat",
        start_point="main",
    )
    assert git.branch_exists(repo_path=repo, branch="feat") is True
    assert git.current_branch(worktree_path=target) == "claude/feat"
    assert sha(repo, "feat") == sha(repo, "main")
