from pathlib import Path

from conftest import commit, run, sha

from repo_control import git


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
