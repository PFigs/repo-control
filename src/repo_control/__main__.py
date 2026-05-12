import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_control import config, gh, git, ide, setup, state


@dataclass(frozen=True)
class WorktreeRow:
    repo_slug: str
    pr_number: int | None
    branch: str | None
    path: Path
    status: str


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="repo-control",
        description="Mirror your open GitHub PRs as worktrees under ~/workspace/repo-control/.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync", help="Refresh worktrees from open PRs")
    sub.add_parser("list", help="Show all tracked worktrees")
    open_p = sub.add_parser("open", help="Open a PR's worktree in the IDE")
    open_p.add_argument("pr", help="PR number (or owner/repo#N for disambiguation)")
    open_p.add_argument("--ide", choices=sorted(ide.COMMANDS), default=None)
    clean_p = sub.add_parser("clean", help="Remove stale worktrees")
    clean_p.add_argument("--force", action="store_true", help="Also drop dirty worktrees (with confirmation)")

    args = parser.parse_args()
    try:
        if args.cmd == "sync":
            return cmd_sync()
        if args.cmd == "list":
            return cmd_list()
        if args.cmd == "open":
            return cmd_open(reference=args.pr, ide_override=args.ide)
        if args.cmd == "clean":
            return cmd_clean(force=args.force)
    except (gh.GhError, git.GitError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def cmd_sync() -> int:
    gh.check_auth()
    config.ensure_default_file()
    cfg = config.load()
    skip = set(cfg["skip_repos"])
    root = config.root()
    root.mkdir(parents=True, exist_ok=True)

    prs = gh.list_open_prs()
    desired: dict[tuple[str, str], dict[int, gh.OpenPR]] = {}
    for pr in prs:
        if pr.base_slug in skip:
            continue
        desired.setdefault((pr.base_owner, pr.base_repo), {})[pr.number] = pr

    created: list[Path] = []
    refreshed: list[Path] = []
    removed: list[Path] = []
    kept_dirty: list[Path] = []
    setup_steps: dict[Path, list[str]] = {}

    for (owner, name), prs_by_num in sorted(desired.items()):
        repo_path = root / state.repo_dir_name(owner=owner, name=name)
        main_path = repo_path / "main"
        if not main_path.exists():
            print(f"cloning {owner}/{name} ...")
            git.clone(owner=owner, name=name, target=main_path)
        git.fetch(repo_path=main_path)
        default = git.default_branch(repo_path=main_path)
        git.fast_forward(repo_path=main_path, branch=default)

        for pr_number, pr in sorted(prs_by_num.items()):
            wt_name = state.worktree_dir_name(pr_number=pr_number, branch=pr.head_branch)
            wt_path = repo_path / wt_name
            local_branch = f"pr-{pr_number}" if pr.is_fork else pr.head_branch
            if wt_path.exists():
                if pr.is_fork and pr.fork_clone_url:
                    git.fetch_fork(
                        repo_path=main_path,
                        fork_url=pr.fork_clone_url,
                        head_branch=pr.head_branch,
                        local_branch=local_branch,
                    )
                else:
                    git.fetch(repo_path=main_path, refspec=pr.head_branch)
                refreshed.append(wt_path)
                continue
            if pr.is_fork and pr.fork_clone_url:
                git.fetch_fork(
                    repo_path=main_path,
                    fork_url=pr.fork_clone_url,
                    head_branch=pr.head_branch,
                    local_branch=local_branch,
                )
            else:
                git.fetch(repo_path=main_path, refspec=pr.head_branch)
            git.worktree_add(repo_path=main_path, target=wt_path, branch=local_branch)
            created.append(wt_path)
            setup_steps[wt_path] = setup.run_init(worktree_path=wt_path)

    for repo in state.list_repo_dirs(root=root):
        wanted = desired.get((repo.owner, repo.name), {})
        wanted_paths = {repo.path / state.worktree_dir_name(pr_number=pr.number, branch=pr.head_branch) for pr in wanted.values()}
        wanted_paths.add(repo.main_path)
        if not repo.main_path.exists():
            continue
        default = git.default_branch(repo_path=repo.main_path)
        for worktree in state.existing_worktrees(repo=repo):
            wt_path = worktree.path.resolve()
            if wt_path == repo.main_path.resolve():
                continue
            if wt_path in {p.resolve() for p in wanted_paths}:
                continue
            if not git.is_clean(worktree_path=wt_path):
                kept_dirty.append(wt_path)
                continue
            git.worktree_remove(repo_path=repo.main_path, target=wt_path)
            if worktree.branch and worktree.branch != default:
                git.delete_branch(repo_path=repo.main_path, branch=worktree.branch)
            removed.append(wt_path)

    _print_sync_summary(
        created=created,
        refreshed=refreshed,
        removed=removed,
        kept_dirty=kept_dirty,
        setup_steps=setup_steps,
    )
    return 0


def cmd_list() -> int:
    rows = _collect_rows()
    if not rows:
        print("no worktrees tracked yet — run `repo-control sync`")
        return 0
    _print_table(rows=rows)
    return 0


def cmd_open(*, reference: str, ide_override: str | None) -> int:
    cfg = config.load()
    chosen = ide_override or cfg["ide"]
    path = _resolve_pr(reference=reference)
    if path is None:
        print(f"no worktree found for {reference!r}", file=sys.stderr)
        return 1
    ide.launch(ide=chosen, path=path)
    print(f"launching {chosen} on {path}")
    return 0


def cmd_clean(*, force: bool) -> int:
    gh.check_auth()
    prs = gh.list_open_prs()
    wanted_by_repo: dict[tuple[str, str], set[Path]] = {}
    root = config.root()
    for pr in prs:
        key = (pr.base_owner, pr.base_repo)
        repo_path = root / state.repo_dir_name(owner=pr.base_owner, name=pr.base_repo)
        wt = repo_path / state.worktree_dir_name(pr_number=pr.number, branch=pr.head_branch)
        wanted_by_repo.setdefault(key, set()).add(wt.resolve())

    stale_clean: list[tuple[Path, Path, str | None]] = []  # (main_path, wt_path, branch)
    stale_dirty: list[Path] = []
    for repo in state.list_repo_dirs(root=root):
        if not repo.main_path.exists():
            continue
        wanted = wanted_by_repo.get((repo.owner, repo.name), set())
        default = git.default_branch(repo_path=repo.main_path)
        for worktree in state.existing_worktrees(repo=repo):
            wt_path = worktree.path.resolve()
            if wt_path == repo.main_path.resolve():
                continue
            if wt_path in wanted:
                continue
            if git.is_clean(worktree_path=wt_path):
                stale_clean.append((repo.main_path, wt_path, worktree.branch if worktree.branch != default else None))
            else:
                stale_dirty.append(wt_path)

    for main_path, wt_path, branch in stale_clean:
        git.worktree_remove(repo_path=main_path, target=wt_path)
        if branch:
            git.delete_branch(repo_path=main_path, branch=branch)
        print(f"removed {wt_path}")

    if not stale_dirty:
        return 0
    if not force:
        print(f"\n{len(stale_dirty)} dirty stale worktree(s) preserved:")
        for path in stale_dirty:
            print(f"  {path}")
        print("re-run with --force to drop them anyway")
        return 0
    print(f"\nabout to remove {len(stale_dirty)} dirty worktree(s):")
    for path in stale_dirty:
        print(f"  {path}")
    answer = input("type 'yes' to confirm: ").strip().lower()
    if answer != "yes":
        print("aborted")
        return 1
    for wt_path in stale_dirty:
        repo_main = wt_path.parent / "main"
        git.worktree_remove(repo_path=repo_main, target=wt_path)
        print(f"removed {wt_path}")
    return 0


def _collect_rows() -> list[WorktreeRow]:
    rows: list[WorktreeRow] = []
    root = config.root()
    for repo in state.list_repo_dirs(root=root):
        if not repo.main_path.exists():
            continue
        default = git.default_branch(repo_path=repo.main_path)
        for worktree in state.existing_worktrees(repo=repo):
            wt_path = worktree.path
            if wt_path.resolve() == repo.main_path.resolve():
                rows.append(WorktreeRow(
                    repo_slug=repo.slug,
                    pr_number=None,
                    branch=default,
                    path=wt_path,
                    status="main",
                ))
                continue
            pr_number = _pr_number_from_dir(name=wt_path.name)
            status = "clean" if git.is_clean(worktree_path=wt_path) else "dirty"
            rows.append(WorktreeRow(
                repo_slug=repo.slug,
                pr_number=pr_number,
                branch=worktree.branch,
                path=wt_path,
                status=status,
            ))
    return rows


def _pr_number_from_dir(*, name: str) -> int | None:
    head, _, _ = name.partition("-")
    if head.isdigit():
        return int(head)
    return None


def _resolve_pr(*, reference: str) -> Path | None:
    rows = _collect_rows()
    if "#" in reference:
        slug, _, num = reference.partition("#")
        target = int(num)
        for row in rows:
            if row.repo_slug == slug and row.pr_number == target:
                return row.path
        return None
    if not reference.isdigit():
        return None
    target = int(reference)
    matches = [row for row in rows if row.pr_number == target]
    if len(matches) == 0:
        return None
    if len(matches) > 1:
        print("ambiguous PR number; matches:", file=sys.stderr)
        for row in matches:
            print(f"  {row.repo_slug}#{row.pr_number}  {row.path}", file=sys.stderr)
        return None
    return matches[0].path


def _print_table(*, rows: list[WorktreeRow]) -> None:
    headers = ("repo", "pr", "branch", "status", "path")
    data = [
        (
            row.repo_slug,
            str(row.pr_number) if row.pr_number is not None else "-",
            row.branch or "-",
            row.status,
            str(row.path),
        )
        for row in rows
    ]
    widths = [len(h) for h in headers]
    for record in data:
        for i, cell in enumerate(record):
            widths[i] = max(widths[i], len(cell))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in widths]))
    for record in data:
        print(fmt.format(*record))


def _print_sync_summary(
    *,
    created: list[Path],
    refreshed: list[Path],
    removed: list[Path],
    kept_dirty: list[Path],
    setup_steps: dict[Path, list[str]],
) -> None:
    print()
    print(f"created:  {len(created)}")
    for path in created:
        steps = setup_steps.get(path, [])
        suffix = f" [{', '.join(steps)}]" if steps else ""
        print(f"  + {path}{suffix}")
    print(f"refreshed: {len(refreshed)}")
    for path in refreshed:
        print(f"  ~ {path}")
    print(f"removed:  {len(removed)}")
    for path in removed:
        print(f"  - {path}")
    if kept_dirty:
        print(f"kept dirty: {len(kept_dirty)} (PR closed but worktree has uncommitted work)")
        for path in kept_dirty:
            print(f"  ! {path}")


if __name__ == "__main__":
    sys.exit(main())
