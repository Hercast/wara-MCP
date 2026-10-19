"""Server configuration, read from environment variables.

The mode can only be set here (the MCP client's server environment), never
through tool arguments.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

READ_ONLY = "read_only"
READ_WRITE = "read_write"
READ_WRITE_SAVE = "read_write_save"
MODES = (READ_ONLY, READ_WRITE, READ_WRITE_SAVE)


def default_exchange_dir() -> Path:
    """A per-user folder (not world-writable like C:\\Users\\Public), with no spaces."""
    if os.name == "nt":
        user = re.sub(r"[^A-Za-z0-9_.-]", "_", os.environ.get("USERNAME", "user"))
        base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(base) / "altium_lite_mcp" / user
    return Path.home() / ".altium_lite_mcp"


@dataclass(frozen=True)
class Config:
    mode: str = READ_ONLY
    exchange_dir: Path = field(default_factory=default_exchange_dir)
    exe_path: Path | None = None
    timeout_s: float = 60.0
    poll_interval_s: float = 0.5
    cache_ttl_s: float = 5.0
    bridge: str = "altium"  # "altium" or "fake"
    warnings: tuple[str, ...] = ()

    @property
    def writable(self) -> bool:
        return self.mode in (READ_WRITE, READ_WRITE_SAVE)

    @property
    def can_save(self) -> bool:
        return self.mode == READ_WRITE_SAVE

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Config":
        env = dict(os.environ) if env is None else env
        warnings: list[str] = []

        mode = env.get("ALTIUM_LITE_MODE", READ_ONLY).strip().lower()
        if mode not in MODES:
            warnings.append(f"Unknown ALTIUM_LITE_MODE {mode!r}; using read_only.")
            mode = READ_ONLY

        bridge = env.get("ALTIUM_LITE_BRIDGE", "altium").strip().lower()
        if bridge not in ("altium", "fake"):
            warnings.append(f"Unknown ALTIUM_LITE_BRIDGE {bridge!r}; using altium.")
            bridge = "altium"

        timeout_s = _float(env, "ALTIUM_LITE_TIMEOUT", 60.0, warnings, minimum=1.0)
        cache_ttl_s = _float(env, "ALTIUM_LITE_CACHE_TTL", 5.0, warnings, minimum=0.0)
        exchange = env.get("ALTIUM_LITE_EXCHANGE_DIR")
        exe = env.get("ALTIUM_LITE_EXE")

        return cls(
            mode=mode,
            exchange_dir=Path(exchange) if exchange else default_exchange_dir(),
            exe_path=Path(exe) if exe else None,
            timeout_s=timeout_s,
            cache_ttl_s=cache_ttl_s,
            bridge=bridge,
            warnings=tuple(warnings),
        )


def _float(env: dict[str, str], key: str, default: float, warnings: list[str], minimum: float) -> float:
    raw = env.get(key)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        warnings.append(f"{key}={raw!r} is not a number; using {default}.")
        return default
    if value < minimum:
        warnings.append(f"{key}={raw!r} is below {minimum}; using {default}.")
        return default
    return value
