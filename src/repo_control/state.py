from dataclasses import dataclass, field
from pathlib import Path

from repo_control import git

LEGACY_REPO_DIR_SUFFIX = "-control"
WORKTREES_SUBDIR = ".worktrees"
SIDECAR_PREFIX = "claude/"


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


def sidecar_name(*, real: str) -> str:
    """The sidecar branch a worktree checks out for real PR branch `real`."""
    return f"{SIDECAR_PREFIX}{real}"


def real_from_sidecar(*, sidecar: str) -> str:
    """The real PR branch behind a sidecar branch (no-op for non-sidecar names)."""
    return sidecar.removeprefix(SIDECAR_PREFIX)


def is_sidecar(*, branch: str) -> bool:
    return branch.startswith(SIDECAR_PREFIX)


def main_dir_name(*, name: str, prefix: bool) -> str:
    return f"{name.lower()}-main" if prefix else "main"


def worktree_dir_name(*, name: str, pr_number: int, branch: str, prefix: bool) -> str:
    suffix = f"{pr_number}-{slugify_branch(branch=branch)}"
    return f"{name.lower()}-{suffix}" if prefix else suffix


def worktree_path(
    *,
    repo_path: Path,
    name: str,
    pr_number: int,
    branch: str,
    layout: str,
    prefix: bool,
) -> Path:
    folder = worktree_dir_name(name=name, pr_number=pr_number, branch=branch, prefix=prefix)
    if layout == "hierarchical":
        return repo_path / WORKTREES_SUBDIR / folder
    return repo_path / folder


def acceptable_worktree_paths(
    *,
    repo_path: Path,
    name: str,
    pr_number: int,
    branch: str,
    layout: str,
) -> set[Path]:
    """Worktree folder names with or without the repo prefix are both accepted."""
    return {
        worktree_path(
            repo_path=repo_path,
            name=name,
            pr_number=pr_number,
            branch=branch,
            layout=layout,
            prefix=prefix,
        )
        for prefix in (True, False)
    }


def resolve_repo_dir(*, base_path: Path, owner: str, name: str) -> Path:
    """Prefer an existing legacy dir on disk; otherwise return the canonical lowercase path."""
    for candidate in (
        base_path / f"{name}{LEGACY_REPO_DIR_SUFFIX}",
        base_path / name,
    ):
        if candidate.exists():
            return candidate
    return base_path / name.lower()


def ensure_main_path(*, repo_path: Path, name: str, layout: str, prefix: bool, bare: bool) -> Path:
    """Return existing main checkout if a known layout matches; else the canonical new path."""
    for candidate in (
        repo_path / f"{name.lower()}-main",
        repo_path / f"{repo_path.name.lower()}-main",
        repo_path / "main",
        repo_path / WORKTREES_SUBDIR / f"{name.lower()}-main",
        repo_path / WORKTREES_SUBDIR / "main",
    ):
        if (candidate / ".git").exists():
            return candidate
    if (repo_path / ".git").is_dir() and not bare:
        return repo_path
    if layout == "hierarchical":
        if bare:
            return repo_path / WORKTREES_SUBDIR / main_dir_name(name=name, prefix=prefix)
        return repo_path
    return repo_path / main_dir_name(name=name, prefix=prefix)


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
    # Exact names only: PR worktrees (`<pr>-<slug>`) can end in "-main" too.
    names = {child.name.lower()}
    if (child / ".git").is_dir():
        url = git.remote_url(repo_path=child)
        parsed = git.parse_owner_repo(url=url) if url else None
        if parsed is not None:
            names.add(parsed[1].lower())
    for base in (child, child / WORKTREES_SUBDIR):
        for candidate in (*(base / f"{n}-main" for n in sorted(names)), base / "main"):
            if (candidate / ".git").exists():
                return candidate
    if (child / ".git").is_dir():
        return child
    return None


def existing_worktrees(*, repo: RepoDir) -> list[git.Worktree]:
    if not repo.main_path.exists():
        return []
    return git.list_worktrees(repo_path=repo.main_path)
