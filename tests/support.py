"""Shared helpers for the test suite."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def posix_path(path: Path | str) -> str:
    """Path in the form the bash from bash_command() understands.

    Git for Windows' bash treats a backslash path as an escape sequence, which
    silently breaks the build scripts' own path handling.
    """
    text = str(path)
    if os.name != "nt":
        return text
    drive, _, rest = text.partition(":")
    if len(drive) == 1 and rest:
        return "/" + drive.lower() + rest.replace("\\", "/")
    return text.replace("\\", "/")


def bash_command() -> str:
    """Absolute path of a POSIX bash able to run the build scripts.

    On Windows the bare name "bash" reaches the WSL launcher, which cannot use
    Windows paths, so the build tests could only run in CI. Git for Windows
    ships a usable bash; prefer it, and fall back to whatever is on PATH.
    """
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "Git/bin/bash.exe",
            Path(os.environ.get("ProgramW6432", r"C:\Program Files"))
            / "Git/bin/bash.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Git/bin/bash.exe",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return shutil.which("bash") or "bash"
