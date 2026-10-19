"""Error codes, the exception type and the response envelope."""

from __future__ import annotations

from typing import Any

E_MODE_READ_ONLY = "E_MODE_READ_ONLY"
E_ALTIUM_NOT_FOUND = "E_ALTIUM_NOT_FOUND"
E_NO_PROJECT = "E_NO_PROJECT"
E_TIMEOUT = "E_TIMEOUT"
E_BRIDGE_WEDGED = "E_BRIDGE_WEDGED"
E_SCRIPT_VERSION = "E_SCRIPT_VERSION"
E_NOT_FOUND = "E_NOT_FOUND"
E_INVALID_INPUT = "E_INVALID_INPUT"
E_ALTIUM_ERROR = "E_ALTIUM_ERROR"

ERROR_CODES = frozenset(
    {
        E_MODE_READ_ONLY,
        E_ALTIUM_NOT_FOUND,
        E_NO_PROJECT,
        E_TIMEOUT,
        E_BRIDGE_WEDGED,
        E_SCRIPT_VERSION,
        E_NOT_FOUND,
        E_INVALID_INPUT,
        E_ALTIUM_ERROR,
    }
)

DEFAULT_HINTS = {
    E_MODE_READ_ONLY: "Set ALTIUM_LITE_MODE=read_write in the MCP server's environment and restart the server.",
    E_ALTIUM_NOT_FOUND: "Start Altium Designer on this Windows machine, or set ALTIUM_LITE_EXE to the full path of X2.EXE.",
    E_NO_PROJECT: "Open a project in Altium Designer (File > Open) and try again.",
    E_TIMEOUT: (
        "Altium did not answer. Check for a modal dialog in Altium, press Ctrl+F3 "
        "(Stop Running Script) if a script is stuck, or restart Altium. Then call altium_status."
    ),
    E_BRIDGE_WEDGED: (
        "An earlier call timed out. Fix Altium (close dialogs, Ctrl+F3 to stop a stuck script, "
        "or restart it), then call altium_status to clear this state."
    ),
    E_SCRIPT_VERSION: "Restart Altium or clear its script cache, then try again.",
}


class AltiumError(Exception):
    def __init__(self, code: str, message: str, hint: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint if hint is not None else DEFAULT_HINTS.get(code)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "hint": self.hint}


def ok(data: Any, meta: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None, "meta": meta}


def fail(err: AltiumError, meta: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "data": None, "error": err.to_dict(), "meta": meta}
