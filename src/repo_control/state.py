from dataclasses import dataclass
from pathlib import Path

from repo_control import git


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


def repo_dir_name(*, owner: str, name: str) -> str:
    return f"{owner}__{name}"


def parse_repo_dir(*, name: str) -> tuple[str, str] | None:
    if "__" not in name:
        return None
    owner, repo = name.split("__", 1)
    if not owner or not repo:
        return None
    return owner, repo


def worktree_dir_name(*, pr_number: int, branch: str) -> str:
    return f"{pr_number}-{slugify_branch(branch=branch)}"


def list_repo_dirs(*, root: Path) -> list[RepoDir]:
    if not root.exists():
        return []
    out: list[RepoDir] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        parsed = parse_repo_dir(name=child.name)
        if parsed is None:
            continue
        owner, name = parsed
        out.append(RepoDir(owner=owner, name=name, path=child))
    return out


def existing_worktrees(*, repo: RepoDir) -> list[git.Worktree]:
    if not repo.main_path.exists():
        return []
    return git.list_worktrees(repo_path=repo.main_path)
