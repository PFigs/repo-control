---
name: repo-control
description: Use when the user says "sync my PRs", "sync repo-control", "refresh my worktrees", "open PR <n>", "what am I working on", or otherwise wants to inspect or refresh the local per-repo worktree mirrors created by the `repo-control` CLI. Wraps the `repo-control` command.
allowed-tools: Bash
---

# repo-control

For every open PR the user has authored on GitHub, the `repo-control` CLI scaffolds a per-repo folder under one configurable base path (default `~/.local/share/repo-control/`, XDG_DATA_HOME). Each folder holds the repo's `main/` worktree plus one worktree per open PR.

```
<base_path>/
  webapp/                        # hierarchical layout (default)
    webapp-main/
    .worktrees/
      webapp-142-fix-navbar-overflow/
      webapp-141-add-dark-mode/
  cli-tool/                      # flat layout
    cli-tool-main/
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
worktree_layout = "hierarchical"   # "hierarchical" (.worktrees/) or "flat" (siblings)
prefix_worktrees = true            # name folders <repo-lower>-main / <repo-lower>-<pr>-<branch>
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
| "sync just owner/repo", "sync this repo only" | `repo-control sync <owner/repo>` |
| "list my worktrees", "what am I working on" | `repo-control list` |
| "open PR 5432", "open the parser fix" (after resolving) | `repo-control open <pr>` |
| "clean stale worktrees", "prune merged ones" | `repo-control clean` |
| "what's dirty", "vacuum dirty worktrees", "kill the kept-dirty ones" | `repo-control vacuum` |
| "set up repo-control", "reconfigure repo-control" | `repo-control setup` |
| "install the skill", "link the skill" | `repo-control install-skill` |

## sync

Run `repo-control sync` and show the summary verbatim. When the user names a single repo (e.g. "sync just PFigs/repo-control" or pastes a GitHub URL), pass it as an argument: `repo-control sync PFigs/repo-control` — only that repo's worktrees are created/refreshed/cleaned; others are left untouched. Otherwise sync may show an interactive repo picker (arrows/space/enter) when multiple repos have open PRs — let it complete. If no config exists yet, sync will auto-launch `setup` which is interactive — let it complete. After sync finishes, surface anything that needs the user's attention:

- Worktrees kept dirty (PR closed but uncommitted work present) — call them out by path.
- Fork PRs that failed to fetch — print the error.

Never auto-rerun on failure. Never run `clean` as a follow-up unless the user asks.

## open

If the user's reference is ambiguous (e.g. "open the parser fix"), run `repo-control list` first and show matches, then ask which one. Once the PR is unambiguous, invoke `repo-control open <pr>`. Pass `--ide=<binary>` (e.g. `code`, `idea`, `zed`, or any command on PATH; quote to include args) to override the configured default for one call.

## clean

Never run `repo-control clean --force` without explicit user authorisation in this turn. The plain `repo-control clean` removes only worktrees that are clean and whose PR no longer exists — that's safe and you can run it when asked.

## vacuum

`repo-control vacuum` targets the same set as the "kept dirty" callout from `sync`: worktrees whose PR has closed but that still have uncommitted work, unpushed commits, or branch-scoped stashes. It prints a per-worktree inspection (file counts, ahead/stash, and the first lines of `git status --short`) and opens a multi-select picker with everything **unchecked by default** since selection is destructive. Selected worktrees are removed with `git worktree remove --force` and their branch is deleted. Run when the user says they want to drop the kept-dirty entries; never preselect on their behalf.

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
