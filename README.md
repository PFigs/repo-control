# repo-control

Mirror every open GitHub PR you've authored as a per-repo cluster of git worktrees under a single base path. One folder per tracked repo, holding the main checkout plus one worktree per open PR.

```
<base_path>/
  webapp/                        # flat layout (default)
    webapp-main/                 # main checkout, fast-forwarded each sync
    webapp-142-fix-navbar/       # one worktree per open PR
    webapp-141-add-dark-mode/
  cli-tool/                      # hierarchical layout: the repo folder IS the main checkout
    .worktrees/
      cli-tool-37-bump-python/   # PR worktrees live inside it, git-excluded
```

With `bare_repo = true` (hierarchical), `.git` at `<repo>/.git` is bare and main is itself a worktree at `<repo>/.worktrees/<repo>-main/`, next to the PR worktrees. Pre-existing `<repo>-control/`, `<repo>/main/`, or `<repo>/<repo>-main/` checkouts on disk are always detected and reused in place; nothing migrates.

A single daily `repo-control sync` clones missing repos, creates worktrees for new PRs, refreshes existing ones, and removes worktrees whose PRs were merged/closed (only if the worktree is clean). First creation runs `mise install` / `uv sync` / `npm install` automatically when those manifests exist.

## Sidecar branches

Each PR worktree is checked out on a **sidecar branch** `claude/<branch>`, not the PR's real branch. The real `<branch>` stays in the main checkout un-checked-out, so `gt sync` can restack the whole Graphite stack there — git refuses to rebase a branch that is checked out in a worktree.

Edit in the worktree on the sidecar; restack from the main checkout with `repo-control sync-stack`. That command is flock-guarded (parallel sessions can't collide): it fast-forwards `<branch>` from the sidecar, restacks (`gt sync` where Graphite is set up, else `git fetch` + fast-forward), then rebases the sidecar back onto the restacked `<branch>`. Set `sidecar_branches = false` to keep the older direct-checkout behavior.

## Install

From PyPI:

```bash
uv tool install repo-control
```

Or with pipx / pip:

```bash
pipx install repo-control
# pip install --user repo-control
```

From a local checkout (editable):

```bash
uv tool install --editable "/path/to/repo-control"
```

Then:

```bash
repo-control setup           # interactive config (also auto-triggered on first sync)
repo-control install-skill   # symlinks the bundled Claude skill into ~/.claude/skills/
```

Requires `gh` (authenticated) and `uv` on PATH. Python 3.12+.

## Usage

```bash
repo-control sync               # daily refresh (auto-runs setup on first invocation)
repo-control sync-stack         # flock-guarded restack: reconcile sidecars from main
repo-control list               # table of repo / pr / branch / status / path
repo-control open <pr>          # launch the configured IDE on that worktree
repo-control open <pr> --ide=code
repo-control clean              # prune stale worktrees (clean only)
repo-control clean --force      # confirm-then-drop dirty ones too
repo-control vacuum             # inspect dirty stale worktrees and drop selected ones
repo-control setup              # re-run interactive config
repo-control install-skill      # symlink the bundled skill (or --uninstall)
```

`<pr>` is the GitHub PR number. If the same number exists across multiple repos (rare), use `<owner>/<repo>#<n>`.

## Config

XDG-conformant paths:

- Config: `$XDG_CONFIG_HOME/repo-control/config.toml` (default `~/.config/repo-control/config.toml`).
- Default base path: `$XDG_DATA_HOME/repo-control/` (default `~/.local/share/repo-control/`).

```toml
base_path = "/home/<user>/.local/share/repo-control"
ide = "idea"                   # any binary on PATH; suggestions: idea, code, zed
skip_repos = []                # ["owner/repo", ...] to ignore
sidecar_branches = true        # check PR worktrees out on a claude/<branch> sidecar
```

`repo-control setup` is interactive — first sync triggers it automatically; re-run any time to change settings.

## Bundled Claude skill

The skill ships inside the Python package at `repo_control/skill/SKILL.md`. `repo-control install-skill` symlinks it into `~/.claude/skills/repo-control/` so Claude Code picks it up. Idempotent; `--uninstall` removes the symlink.

## Per-repo hooks

Drop executable scripts in `<base>/<repo>/.repo-control/` to run custom commands during sync. The folder sits at the repo folder root, never inside any PR worktree — fork PRs can never inject one. In hierarchical layout that root is the main checkout's own tree; the folder is git-excluded via `.git/info/exclude`.

- `post-create` — runs once after a new PR worktree is set up, after the built-in installers.
- `post-sync` — runs after every create AND every refresh, for the periodic action (re-auth, `mise run …`, etc.).

Each script runs with the worktree as `cwd` and these env vars exposed: `REPO_CONTROL_EVENT`, `REPO_CONTROL_WORKTREE`, `REPO_CONTROL_REPO_PATH`, `REPO_CONTROL_OWNER`, `REPO_CONTROL_REPO`, `REPO_CONTROL_PR_NUMBER`, `REPO_CONTROL_BRANCH`. Non-zero exit is reported in the sync summary but does not abort. A file that isn't `chmod +x` is skipped with a warning.

## Safety properties

- Idempotent. Re-running `sync` immediately is a no-op.
- A worktree with uncommitted work, stashes, or unpushed commits is never auto-removed; sync flags it and moves on.
- `gh` auth or network failure aborts before any filesystem mutation.
- If two different `<owner>/<repo>` pairs would collide on the same repo folder, sync skips the second with a warning rather than overwriting.
