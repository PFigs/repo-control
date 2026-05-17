# repo-control

Mirror every open GitHub PR you've authored as a per-repo cluster of git worktrees under a single base path. One folder per tracked repo, named `<repo>-control/`, holding `main/` plus one worktree per open PR.

```
<base_path>/
  webapp-control/
    main/                        # always kept, fast-forwarded each sync
    142-fix_navbar_overflow/     # one worktree per open PR
    141-add_dark_mode/
  cli-tool-control/
    main/
    37-bump_python_to_312/
```

A single daily `repo-control sync` clones missing repos, creates worktrees for new PRs, refreshes existing ones, and removes worktrees whose PRs were merged/closed (only if the worktree is clean). First creation runs `mise install` / `uv sync` / `npm install` automatically when those manifests exist.

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
```

`repo-control setup` is interactive — first sync triggers it automatically; re-run any time to change settings.

## Bundled Claude skill

The skill ships inside the Python package at `repo_control/skill/SKILL.md`. `repo-control install-skill` symlinks it into `~/.claude/skills/repo-control/` so Claude Code picks it up. Idempotent; `--uninstall` removes the symlink.

## Per-repo hooks

Drop executable scripts in `<base>/<repo>/.repo-control/` to run custom commands during sync. The folder lives next to `main/` and the worktrees, NOT inside any worktree — fork PRs can never inject one.

- `post-create` — runs once after a new PR worktree is set up, after the built-in installers.
- `post-sync` — runs after every create AND every refresh, for the periodic action (re-auth, `mise run …`, etc.).

Each script runs with the worktree as `cwd` and these env vars exposed: `REPO_CONTROL_EVENT`, `REPO_CONTROL_WORKTREE`, `REPO_CONTROL_REPO_PATH`, `REPO_CONTROL_OWNER`, `REPO_CONTROL_REPO`, `REPO_CONTROL_PR_NUMBER`, `REPO_CONTROL_BRANCH`. Non-zero exit is reported in the sync summary but does not abort. A file that isn't `chmod +x` is skipped with a warning.

## Safety properties

- Idempotent. Re-running `sync` immediately is a no-op.
- A worktree with uncommitted work, stashes, or unpushed commits is never auto-removed; sync flags it and moves on.
- `gh` auth or network failure aborts before any filesystem mutation.
- If two different `<owner>/<repo>` pairs would collide on `<repo>-control/`, sync skips the second with a warning rather than overwriting.
