"""Minimal stdlib multi-select TUI: arrows to navigate, space to toggle, enter to confirm."""

from __future__ import annotations

import sys
import termios
import tty
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Choice:
    key: str
    label: str


def select_multi(
    *,
    title: str,
    choices: Sequence[Choice],
    default_selected: bool = True,
) -> list[str] | None:
    """Render an interactive checkbox list. Returns selected keys, or None if cancelled.

    Falls back to "select all" when stdin is not a TTY.
    """
    if not choices:
        return []
    if not sys.stdin.isatty():
        return [c.key for c in choices] if default_selected else []

    selected = [default_selected] * len(choices)
    cursor = 0
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    out = sys.stdout
    rendered_lines = 0
    try:
        tty.setcbreak(fd)
        out.write("\x1b[?25l")
        while True:
            if rendered_lines:
                out.write(f"\x1b[{rendered_lines}A")
            out.write("\x1b[J")
            out.write(f"{title}\n")
            out.write("(↑/↓ move, space toggle, a/n all/none, enter confirm, q cancel)\n\n")
            for i, choice in enumerate(choices):
                pointer = ">" if i == cursor else " "
                mark = "[x]" if selected[i] else "[ ]"
                out.write(f"{pointer} {mark} {choice.label}\n")
            rendered_lines = 3 + len(choices)
            out.flush()
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                seq = sys.stdin.read(2)
                if seq == "[A":
                    cursor = (cursor - 1) % len(choices)
                elif seq == "[B":
                    cursor = (cursor + 1) % len(choices)
            elif ch == " ":
                selected[cursor] = not selected[cursor]
            elif ch in ("a", "A"):
                selected = [True] * len(choices)
            elif ch in ("n", "N"):
                selected = [False] * len(choices)
            elif ch in ("\r", "\n"):
                return [choices[i].key for i, on in enumerate(selected) if on]
            elif ch in ("q", "Q", "\x03"):
                return None
    finally:
        out.write("\x1b[?25h")
        out.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
