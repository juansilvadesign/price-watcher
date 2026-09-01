"""Configuration read from the real environment, falling back to a local `.env`.

⛔ The `.env` is **parsed here, never sourced in a shell.** Sourcing an env file
leaks every value into the shell's history and into any child process, and one
malformed line can execute arbitrary code. This reader does neither: it does no
expansion, no substitution, and no execution.

Precedence: a real environment variable always wins over the `.env` file, so a cron
entry or a one-off `BOT_API_TOKEN=... python3 watch.py` can override the file.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def parse_env_file(path: Path) -> dict[str, str]:
    """Minimal, non-executing `.env` parser. Returns {} when the file is absent."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        val = val.strip()
        # Strip one matching pair of surrounding quotes; do not unescape anything else.
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key:
            out[key] = val
    return out


def get(name: str, default: str | None = None, env_path: Path | None = None) -> str | None:
    """Real environment first, then `.env`, then the default."""
    if name in os.environ and os.environ[name] != "":
        return os.environ[name]
    val = parse_env_file(env_path or DEFAULT_ENV_PATH).get(name)
    return val if val else default


def require(name: str, why: str, env_path: Path | None = None) -> str:
    val = get(name, env_path=env_path)
    if not val:
        raise KeyError(
            f"{name} is not set. {why} "
            f"Add it to {(env_path or DEFAULT_ENV_PATH).name} (see .env.example) "
            f"or export it in the environment."
        )
    return val
