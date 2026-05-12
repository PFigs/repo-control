# repo-control

Mirror every open GitHub PR you've authored as a per-repo cluster of git worktrees under a single base path. One folder per tracked repo, named `<repo>-control/`, holding `main/` plus one worktree per open PR.

```
<base_path>/
  Backend-control/
    main/                        # always kept, fast-forwarded each sync
    2851-fix_parser_foo/         # one worktree per open PR
    2850-fix_data_ingestion_fmt/
  metering-sdk-control/
    main/
    522-feat_android_mercado_libre_br/
```

A single daily `repo-control sync` clones missing repos, creates worktrees for new PRs, refreshes existing ones, and removes worktrees whose PRs were merged/closed (only if the worktree is clean). First creation runs `mise install` / `uv sync` / `npm install` automatically when those manifests exist.

## Install

```bash
uv tool install --editable "/path/to/repo-control"   # or `uv tool install repo-control` once published
repo-control setup                                   # interactive config (also auto-triggered on first sync)
repo-control install-skill                           # symlinks the bundled Claude skill into ~/.claude/skills/
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
ide = "idea"                   # or "code"
skip_repos = []                # ["owner/repo", ...] to ignore
```

`repo-control setup` is interactive — first sync triggers it automatically; re-run any time to change settings.

## Bundled Claude skill

The skill ships inside the Python package at `repo_control/skill/SKILL.md`. `repo-control install-skill` symlinks it into `~/.claude/skills/repo-control/` so Claude Code picks it up. Idempotent; `--uninstall` removes the symlink.

## Safety properties

- Idempotent. Re-running `sync` immediately is a no-op.
- A worktree with uncommitted work, stashes, or unpushed commits is never auto-removed; sync flags it and moves on.
- `gh` auth or network failure aborts before any filesystem mutation.
- If two different `<owner>/<repo>` pairs would collide on `<repo>-control/`, sync skips the second with a warning rather than overwriting.
