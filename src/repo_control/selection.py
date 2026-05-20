"""Persist the user's last interactive sync repo selection."""

from __future__ import annotations

import json
from pathlib import Path

from repo_control.config import xdg_data_home


def selection_path() -> Path:
    return xdg_data_home() / "repo-control" / "sync-selection.json"


def load_selection() -> set[tuple[str, str]] | None:
    """Last saved selection, or None when absent, unreadable, malformed, or empty."""
    path = selection_path()
    if not path.exists():
        return None
    try:
        repos = json.loads(path.read_text())["repos"]
        slugs = list(repos)
    except (json.JSONDecodeError, OSError, KeyError, TypeError):
        return None
    out: set[tuple[str, str]] = set()
    for slug in slugs:
        owner, _, name = str(slug).partition("/")
        if owner and name:
            out.add((owner, name))
    return out or None


def save_selection(repos: set[tuple[str, str]]) -> None:
    """Persist a non-empty selection as sorted owner/name slugs; empty sets are ignored."""
    if not repos:
        return
    path = selection_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    slugs = sorted(f"{owner}/{name}" for owner, name in repos)
    path.write_text(json.dumps({"repos": slugs}, indent=2) + "\n")


def preselected_keys(
    *,
    last: set[tuple[str, str]] | None,
    available: set[tuple[str, str]],
) -> set[str] | None:
    """Slugs to pre-check in the picker.

    None means there is no usable memory (no saved selection, or none of the
    saved repos are still available) -- the caller falls back to default_selected.
    """
    if not last:
        return None
    sticky = last & available
    if not sticky:
        return None
    return {f"{owner}/{name}" for owner, name in sticky}
