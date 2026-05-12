import shutil
import subprocess
from pathlib import Path

COMMANDS = {"idea": "idea", "code": "code"}


def launch(*, ide: str, path: Path) -> None:
    binary = COMMANDS.get(ide)
    if binary is None:
        raise ValueError(f"unknown ide: {ide!r} (expected one of {sorted(COMMANDS)})")
    if shutil.which(binary) is None:
        raise RuntimeError(
            f"{binary!r} not on PATH; install the IDE's CLI launcher or pick a different --ide"
        )
    subprocess.Popen(
        [binary, str(path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
