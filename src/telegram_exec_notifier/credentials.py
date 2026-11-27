"""Load settings from a systemd encrypted credential instead of a plain env file."""

from __future__ import annotations

import os
from pathlib import Path

CREDENTIAL_NAME = "environment"
# Variables the spawned agent CLIs must never inherit.
SECRET_VARS = ("TELEGRAM_BOT_TOKEN", "CREDENTIALS_DIRECTORY")


def _parse(text: str) -> dict[str, str]:
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_credentials() -> None:
    """Export KEY=VALUE pairs from the credential into os.environ.

    Does nothing when the service was not started with a credential (for example
    when variables come from a plain EnvironmentFile or the shell).
    """
    directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if not directory:
        return
    path = Path(directory) / CREDENTIAL_NAME
    try:
        values = _parse(path.read_text())
    except OSError:
        return
    os.environ.update(values)


def child_env() -> dict[str, str]:
    """Environment for agent subprocesses, without the bot token."""
    return {k: v for k, v in os.environ.items() if k not in SECRET_VARS}
