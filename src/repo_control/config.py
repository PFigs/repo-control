import os
import tomllib
from pathlib import Path


def xdg_config_home() -> Path:
    raw = os.environ.get("XDG_CONFIG_HOME")
    return Path(raw) if raw else Path.home() / ".config"


def xdg_data_home() -> Path:
    raw = os.environ.get("XDG_DATA_HOME")
    return Path(raw) if raw else Path.home() / ".local" / "share"


DEFAULTS: dict = {
    "base_path": str(xdg_data_home() / "repo-control"),
    "ide": "idea",
    "skip_repos": [],
}


def config_path() -> Path:
    return xdg_config_home() / "repo-control" / "config.toml"


def exists() -> bool:
    return config_path().exists()


def load() -> dict:
    path = config_path()
    if not path.exists():
        return dict(DEFAULTS)
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return {**DEFAULTS, **data}


def write(*, base_path: str, ide: str, skip_repos: list[str]) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    skip_repr = ", ".join(f'"{r}"' for r in skip_repos)
    path.write_text(
        f'base_path = "{base_path}"\n'
        f'ide = "{ide}"\n'
        f"skip_repos = [{skip_repr}]\n"
    )
    return path


def base_path(*, cfg: dict | None = None) -> Path:
    settings = cfg or load()
    return Path(os.path.expanduser(settings["base_path"]))
