from dataclasses import dataclass, field
from pathlib import Path

from repo_control import git

LEGACY_REPO_DIR_SUFFIX = "-control"
WORKTREES_SUBDIR = ".worktrees"


@dataclass(frozen=True)
class RepoDir:
    owner: str
    name: str
    path: Path
    main_path: Path = field()

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"


def slugify_branch(*, branch: str) -> str:
    return branch.replace("/", "-").replace(" ", "-")


def main_dir_name(*, name: str) -> str:
    return f"{name.lower()}-main"


def worktree_dir_name(*, name: str, pr_number: int, branch: str) -> str:
    return f"{name.lower()}-{pr_number}-{slugify_branch(branch=branch)}"


def worktree_path(
    *, repo_path: Path, name: str, pr_number: int, branch: str, layout: str
) -> Path:
    folder = worktree_dir_name(name=name, pr_number=pr_number, branch=branch)
    if layout == "hierarchical":
        return repo_path / WORKTREES_SUBDIR / folder
    return repo_path / folder


def resolve_repo_dir(*, base_path: Path, owner: str, name: str) -> Path:
    """Prefer an existing legacy dir on disk; otherwise return the canonical lowercase path."""
    for candidate in (
        base_path / f"{name}{LEGACY_REPO_DIR_SUFFIX}",
        base_path / name,
    ):
        if candidate.exists():
            return candidate
    return base_path / name.lower()


def ensure_main_path(*, repo_path: Path, name: str) -> Path:
    """Return the existing main checkout if any layout matches; else the canonical new path."""
    for candidate in (
        repo_path / main_dir_name(name=name),
        repo_path / f"{repo_path.name.lower()}-main",
        repo_path / "main",
    ):
        if candidate.exists():
            return candidate
    return repo_path / main_dir_name(name=name)


def discover_repos(*, base_path: Path) -> list[RepoDir]:
    """Walk <base>/<*>/ dirs and recover (owner, name) from each main checkout's remote."""
    if not base_path.exists():
        return []
    out: list[RepoDir] = []
    for child in sorted(base_path.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        main = _find_main_in(child)
        if main is None:
            continue
        url = git.remote_url(repo_path=main)
        if url is None:
            continue
        parsed = git.parse_owner_repo(url=url)
        if parsed is None:
            continue
        owner, name = parsed
        out.append(RepoDir(owner=owner, name=name, path=child, main_path=main))
    return out


def _find_main_in(child: Path) -> Path | None:
    for candidate in (
        child / f"{child.name.lower()}-main",
        child / "main",
    ):
        if candidate.exists():
            return candidate
    return None


def existing_worktrees(*, repo: RepoDir) -> list[git.Worktree]:
    if not repo.main_path.exists():
        return []
    return git.list_worktrees(repo_path=repo.main_path)
