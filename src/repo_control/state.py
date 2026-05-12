from dataclasses import dataclass
from pathlib import Path

from repo_control import git

REPO_DIR_SUFFIX = "-control"


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


def repo_dir_name(*, name: str) -> str:
    return f"{name}{REPO_DIR_SUFFIX}"


def worktree_dir_name(*, pr_number: int, branch: str) -> str:
    return f"{pr_number}-{slugify_branch(branch=branch)}"


def resolve_repo_dir(*, base_path: Path, owner: str, name: str) -> Path:
    return base_path / repo_dir_name(name=name)


def discover_repos(*, base_path: Path) -> list[RepoDir]:
    """Walk <base>/*-control/ dirs and recover (owner, name) from each main/'s remote."""
    if not base_path.exists():
        return []
    out: list[RepoDir] = []
    for child in sorted(base_path.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if not child.name.endswith(REPO_DIR_SUFFIX):
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
