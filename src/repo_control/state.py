from dataclasses import dataclass
from pathlib import Path

from repo_control import git

LEGACY_REPO_DIR_SUFFIX = "-control"
WORKTREES_SUBDIR = ".worktrees"


@dataclass(frozen=True)
class RepoDir:
    owner: str
    name: str
    path: Path

    @property
    def main_path(self) -> Path:
        return self.path / "main"

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"


def slugify_branch(*, branch: str) -> str:
    return branch.replace("/", "-").replace(" ", "-")


def worktree_dir_name(*, pr_number: int, branch: str) -> str:
    return f"{pr_number}-{slugify_branch(branch=branch)}"


def worktree_path(*, repo_path: Path, pr_number: int, branch: str, layout: str) -> Path:
    name = worktree_dir_name(pr_number=pr_number, branch=branch)
    if layout == "hierarchical":
        return repo_path / WORKTREES_SUBDIR / name
    return repo_path / name


def resolve_repo_dir(*, base_path: Path, owner: str, name: str) -> Path:
    """Prefer an existing legacy <name>-control dir; otherwise return <base>/<name>."""
    legacy = base_path / f"{name}{LEGACY_REPO_DIR_SUFFIX}"
    if legacy.exists():
        return legacy
    return base_path / name


def discover_repos(*, base_path: Path) -> list[RepoDir]:
    """Walk <base>/<*>/main and recover (owner, name) from each main's remote."""
    if not base_path.exists():
        return []
    out: list[RepoDir] = []
    for child in sorted(base_path.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        main = child / "main"
        if not main.exists():
            continue
        url = git.remote_url(repo_path=main)
        if url is None:
            continue
        parsed = git.parse_owner_repo(url=url)
        if parsed is None:
            continue
        owner, name = parsed
        out.append(RepoDir(owner=owner, name=name, path=child))
    return out


def existing_worktrees(*, repo: RepoDir) -> list[git.Worktree]:
    if not repo.main_path.exists():
        return []
    return git.list_worktrees(repo_path=repo.main_path)
