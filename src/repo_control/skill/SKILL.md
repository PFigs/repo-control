---
name: repo-control
description: Use when the user says "sync my PRs", "sync repo-control", "refresh my worktrees", "open PR <n>", "what am I working on", or otherwise wants to inspect or refresh the local per-repo worktree mirrors created by the `repo-control` CLI. Wraps the `repo-control` command.
allowed-tools: Bash
---

# repo-control

For every open PR the user has authored on GitHub, the `repo-control` CLI scaffolds a sibling `<repo>-control/` folder under one configurable base path (default `~/.local/share/repo-control/`, XDG_DATA_HOME). Each folder holds the repo's `main/` worktree plus one worktree per open PR.

```
<base_path>/
  Backend-control/
    main/                        # always kept
    2851-fix_parser_foo/         # one worktree per open PR
    2850-fix_data_ingestion_fmt/
  metering-sdk-control/
    main/
    522-feat_android_mercado_libre_br/
```

Configuration lives at `~/.config/repo-control/config.toml` (XDG_CONFIG_HOME). Created interactively by `repo-control setup` or on first `sync`.

```toml
base_path = "/home/<user>/.local/share/repo-control"
ide = "idea"          # any binary on PATH; suggestions: idea, code, zed
skip_repos = []       # ["owner/repo", ...]
```

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
| "list my worktrees", "what am I working on" | `repo-control list` |
| "open PR 5432", "open the parser fix" (after resolving) | `repo-control open <pr>` |
| "clean stale worktrees", "prune merged ones" | `repo-control clean` |
| "set up repo-control", "reconfigure repo-control" | `repo-control setup` |
| "install the skill", "link the skill" | `repo-control install-skill` |

## sync

Run `repo-control sync` and show the summary verbatim. If no config exists yet, sync will auto-launch `setup` which is interactive — let it complete. After sync finishes, surface anything that needs the user's attention:

- Worktrees kept dirty (PR closed but uncommitted work present) — call them out by path.
- Fork PRs that failed to fetch — print the error.

Never auto-rerun on failure. Never run `clean` as a follow-up unless the user asks.

## open

If the user's reference is ambiguous (e.g. "open the parser fix"), run `repo-control list` first and show matches, then ask which one. Once the PR is unambiguous, invoke `repo-control open <pr>`. Pass `--ide=<binary>` (e.g. `code`, `idea`, `zed`, or any command on PATH; quote to include args) to override the configured default for one call.

## clean

Never run `repo-control clean --force` without explicit user authorisation in this turn. The plain `repo-control clean` removes only worktrees that are clean and whose PR no longer exists — that's safe and you can run it when asked.

## setup

Interactive. Prompts for base_path, ide, skip_repos. Re-running it overwrites the existing config. Use when the user explicitly wants to change settings.

## install-skill

Symlinks the skill (bundled inside the installed Python package) to `~/.claude/skills/repo-control/`. Idempotent. Run when:

- The user just installed the package on a new machine.
- The user moved or reinstalled the package.
- `--uninstall` removes the symlink.

## Out of scope

This skill never:

- Commits, pushes, or opens PRs (that's `graphite-cli` / `parley`).
- Auto-syncs on session start.
- Modifies the user's working tree in any worktree other than via `git worktree add` / `remove`.
