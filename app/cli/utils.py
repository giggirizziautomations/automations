"""Utility helpers for CLI commands."""
from __future__ import annotations

from pathlib import Path


def upsert_env_value(env_path: Path, name: str, value: str) -> None:
    """Create or update an environment variable entry inside ``env_path``.

    The function keeps existing content untouched except for the requested
    variable, ensuring no duplicate keys are present and always leaving a
    trailing newline to play nicely with POSIX tooling.
    """

    env_path.parent.mkdir(parents=True, exist_ok=True)

    lines = env_path.read_text().splitlines() if env_path.exists() else []

    for index, line in enumerate(lines):
        if "=" not in line or line.lstrip().startswith("#"):
            continue

        key, _, _ = line.partition("=")
        if key.strip() == name:
            lines[index] = f"{name}={value}"
            break
    else:
        lines.append(f"{name}={value}")

    env_path.write_text("\n".join(lines) + "\n")

