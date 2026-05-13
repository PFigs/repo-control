import shlex
import shutil
import subprocess
from pathlib import Path

KNOWN = ("idea", "code", "zed")


def launch(*, ide: str, path: Path) -> None:
    parts = shlex.split(ide)
    if not parts:
        raise ValueError("ide is empty")
    binary, *extra = parts
    if shutil.which(binary) is None:
        raise RuntimeError(
            f"{binary!r} not on PATH; install its CLI launcher or pick a different --ide"
        )
    subprocess.Popen(
        [binary, *extra, str(path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
