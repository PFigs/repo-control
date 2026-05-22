---
name: repo-control
description: Use when the user says "sync my PRs", "sync repo-control", "refresh my worktrees", "open PR <n>", "sync the stack", "restack from main", "gt sync safely", "what am I working on", or otherwise wants to inspect, refresh, or restack the local per-repo worktree mirrors created by the `repo-control` CLI. Wraps the `repo-control` command.
allowed-tools: Bash
---

# repo-control

For every open PR the user has authored on GitHub, the `repo-control` CLI scaffolds a per-repo folder under one configurable base path (default `~/.local/share/repo-control/`, XDG_DATA_HOME). Each folder holds the repo's `main/` worktree plus one worktree per open PR.

```
<base_path>/
  webapp/                        # flat layout (default)
    webapp-main/                 # real PR branches live here, un-checked-out
    webapp-142-fix-navbar/       # checked out on sidecar claude/142-fix-navbar
    webapp-141-add-dark-mode/    # checked out on sidecar claude/141-add-dark-mode
    .repo-control/               # per-repo hooks + the sync-stack shim + lock
  cli-tool/                      # hierarchical layout
    cli-tool-main/
    .worktrees/
      cli-tool-37-bump-python-to-312/
```

Every worktree folder is prefixed with the repo name (lowercased). The repo dir itself is also lowercased on new clones. Pre-existing `<repo>-control/` or `<repo>/main/` layouts from older versions are reused in place.

Configuration lives at `~/.config/repo-control/config.toml` (XDG_CONFIG_HOME). Created interactively by `repo-control setup` or on first `sync`.

```toml
base_path = "/home/<user>/.local/share/repo-control"
ide = "idea"                       # any binary on PATH; suggestions: idea, code, zed
skip_repos = []                    # ["owner/repo", ...]
auto_install = true                # run mise install / uv sync / npm install in fresh worktrees
auto_trust_mise = true             # `mise trust` before `mise install` to skip its prompt
worktree_layout = "flat"           # "flat" (siblings) or "hierarchical" (.worktrees/)
prefix_worktrees = true            # name folders <repo-lower>-main / <repo-lower>-<pr>-<branch>
bare_repo = false                  # store .git as a bare repo and treat main as a worktree
sidecar_branches = true            # check PR worktrees out on a claude/<branch> sidecar
```

## Sidecar model — diff in the worktree, sync from main

Each PR worktree is checked out on a **sidecar branch** `claude/<branch>`, not the PR's
real branch. The real `<branch>` stays in `<repo>-main/` **un-checked-out**, so `gt sync`
can restack the whole Graphite stack there — git refuses to rebase a branch that is
checked out in a worktree, which is why direct-checkout worktrees broke `gt sync`.

The contract:

- **All editing happens in the worktree folder**, on the `claude/<branch>` sidecar.
- **Sync / consistency happens only in `<repo>-main/`** — never run `gt sync` inside a
  worktree, and never run two `gt sync` for the same repo at once.
- `repo-control sync-stack` is the one safe way to restack: it holds an flock, then
  fast-forwards `<branch>` from the sidecar, restacks in main, and rebases the sidecar
  back onto the restacked `<branch>`.

`<branch>` is canonical — Graphite tracks and pushes it from main.

## Preflight (once per session)

Before the first `repo-control` invocation, confirm the environment:

```bash
command -v repo-control && gh auth status
```

If either fails, halt and report the exact remediation:

- `gh auth status` failure → `gh auth login` (user runs themselves).
- `repo-control` missing → install via `uv tool install --editable <repo-path>` or `uv tool install repo-control` (once published).

Do not retry blindly. Do not bootstrap silently.

## Mode dispatch

| User says | Run |
|---|---|
| "sync my PRs", "sync repo-control", "refresh worktrees" | `repo-control sync` |
| "sync just owner/repo", "sync this repo only" | `repo-control sync <owner/repo>` |
| "sync the stack", "restack from main", "gt sync safely", "reconcile worktrees" | `repo-control sync-stack` |
| "restack just owner/repo" | `repo-control sync-stack <owner/repo>` |
| "list my worktrees", "what am I working on" | `repo-control list` |
| "open PR 5432", "open the parser fix" (after resolving) | `repo-control open <pr>` |
| "clean stale worktrees", "prune merged ones" | `repo-control clean` |
| "what's dirty", "vacuum dirty worktrees", "kill the kept-dirty ones" | `repo-control vacuum` |
| "set up repo-control", "reconfigure repo-control" | `repo-control setup` |
| "install the skill", "link the skill" | `repo-control install-skill` |

## sync

Run `repo-control sync` and show the summary verbatim. When the user names a single repo (e.g. "sync just PFigs/repo-control" or pastes a GitHub URL), pass it as an argument: `repo-control sync PFigs/repo-control` — only that repo's worktrees are created/refreshed/cleaned; others are left untouched. Otherwise sync may show an interactive repo picker (arrows/space/enter) when multiple repos have open PRs — let it complete. If no config exists yet, sync will auto-launch `setup` which is interactive — let it complete.

`sync` creates/refreshes the sidecar worktrees and fast-forwards each real `<branch>` from `origin`. It does **not** restack — that is `sync-stack`. After sync finishes, surface anything that needs the user's attention:

- Worktrees kept dirty (PR closed but uncommitted work present) — call them out by path.
- Fork PRs that failed to fetch — print the error.

Never auto-rerun on failure. Never run `clean` as a follow-up unless the user asks.

## sync-stack

`repo-control sync-stack` is the consistency operation — run it from anywhere; it operates inside each `<repo>-main/`. It is flock-guarded, so it is safe to run while a parallel session is working: if the lock is held it reports `another session is syncing <repo>` and skips that repo rather than colliding.

For each repo it: fast-forwards each real `<branch>` from its sidecar's committed work, restacks (`gt sync` where Graphite metadata exists, otherwise `git fetch` + fast-forward of trunk), then rebases each clean sidecar back onto its restacked `<branch>`. Pass `<owner/repo>` to limit it to one repo.

Show the per-repo summary verbatim and surface the warning lines (prefixed `!`):

- A `<branch>` that **diverged** from its sidecar — needs a manual reconcile.
- A sidecar skipped because its worktree is **dirty** — the user must commit first.
- A sidecar whose rebase **conflicted** — left untouched for the user to resolve.

The per-repo entry point `<base>/<repo>/.repo-control/sync-stack` runs the same thing for that one repo.

## open

If the user's reference is ambiguous (e.g. "open the parser fix"), run `repo-control list` first and show matches, then ask which one. Once the PR is unambiguous, invoke `repo-control open <pr>`. Pass `--ide=<binary>` (e.g. `code`, `idea`, `zed`, or any command on PATH; quote to include args) to override the configured default for one call.

## clean

Never run `repo-control clean --force` without explicit user authorisation in this turn. The plain `repo-control clean` removes only worktrees that are clean and whose PR no longer exists — that's safe and you can run it when asked. Removing a sidecar worktree also deletes both the `claude/<branch>` sidecar and the real `<branch>`.

## vacuum

`repo-control vacuum` targets the same set as the "kept dirty" callout from `sync`: worktrees whose PR has closed but that still have uncommitted work, unpushed commits, or branch-scoped stashes. It prints a per-worktree inspection (file counts, ahead/stash, and the first lines of `git status --short`) and opens a multi-select picker with everything **unchecked by default** since selection is destructive. Selected worktrees are removed with `git worktree remove --force` and both their sidecar and real branch are deleted. Run when the user says they want to drop the kept-dirty entries; never preselect on their behalf.

## setup

Interactive. Prompts for base_path, ide, skip_repos, layout, and `sidecar_branches`. Re-running it overwrites the existing config. Use when the user explicitly wants to change settings.

## install-skill

Symlinks the skill (bundled inside the installed Python package) to `~/.claude/skills/repo-control/`. Idempotent. Run when:

- The user just installed the package on a new machine.
- The user moved or reinstalled the package.
- `--uninstall` removes the symlink.

## Per-repo hooks

Drop executable scripts in `<base>/<repo>/.repo-control/` to run custom commands during sync. The folder lives next to `main/` and the worktrees, NOT inside any worktree — fork PRs can never inject one. It also holds the generated `sync-stack` shim and the sync-stack flock.

- `post-create` — runs once after a new PR worktree is set up, after the built-in installers.
- `post-sync` — runs after every create AND every refresh, for periodic actions (re-auth, `mise run …`, etc.).

Each hook runs with the worktree as `cwd` and these env vars exposed: `REPO_CONTROL_EVENT`, `REPO_CONTROL_WORKTREE`, `REPO_CONTROL_REPO_PATH`, `REPO_CONTROL_OWNER`, `REPO_CONTROL_REPO`, `REPO_CONTROL_PR_NUMBER`, `REPO_CONTROL_BRANCH`. Non-zero exit is reported in the sync summary but does not abort. A file that isn't `chmod +x` is skipped with a warning.

## Out of scope

This skill never:

- Commits, pushes, or opens PRs (that's `graphite-cli` / `parley`).
- Auto-syncs on session start.
- Runs `gt sync` directly inside a worktree — restacks go through `sync-stack` from main.
- Modifies the user's working tree in any worktree other than via `git worktree add` / `remove` and the `sync-stack` reconcile.
