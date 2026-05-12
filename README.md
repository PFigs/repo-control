# repo-control

Mirror every open GitHub PR you've authored as a ready-to-code git worktree under `~/workspace/repo-control/`.

```
~/workspace/repo-control/
  <owner>__<repo>/
    main/                        # always kept, fast-forwarded each sync
    <pr#>-<branch>/              # one worktree per open PR
  .config.toml                   # ide = "idea"|"code"; skip_repos = [...]
```

A single daily `repo-control sync` clones missing repos, creates worktrees for new PRs, refreshes existing ones, and removes worktrees whose PRs were merged/closed (only if clean). First creation runs `mise install` / `uv sync` / `npm install` automatically when those manifests exist.

## Install

```bash
uv tool install --editable "/home/silva/home projects/repo-control"
```

Requires `gh` (authenticated) and `uv` on PATH. Python 3.12+.

## Usage

```bash
repo-control sync               # daily refresh
repo-control list               # table of repo / pr / branch / status / path
repo-control open <pr>          # launch the configured IDE on that worktree
repo-control open <pr> --ide=code
repo-control clean              # prune stale worktrees (clean only)
repo-control clean --force      # confirm-then-drop dirty ones too
```

`<pr>` is the GitHub PR number. If the same number exists across multiple repos (rare), use `<owner>/<repo>#<n>`.

## Config

`~/workspace/repo-control/.config.toml` is created on first sync:

```toml
ide = "idea"          # or "code"
skip_repos = []       # ["owner/repo", ...] to ignore
```

## Safety properties

- Idempotent. Re-running `sync` immediately is a no-op.
- A worktree with uncommitted work, stashes, or unpushed commits is never auto-removed; sync flags it and moves on.
- `gh` auth or network failure aborts before any filesystem mutation.
