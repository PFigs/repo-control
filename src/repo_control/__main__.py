import argparse
import fcntl
import os
import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_control import config, gh, git, ide, picker, setup, state

SKILL_NAME = "repo-control"


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
        description="Mirror your open GitHub PRs as per-repo worktree folders under a base path.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sync_p = sub.add_parser("sync", help="Refresh worktrees from open PRs")
    sync_p.add_argument(
        "repo",
        nargs="?",
        default=None,
        help="Limit sync to one repo (owner/name or GitHub URL); default: all authored PRs",
    )
    sub.add_parser("list", help="Show all tracked worktrees")
    open_p = sub.add_parser("open", help="Open a PR's worktree in the IDE")
    open_p.add_argument("pr", help="PR number (or owner/repo#N for disambiguation)")
    open_p.add_argument(
        "--ide",
        default=None,
        help=f"Editor command ({', '.join(ide.KNOWN)}, or any binary on PATH; quote for args)",
    )
    clean_p = sub.add_parser("clean", help="Remove stale worktrees")
    clean_p.add_argument(
        "--force", action="store_true", help="Also drop dirty worktrees (with confirmation)"
    )
    sub.add_parser(
        "vacuum",
        help="Inspect dirty stale worktrees (PR closed but uncommitted) and drop selected ones",
    )
    sync_stack_p = sub.add_parser(
        "sync-stack",
        help="Reconcile sidecar worktrees and restack from <repo>-main (flock-guarded)",
    )
    sync_stack_p.add_argument(
        "repo",
        nargs="?",
        default=None,
        help="Limit to one repo (owner/name or GitHub URL); default: all mirrored repos",
    )
    install_p = sub.add_parser(
        "install-skill", help="Symlink the bundled Claude skill into ~/.claude/skills/"
    )
    install_p.add_argument("--uninstall", action="store_true", help="Remove the symlink")
    install_p.add_argument(
        "--force", action="store_true", help="Replace an existing non-symlink at the destination"
    )
    sub.add_parser("setup", help="Interactive first-run configuration (or re-configure later)")

    args = parser.parse_args()
    try:
        if args.cmd == "sync":
            return cmd_sync(repo_arg=args.repo)
        if args.cmd == "list":
            return cmd_list()
        if args.cmd == "open":
            return cmd_open(reference=args.pr, ide_override=args.ide)
        if args.cmd == "clean":
            return cmd_clean(force=args.force)
        if args.cmd == "vacuum":
            return cmd_vacuum()
        if args.cmd == "sync-stack":
            return cmd_sync_stack(repo_arg=args.repo)
        if args.cmd == "install-skill":
            return cmd_install_skill(uninstall=args.uninstall, force=args.force)
        if args.cmd == "setup":
            return cmd_setup()
    except (gh.GhError, git.GitError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def cmd_sync(*, repo_arg: str | None = None) -> int:
    gh.check_auth()
    if not config.exists():
        print("No config found; running first-run setup.\n")
        rc = cmd_setup()
        if rc != 0:
            return rc
        print()
    cfg = config.load()
    skip = set(cfg["skip_repos"])
    base = config.base_path(cfg=cfg)
    base.mkdir(parents=True, exist_ok=True)
    sidecar = cfg["sidecar_branches"]

    single_repo = _parse_repo_arg(value=repo_arg) if repo_arg else None
    if repo_arg and single_repo is None:
        raise ValueError(f"could not parse {repo_arg!r} as owner/name or GitHub URL")

    prs = gh.list_open_prs()
    by_repo: dict[tuple[str, str], dict[int, gh.OpenPR]] = {}
    for pr in prs:
        if pr.base_slug in skip:
            continue
        if single_repo is not None and (pr.base_owner, pr.base_repo) != single_repo:
            continue
        by_repo.setdefault((pr.base_owner, pr.base_repo), {})[pr.number] = pr

    selected_repos = _select_repos_interactive(by_repo=by_repo, single_repo=single_repo)
    if selected_repos is None:
        print("sync cancelled")
        return 0
    desired = {key: prs_by_num for key, prs_by_num in by_repo.items() if key in selected_repos}

    created: list[Path] = []
    refreshed: list[Path] = []
    removed: list[Path] = []
    kept_dirty: list[Path] = []
    setup_steps: dict[Path, list[str]] = {}
    synced_steps: dict[Path, list[str]] = {}

    for (owner, name), prs_by_num in sorted(desired.items()):
        repo_path = state.resolve_repo_dir(base_path=base, owner=owner, name=name)
        main_path = state.ensure_main_path(
            repo_path=repo_path, name=name, prefix=cfg["prefix_worktrees"]
        )
        if repo_path.exists() and main_path.exists():
            existing = git.remote_url(repo_path=main_path)
            existing_parsed = git.parse_owner_repo(url=existing) if existing else None
            if existing_parsed is not None and existing_parsed != (owner, name):
                print(
                    f"skipping {owner}/{name}: {repo_path} already mirrors "
                    f"{existing_parsed[0]}/{existing_parsed[1]} (name collision)"
                )
                continue
        if not main_path.exists():
            print(f"cloning {owner}/{name} ...")
            if cfg["bare_repo"]:
                git_dir = repo_path / ".git"
                if not git_dir.exists():
                    git.clone_bare(owner=owner, name=name, git_dir=git_dir)
                default = git.default_branch(repo_path=git_dir)
                git.worktree_add_tracking(
                    repo_path=git_dir,
                    target=main_path,
                    local_branch=default,
                    upstream=f"origin/{default}",
                )
            else:
                main_path.parent.mkdir(parents=True, exist_ok=True)
                git.clone(owner=owner, name=name, target=main_path)
        git.fetch(repo_path=main_path)
        default = git.default_branch(repo_path=main_path)
        git.fast_forward(repo_path=main_path, branch=default)
        setup.install_sync_stack_script(repo_path=repo_path, slug=f"{owner}/{name}")

        existing_by_branch = {
            wt.branch: wt.path
            for wt in git.list_worktrees(repo_path=main_path)
            if wt.branch is not None
        }

        for pr_number, pr in sorted(prs_by_num.items()):
            wt_path = state.worktree_path(
                repo_path=repo_path,
                name=name,
                pr_number=pr_number,
                branch=pr.head_branch,
                layout=cfg["worktree_layout"],
                prefix=cfg["prefix_worktrees"],
            )
            acceptable = {
                p.resolve()
                for p in state.acceptable_worktree_paths(
                    repo_path=repo_path,
                    name=name,
                    pr_number=pr_number,
                    branch=pr.head_branch,
                    layout=cfg["worktree_layout"],
                )
            }
            wt_path.parent.mkdir(parents=True, exist_ok=True)
            local_branch = f"pr-{pr_number}" if pr.is_fork else pr.head_branch
            wt_branch = state.sidecar_name(real=local_branch) if sidecar else local_branch
            existing_path = existing_by_branch.get(wt_branch) or existing_by_branch.get(
                local_branch
            )
            if existing_path is not None:
                existing_resolved = existing_path.resolve()
                if existing_resolved in acceptable:
                    wt_path = existing_path
                elif existing_resolved != wt_path.resolve():
                    if git.is_clean(worktree_path=existing_path):
                        git.worktree_move(
                            repo_path=main_path,
                            source=existing_path,
                            target=wt_path,
                        )
                        existing_by_branch[wt_branch] = wt_path
                    else:
                        print(
                            f"warning: {local_branch} at {existing_path} is dirty; "
                            f"refreshing in place instead of moving to {wt_path}"
                        )
                        wt_path = existing_path
            hook_ctx = {
                "owner": owner,
                "name": name,
                "pr_number": pr_number,
                "branch": local_branch,
            }
            if wt_path.exists():
                if sidecar and git.current_branch(worktree_path=wt_path) == local_branch:
                    git.switch_new_branch(worktree_path=wt_path, name=wt_branch)
                    git.set_upstream(repo_path=main_path, branch=wt_branch, upstream=local_branch)
                if pr.is_fork and pr.fork_clone_url:
                    git.fetch_fork(
                        repo_path=main_path,
                        fork_url=pr.fork_clone_url,
                        head_branch=pr.head_branch,
                        local_branch=local_branch,
                    )
                else:
                    git.fetch(repo_path=main_path, refspec=pr.head_branch)
                    if sidecar:
                        git.fast_forward_branch(
                            repo_path=main_path,
                            branch=local_branch,
                            to_ref=f"origin/{local_branch}",
                        )
                refreshed.append(wt_path)
                synced_steps[wt_path] = setup.run_post_sync(
                    repo_path=repo_path, worktree_path=wt_path, ctx=hook_ctx
                )
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
            if sidecar:
                git.worktree_add_sidecar(
                    repo_path=main_path,
                    target=wt_path,
                    real_branch=local_branch,
                    sidecar_branch=wt_branch,
                    start_point=local_branch if pr.is_fork else f"origin/{local_branch}",
                )
            else:
                git.worktree_add(repo_path=main_path, target=wt_path, branch=local_branch)
            created.append(wt_path)
            init_steps = setup.run_init(worktree_path=wt_path, cfg=cfg)
            post_create_steps = setup.run_post_create(
                repo_path=repo_path, worktree_path=wt_path, ctx=hook_ctx
            )
            post_sync_steps = setup.run_post_sync(
                repo_path=repo_path, worktree_path=wt_path, ctx=hook_ctx
            )
            setup_steps[wt_path] = init_steps + post_create_steps + post_sync_steps

    for repo in state.discover_repos(base_path=base):
        if (repo.owner, repo.name) not in selected_repos:
            continue
        wanted = desired.get((repo.owner, repo.name), {})
        wanted_paths: set[Path] = set()
        for pr in wanted.values():
            wanted_paths.update(
                state.acceptable_worktree_paths(
                    repo_path=repo.path,
                    name=repo.name,
                    pr_number=pr.number,
                    branch=pr.head_branch,
                    layout=cfg["worktree_layout"],
                )
            )
        wanted_paths.add(repo.main_path)
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
            branch = worktree.branch if worktree.branch != default else None
            _delete_worktree_branches(repo_path=repo.main_path, branch=branch)
            removed.append(wt_path)

    _print_sync_summary(
        created=created,
        refreshed=refreshed,
        removed=removed,
        kept_dirty=kept_dirty,
        setup_steps=setup_steps,
        synced_steps=synced_steps,
    )
    return 0


def cmd_sync_stack(*, repo_arg: str | None = None) -> int:
    cfg = config.load()
    base = config.base_path(cfg=cfg)
    single_repo = _parse_repo_arg(value=repo_arg) if repo_arg else None
    if repo_arg and single_repo is None:
        raise ValueError(f"could not parse {repo_arg!r} as owner/name or GitHub URL")
    repos = [
        repo
        for repo in state.discover_repos(base_path=base)
        if single_repo is None or (repo.owner, repo.name) == single_repo
    ]
    if not repos:
        print("no mirrored repos found — run `repo-control sync` first")
        return 0
    for repo in repos:
        print(f"{repo.slug}:")
        handle = _acquire_lock(path=setup.sync_stack_lock_path(repo_path=repo.path))
        if handle is None:
            print(f"  another session is syncing {repo.slug}; skipped")
            continue
        try:
            for line in _sync_stack_repo(repo=repo):
                print(line)
        finally:
            _release_lock(handle=handle)
    return 0


def _acquire_lock(*, path: Path):
    """Take a non-blocking exclusive flock. Returns the open handle, or None if held."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def _release_lock(*, handle) -> None:
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    handle.close()


def _sync_stack_repo(*, repo: state.RepoDir) -> list[str]:
    """Reconcile sidecar worktrees and restack one repo from its main checkout.

    Outbound: fast-forward each real branch up to its sidecar's committed HEAD.
    Restack: `gt sync` (graphite repos) or fetch + fast-forward trunk (plain repos).
    Inbound: rebase each clean sidecar onto its restacked real branch.
    """
    main = repo.main_path
    default = git.default_branch(repo_path=main)
    sidecars = [
        wt
        for wt in git.list_worktrees(repo_path=main)
        if wt.branch is not None
        and wt.path.resolve() != main.resolve()
        and state.is_sidecar(branch=wt.branch)
    ]
    notes: list[str] = []

    for wt in sidecars:
        real = state.real_from_sidecar(sidecar=wt.branch)
        if not git.branch_exists(repo_path=main, branch=real):
            continue
        if git.fast_forward_branch(repo_path=main, branch=real, to_ref=wt.branch):
            notes.append(f"  outbound: {real} fast-forwarded to {wt.branch}")
        elif not git.is_ancestor(repo_path=main, ancestor=real, descendant=wt.branch):
            notes.append(f"  ! {real} has diverged from {wt.branch}; reconcile by hand")

    if git.has_graphite(repo_path=main):
        ok = git.gt_sync(repo_path=main)
        notes.append("  restack: gt sync" if ok else "  ! gt sync failed")
    else:
        git.fetch(repo_path=main)
        git.fast_forward(repo_path=main, branch=default)
        notes.append(f"  restack: fetched, fast-forwarded {default} (no graphite)")

    for wt in sidecars:
        real = state.real_from_sidecar(sidecar=wt.branch)
        if not git.branch_exists(repo_path=main, branch=real):
            notes.append(f"  inbound: {wt.branch} skipped ({real} gone — merged?)")
            continue
        if not git.is_clean(worktree_path=wt.path):
            notes.append(f"  inbound: {wt.branch} skipped (worktree dirty)")
            continue
        if git.rebase(worktree_path=wt.path, onto=real):
            notes.append(f"  inbound: {wt.branch} rebased onto {real}")
        else:
            notes.append(f"  ! {wt.branch} rebase onto {real} conflicted; left untouched")

    if not sidecars:
        notes.append("  no sidecar worktrees")
    return notes


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


def _delete_worktree_branches(*, repo_path: Path, branch: str | None) -> None:
    """Delete a removed worktree's branch, plus the real branch if it was a sidecar.

    Callers pass `None` for a worktree whose branch is the repo's default.
    """
    if not branch:
        return
    git.delete_branch(repo_path=repo_path, branch=branch)
    real = state.real_from_sidecar(sidecar=branch)
    if real != branch:
        git.delete_branch(repo_path=repo_path, branch=real)


def cmd_clean(*, force: bool) -> int:
    gh.check_auth()
    cfg = config.load()
    base = config.base_path(cfg=cfg)
    prs = gh.list_open_prs()
    wanted_by_repo: dict[tuple[str, str], set[Path]] = {}
    for pr in prs:
        key = (pr.base_owner, pr.base_repo)
        repo_path = state.resolve_repo_dir(base_path=base, owner=pr.base_owner, name=pr.base_repo)
        bucket = wanted_by_repo.setdefault(key, set())
        for variant in state.acceptable_worktree_paths(
            repo_path=repo_path,
            name=pr.base_repo,
            pr_number=pr.number,
            branch=pr.head_branch,
            layout=cfg["worktree_layout"],
        ):
            bucket.add(variant.resolve())

    stale_clean: list[tuple[Path, Path, str | None]] = []
    stale_dirty: list[tuple[Path, Path]] = []  # (main_path, wt_path)
    for repo in state.discover_repos(base_path=base):
        wanted = wanted_by_repo.get((repo.owner, repo.name), set())
        default = git.default_branch(repo_path=repo.main_path)
        for worktree in state.existing_worktrees(repo=repo):
            wt_path = worktree.path.resolve()
            if wt_path == repo.main_path.resolve():
                continue
            if wt_path in wanted:
                continue
            if git.is_clean(worktree_path=wt_path):
                stale_clean.append(
                    (
                        repo.main_path,
                        wt_path,
                        worktree.branch if worktree.branch != default else None,
                    )
                )
            else:
                stale_dirty.append((repo.main_path, wt_path))

    for main_path, wt_path, branch in stale_clean:
        git.worktree_remove(repo_path=main_path, target=wt_path)
        _delete_worktree_branches(repo_path=main_path, branch=branch)
        print(f"removed {wt_path}")

    if not stale_dirty:
        return 0
    if not force:
        print(f"\n{len(stale_dirty)} dirty stale worktree(s) preserved:")
        for _, path in stale_dirty:
            print(f"  {path}")
        print("re-run with --force to drop them anyway")
        return 0
    print(f"\nabout to remove {len(stale_dirty)} dirty worktree(s):")
    for _, path in stale_dirty:
        print(f"  {path}")
    answer = input("type 'yes' to confirm: ").strip().lower()
    if answer != "yes":
        print("aborted")
        return 1
    for main_path, wt_path in stale_dirty:
        git.worktree_remove(repo_path=main_path, target=wt_path)
        print(f"removed {wt_path}")
    return 0


def cmd_vacuum() -> int:
    gh.check_auth()
    cfg = config.load()
    base = config.base_path(cfg=cfg)
    prs = gh.list_open_prs()
    wanted_by_repo: dict[tuple[str, str], set[Path]] = {}
    for pr in prs:
        repo_path = state.resolve_repo_dir(base_path=base, owner=pr.base_owner, name=pr.base_repo)
        bucket = wanted_by_repo.setdefault((pr.base_owner, pr.base_repo), set())
        for variant in state.acceptable_worktree_paths(
            repo_path=repo_path,
            name=pr.base_repo,
            pr_number=pr.number,
            branch=pr.head_branch,
            layout=cfg["worktree_layout"],
        ):
            bucket.add(variant.resolve())

    targets: list[tuple[Path, Path, str | None, git.DirtySummary]] = []
    for repo in state.discover_repos(base_path=base):
        wanted = wanted_by_repo.get((repo.owner, repo.name), set())
        default = git.default_branch(repo_path=repo.main_path)
        for worktree in state.existing_worktrees(repo=repo):
            wt_path = worktree.path.resolve()
            if wt_path == repo.main_path.resolve():
                continue
            if wt_path in wanted:
                continue
            if git.is_clean(worktree_path=wt_path):
                continue
            summary = git.dirty_summary(worktree_path=wt_path)
            branch = worktree.branch if worktree.branch != default else None
            targets.append((repo.main_path, wt_path, branch, summary))

    if not targets:
        print("no dirty stale worktrees — nothing to vacuum")
        return 0

    print(f"{len(targets)} dirty stale worktree(s):\n")
    for _, wt_path, branch, summary in targets:
        _print_dirty_inspection(path=wt_path, branch=branch, summary=summary)
        print()

    by_key = {
        str(wt_path): (main_path, wt_path, branch) for main_path, wt_path, branch, _ in targets
    }
    choices = [
        picker.Choice(
            key=str(wt_path),
            label=_vacuum_label(path=wt_path, branch=branch, summary=summary),
        )
        for _, wt_path, branch, summary in targets
    ]
    chosen = picker.select_multi(
        title="Worktrees to delete (destructive):",
        choices=choices,
        default_selected=False,
    )
    if chosen is None:
        print("vacuum cancelled")
        return 0
    if not chosen:
        print("nothing selected")
        return 0

    for key in chosen:
        main_path, wt_path, branch = by_key[key]
        git.worktree_remove(repo_path=main_path, target=wt_path, force=True)
        _delete_worktree_branches(repo_path=main_path, branch=branch)
        print(f"removed {wt_path}")
    return 0


def _vacuum_label(*, path: Path, branch: str | None, summary: git.DirtySummary) -> str:
    bits = []
    if summary.modified:
        bits.append(f"M:{summary.modified}")
    if summary.added:
        bits.append(f"A:{summary.added}")
    if summary.deleted:
        bits.append(f"D:{summary.deleted}")
    if summary.untracked:
        bits.append(f"?:{summary.untracked}")
    if summary.ahead:
        bits.append(f"ahead:{summary.ahead}")
    if summary.unmerged:
        bits.append(f"unmerged:{summary.unmerged}")
    if summary.stashes:
        bits.append(f"stash:{summary.stashes}")
    counts = " ".join(bits) if bits else "clean?"
    branch_str = branch or "-"
    return f"{path}  [{branch_str}]  {counts}"


def _print_dirty_inspection(*, path: Path, branch: str | None, summary: git.DirtySummary) -> None:
    branch_str = branch or "(detached)"
    print(f"  {path}")
    print(f"    branch: {branch_str}")
    counts = (
        f"M:{summary.modified} A:{summary.added} D:{summary.deleted} "
        f"?:{summary.untracked} ahead:{summary.ahead} "
        f"unmerged:{summary.unmerged} stash:{summary.stashes}"
    )
    print(f"    {counts}")
    snippet = summary.porcelain[:10]
    for line in snippet:
        print(f"      {line}")
    remaining = len(summary.porcelain) - len(snippet)
    if remaining > 0:
        print(f"      ... and {remaining} more")


def _select_repos_interactive(
    *,
    by_repo: dict[tuple[str, str], dict[int, gh.OpenPR]],
    single_repo: tuple[str, str] | None,
) -> set[tuple[str, str]] | None:
    """Show a picker when there's a real choice; otherwise return everything in by_repo."""
    all_keys = set(by_repo.keys())
    if single_repo is not None or len(by_repo) <= 1 or not sys.stdin.isatty():
        return all_keys
    choices = [
        picker.Choice(key=f"{owner}/{name}", label=f"{owner}/{name} ({len(prs)} PRs)")
        for (owner, name), prs in sorted(by_repo.items())
    ]
    chosen_keys = picker.select_multi(
        title="Repos to sync:", choices=choices, default_selected=True
    )
    if chosen_keys is None:
        return None
    chosen_set = set(chosen_keys)
    return {(owner, name) for owner, name in by_repo if f"{owner}/{name}" in chosen_set}


def _parse_repo_arg(*, value: str) -> tuple[str, str] | None:
    candidate = value.strip()
    parsed = git.parse_owner_repo(url=candidate)
    if parsed is not None:
        return parsed
    cleaned = candidate.removesuffix(".git").strip("/")
    parts = cleaned.split("/")
    if len(parts) == 2 and all(parts):
        return parts[0], parts[1]
    return None


def _prompt(*, label: str, default: str) -> str:
    try:
        raw = input(f"{label} [{default}]: ").strip()
    except EOFError:
        return default
    return raw or default


def _prompt_bool(*, label: str, default: bool) -> bool:
    suffix = "Y/n" if default else "y/N"
    try:
        raw = input(f"{label} [{suffix}]: ").strip().lower()
    except EOFError:
        return default
    if not raw:
        return default
    return raw in {"y", "yes", "true", "1"}


def cmd_setup() -> int:
    cfg = config.load()
    print(f"Writing config to {config.config_path()}\n")

    print(
        "Workspace path: each open PR you author becomes a worktree under "
        "<workspace>/<repo>-control/<pr>-<branch>/, alongside <repo>-control/main/.\n"
        "Tip: ~/repos is a fine pick if you want everything in your home."
    )
    base = os.path.expanduser(
        _prompt(
            label="Workspace path",
            default=cfg["base_path"],
        )
    )

    ide_choice = _prompt(
        label=f"Default editor ({', '.join(ide.KNOWN)}, or any binary on PATH; quote for args)",
        default=cfg["ide"],
    )
    binary = shlex.split(ide_choice)[0] if ide_choice else ""
    if binary and shutil.which(binary) is None:
        print(f"  warning: {binary!r} not on PATH — saving anyway; install or fix before `open`")

    skip_raw = _prompt(
        label="Repos to skip (comma-separated owner/repo)",
        default=", ".join(cfg["skip_repos"]),
    )
    skip_repos = [item.strip() for item in skip_raw.split(",") if item.strip()]

    auto_install = _prompt_bool(
        label="Auto-run installers (mise install / uv sync / npm install) in fresh worktrees?",
        default=cfg["auto_install"],
    )
    auto_trust_mise = False
    if auto_install:
        auto_trust_mise = _prompt_bool(
            label="Auto-trust mise.toml in fresh worktrees (skips mise's trust prompt)?",
            default=cfg["auto_trust_mise"],
        )

    layout_choice = (
        _prompt(
            label=(
                "Worktree layout (hierarchical: <repo>/.worktrees/<pr>-<branch>; "
                "flat: <repo>/<pr>-<branch>)"
            ),
            default=cfg["worktree_layout"],
        )
        .strip()
        .lower()
    )
    if layout_choice not in {"hierarchical", "flat"}:
        print(f"  unknown layout {layout_choice!r}; using 'flat'")
        layout_choice = "flat"

    prefix_worktrees = _prompt_bool(
        label=(
            "Prefix worktree folders with the lowercase repo name "
            "(e.g. webapp-main, webapp-142-fix)?"
        ),
        default=cfg["prefix_worktrees"],
    )

    bare_repo = _prompt_bool(
        label="Store .git as a bare repo at <repo>/.git and treat main as a worktree?",
        default=cfg["bare_repo"],
    )

    sidecar_branches = _prompt_bool(
        label=(
            "Check out PR worktrees on a sidecar branch (claude/<branch>) so the real "
            "branch stays free for `gt sync` in <repo>-main?"
        ),
        default=cfg["sidecar_branches"],
    )

    Path(base).mkdir(parents=True, exist_ok=True)
    written = config.write(
        base_path=base,
        ide=ide_choice,
        skip_repos=skip_repos,
        auto_install=auto_install,
        auto_trust_mise=auto_trust_mise,
        worktree_layout=layout_choice,
        prefix_worktrees=prefix_worktrees,
        bare_repo=bare_repo,
        sidecar_branches=sidecar_branches,
    )
    print(f"\nWrote {written}")
    return 0


def cmd_install_skill(*, uninstall: bool, force: bool) -> int:
    source = _bundled_skill_source()
    target = Path.home() / ".claude" / "skills" / SKILL_NAME

    if uninstall:
        if not target.exists() and not target.is_symlink():
            print(f"{target} does not exist; nothing to remove")
            return 0
        if target.is_symlink():
            target.unlink()
            print(f"unlinked {target}")
            return 0
        if not force:
            print(
                f"refusing to remove {target}: not a symlink. "
                "Inspect manually or re-run with --force.",
                file=sys.stderr,
            )
            return 1
        if target.is_dir():
            _rmtree(target)
        else:
            target.unlink()
        print(f"removed {target}")
        return 0

    if not source.exists():
        print(
            f"bundled skill source not found at {source}; is this an editable install?",
            file=sys.stderr,
        )
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        if target.resolve() == source.resolve():
            print(f"{target} -> {source} already in place")
            return 0
        target.unlink()
    elif target.exists():
        if not force:
            print(
                f"refusing to overwrite {target}: not a symlink. "
                "Back it up and re-run with --force.",
                file=sys.stderr,
            )
            return 1
        if target.is_dir():
            _rmtree(target)
        else:
            target.unlink()

    target.symlink_to(source, target_is_directory=True)
    print(f"linked {target} -> {source}")
    return 0


def _rmtree(path: Path) -> None:
    import shutil

    shutil.rmtree(path)


def _bundled_skill_source() -> Path:
    return Path(__file__).resolve().parent / "skill"


def _collect_rows() -> list[WorktreeRow]:
    rows: list[WorktreeRow] = []
    cfg = config.load()
    base = config.base_path(cfg=cfg)
    for repo in state.discover_repos(base_path=base):
        default = git.default_branch(repo_path=repo.main_path)
        for worktree in state.existing_worktrees(repo=repo):
            wt_path = worktree.path
            if wt_path.resolve() == repo.main_path.resolve():
                rows.append(
                    WorktreeRow(
                        repo_slug=repo.slug,
                        pr_number=None,
                        branch=default,
                        path=wt_path,
                        status="main",
                    )
                )
                continue
            pr_number = _pr_number_from_dir(name=wt_path.name, repo_name=repo.name)
            status = "clean" if git.is_clean(worktree_path=wt_path) else "dirty"
            branch = (
                state.real_from_sidecar(sidecar=worktree.branch)
                if worktree.branch is not None
                else None
            )
            rows.append(
                WorktreeRow(
                    repo_slug=repo.slug,
                    pr_number=pr_number,
                    branch=branch,
                    path=wt_path,
                    status=status,
                )
            )
    return rows


def _pr_number_from_dir(*, name: str, repo_name: str) -> int | None:
    stripped = name
    prefix = f"{repo_name.lower()}-"
    if stripped.startswith(prefix):
        stripped = stripped[len(prefix) :]
    head, _, _ = stripped.partition("-")
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
    synced_steps: dict[Path, list[str]],
) -> None:
    print()
    print(f"created:  {len(created)}")
    for path in created:
        steps = setup_steps.get(path, [])
        suffix = f" [{', '.join(steps)}]" if steps else ""
        print(f"  + {path}{suffix}")
    print(f"refreshed: {len(refreshed)}")
    for path in refreshed:
        steps = synced_steps.get(path, [])
        suffix = f" [{', '.join(steps)}]" if steps else ""
        print(f"  ~ {path}{suffix}")
    print(f"removed:  {len(removed)}")
    for path in removed:
        print(f"  - {path}")
    if kept_dirty:
        print(f"kept dirty: {len(kept_dirty)} (PR closed but worktree has uncommitted work)")
        for path in kept_dirty:
            print(f"  ! {path}")
        print("  run `repo-control vacuum` to inspect and drop them")


if __name__ == "__main__":
    sys.exit(main())
