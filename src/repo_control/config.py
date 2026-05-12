import tomllib
from pathlib import Path

DEFAULTS = {"ide": "idea", "skip_repos": []}


def root() -> Path:
    return Path.home() / "workspace" / "repo-control"


def load() -> dict:
    path = root() / ".config.toml"
    if not path.exists():
        return dict(DEFAULTS)
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return {**DEFAULTS, **data}


def ensure_default_file() -> Path:
    path = root() / ".config.toml"
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('ide = "idea"\nskip_repos = []\n')
    return path
