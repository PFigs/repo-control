from pathlib import Path

from conftest import commit, run

from repo_control import state


def _git_repo(path: Path, *, origin: str | None = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-b", "main"], path)
    run(["git", "config", "user.email", "test@example.com"], path)
    run(["git", "config", "user.name", "test"], path)
    commit(path, "c1")
    if origin is not None:
        run(["git", "remote", "add", "origin", origin], path)
    return path


def test_sidecar_name():
    assert state.sidecar_name(real="feat/x") == "claude/feat/x"


def test_real_from_sidecar_roundtrip():
    assert state.real_from_sidecar(sidecar="claude/feat/x") == "feat/x"


def test_real_from_sidecar_is_noop_on_plain_branch():
    assert state.real_from_sidecar(sidecar="main") == "main"


def test_is_sidecar():
    assert state.is_sidecar(branch="claude/x") is True
    assert state.is_sidecar(branch="x") is False


def test_ensure_main_path_existing_legacy_main_wins_over_hierarchical(tmp_path: Path):
    repo_path = tmp_path / "r"
    (repo_path / "main" / ".git").mkdir(parents=True)
    result = state.ensure_main_path(
        repo_path=repo_path, name="n", layout="hierarchical", prefix=True, bare=True
    )
    assert result == repo_path / "main"


def test_ensure_main_path_existing_prefixed_legacy_wins(tmp_path: Path):
    repo_path = tmp_path / "r"
    (repo_path / "n-main" / ".git").mkdir(parents=True)
    result = state.ensure_main_path(
        repo_path=repo_path, name="n", layout="hierarchical", prefix=False, bare=False
    )
    assert result == repo_path / "n-main"


def test_ensure_main_path_flat_fresh_unchanged(tmp_path: Path):
    repo_path = tmp_path / "r"
    repo_path.mkdir()
    for bare in (False, True):
        assert (
            state.ensure_main_path(
                repo_path=repo_path, name="n", layout="flat", prefix=True, bare=bare
            )
            == repo_path / "n-main"
        )
        assert (
            state.ensure_main_path(
                repo_path=repo_path, name="n", layout="flat", prefix=False, bare=bare
            )
            == repo_path / "main"
        )


def test_ensure_main_path_hierarchical_fresh_non_bare_is_repo_path(tmp_path: Path):
    repo_path = tmp_path / "r"
    repo_path.mkdir()
    for prefix in (True, False):
        assert (
            state.ensure_main_path(
                repo_path=repo_path, name="n", layout="hierarchical", prefix=prefix, bare=False
            )
            == repo_path
        )


def test_ensure_main_path_hierarchical_bare_fresh_under_worktrees(tmp_path: Path):
    repo_path = tmp_path / "r"
    repo_path.mkdir()
    assert (
        state.ensure_main_path(
            repo_path=repo_path, name="n", layout="hierarchical", prefix=True, bare=True
        )
        == repo_path / ".worktrees" / "n-main"
    )
    assert (
        state.ensure_main_path(
            repo_path=repo_path, name="n", layout="hierarchical", prefix=False, bare=True
        )
        == repo_path / ".worktrees" / "main"
    )


def test_ensure_main_path_existing_worktrees_main_wins_over_prefix(tmp_path: Path):
    repo_path = tmp_path / "r"
    (repo_path / ".worktrees" / "main" / ".git").mkdir(parents=True)
    result = state.ensure_main_path(
        repo_path=repo_path, name="n", layout="hierarchical", prefix=True, bare=True
    )
    assert result == repo_path / ".worktrees" / "main"


def test_ensure_main_path_existing_checkout_at_root_wins_over_flat(tmp_path: Path):
    repo_path = _git_repo(tmp_path / "r")
    result = state.ensure_main_path(
        repo_path=repo_path, name="n", layout="flat", prefix=True, bare=False
    )
    assert result == repo_path


def test_ensure_main_path_bare_gitdir_without_main_stays_under_worktrees(tmp_path: Path):
    repo_path = tmp_path / "r"
    repo_path.mkdir()
    run(["git", "init", "--bare", "-b", "main", str(repo_path / ".git")], tmp_path)
    result = state.ensure_main_path(
        repo_path=repo_path, name="n", layout="hierarchical", prefix=True, bare=True
    )
    assert result == repo_path / ".worktrees" / "n-main"


def test_ensure_main_path_ignores_content_named_main(tmp_path: Path):
    repo_path = _git_repo(tmp_path / "r")
    (repo_path / "main").mkdir()
    result = state.ensure_main_path(
        repo_path=repo_path, name="n", layout="hierarchical", prefix=True, bare=False
    )
    assert result == repo_path


def test_discover_repos_finds_checkout_at_root(tmp_path: Path):
    base = tmp_path / "base"
    repo_root = _git_repo(base / "n", origin="git@github.com:o/n.git")
    assert state.discover_repos(base_path=base) == [
        state.RepoDir(owner="o", name="n", path=repo_root, main_path=repo_root)
    ]


def test_discover_repos_checkout_at_root_recovers_owner_and_name(tmp_path: Path):
    base = tmp_path / "base"
    _git_repo(base / "n", origin="git@github.com:o/n.git")
    repos = state.discover_repos(base_path=base)
    assert [(repo.owner, repo.name, repo.slug) for repo in repos] == [("o", "n", "o/n")]


def test_discover_repos_finds_bare_repo_with_main_under_worktrees(tmp_path: Path):
    src = _git_repo(tmp_path / "src")
    base = tmp_path / "base"
    repo_root = base / "n"
    repo_root.mkdir(parents=True)
    run(["git", "clone", "--bare", str(src), str(repo_root / ".git")], tmp_path)
    run(["git", "config", "remote.origin.url", "git@github.com:o/n.git"], repo_root / ".git")
    main = repo_root / ".worktrees" / "n-main"
    run(["git", "worktree", "add", str(main), "main"], repo_root / ".git")
    assert state.discover_repos(base_path=base) == [
        state.RepoDir(owner="o", name="n", path=repo_root, main_path=main)
    ]


def test_discover_repos_survives_content_named_main(tmp_path: Path):
    base = tmp_path / "base"
    repo_root = _git_repo(base / "n", origin="git@github.com:o/n.git")
    (repo_root / "main").write_text("content")
    assert state.discover_repos(base_path=base) == [
        state.RepoDir(owner="o", name="n", path=repo_root, main_path=repo_root)
    ]


def test_discover_repos_finds_bare_main_in_control_dir(tmp_path: Path):
    src = _git_repo(tmp_path / "src")
    base = tmp_path / "base"
    repo_root = base / "N-control"
    repo_root.mkdir(parents=True)
    run(["git", "clone", "--bare", str(src), str(repo_root / ".git")], tmp_path)
    run(["git", "config", "remote.origin.url", "git@github.com:o/n.git"], repo_root / ".git")
    main = repo_root / ".worktrees" / "n-main"
    run(["git", "worktree", "add", str(main), "main"], repo_root / ".git")
    assert state.discover_repos(base_path=base) == [
        state.RepoDir(owner="o", name="n", path=repo_root, main_path=main)
    ]


def test_discover_repos_ignores_pr_worktree_ending_in_main(tmp_path: Path):
    base = tmp_path / "base"
    repo_root = _git_repo(base / "n", origin="git@github.com:o/n.git")
    run(["git", "worktree", "add", str(repo_root / ".worktrees" / "12-fix-main")], repo_root)
    assert state.discover_repos(base_path=base) == [
        state.RepoDir(owner="o", name="n", path=repo_root, main_path=repo_root)
    ]


def test_discover_repos_still_finds_legacy_main_subfolder(tmp_path: Path):
    base = tmp_path / "base"
    main = _git_repo(base / "n" / "main", origin="git@github.com:o/n.git")
    assert state.discover_repos(base_path=base) == [
        state.RepoDir(owner="o", name="n", path=base / "n", main_path=main)
    ]


def test_discover_repos_ignores_child_with_gitfile(tmp_path: Path):
    src = _git_repo(tmp_path / "src", origin="git@github.com:o/n.git")
    base = tmp_path / "base"
    base.mkdir()
    run(["git", "worktree", "add", "--detach", str(base / "wt")], src)
    assert state.discover_repos(base_path=base) == []
