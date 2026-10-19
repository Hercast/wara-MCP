"""Bridge interface shared by the real (Altium) and fake bridges."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..models import E_TIMEOUT, AltiumError


class Bridge(ABC):
    name = "bridge"
    exe_path: Path | None = None

    def __init__(self) -> None:
        self.suspect_wedged = False
        self.last_ok: float | None = None
        self.script_version: str | None = None

    def call(self, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run one command and return its `data` dict, or raise AltiumError."""
        try:
            data = self._call(command, params or {})
        except AltiumError as err:
            if err.code == E_TIMEOUT:
                self.suspect_wedged = True
            raise
        self.last_ok = time.time()
        self.suspect_wedged = False
        return data

    @abstractmethod
    def _call(self, command: str, params: dict[str, Any]) -> dict[str, Any]: ...
