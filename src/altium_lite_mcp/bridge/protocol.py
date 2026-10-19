"""Wire format between the Python server and the DelphiScript project.

Request: plain `key=value` lines (DelphiScript reads these with
TStringList.Values). Lists are flattened as `key.0=a`, `key.1=b`, and lists
of objects as `key.0.field=x`. Values are ASCII-escaped.
Response: JSON.
"""

from __future__ import annotations

from typing import Any

from ..models import E_INVALID_INPUT, AltiumError


def escape_value(value: str) -> str:
    out = []
    for ch in value:
        o = ord(ch)
        if o > 0xFF:
            raise AltiumError(E_INVALID_INPUT, "Text contains characters above U+00FF, which cannot be sent to Altium.")
        if ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif o < 0x20 or o >= 0x7F:
            out.append("\\u%04X" % o)
        else:
            out.append(ch)
    return "".join(out)


def unescape_value(text: str) -> str:
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt == "\\":
                out.append("\\")
                i += 2
                continue
            if nxt == "n":
                out.append("\n")
                i += 2
                continue
            if nxt == "r":
                out.append("\r")
                i += 2
                continue
            if nxt == "u" and len(text) >= i + 6:
                out.append(chr(int(text[i + 2 : i + 6], 16)))
                i += 6
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def flatten(params: dict[str, Any]) -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, val in params.items():
        _flatten_into(flat, key, val)
    return flat


def _flatten_into(flat: dict[str, str], key: str, val: Any) -> None:
    if isinstance(val, bool):
        flat[key] = "true" if val else "false"
    elif isinstance(val, (int, float)):
        flat[key] = str(val)
    elif isinstance(val, str):
        flat[key] = val
    elif isinstance(val, (list, tuple)):
        flat[f"{key}.count"] = str(len(val))
        for i, item in enumerate(val):
            _flatten_into(flat, f"{key}.{i}", item)
    elif isinstance(val, dict):
        for k, v in val.items():
            _flatten_into(flat, f"{key}.{k}", v)
    elif val is None:
        pass
    else:
        raise AltiumError(E_INVALID_INPUT, f"Unsupported parameter type {type(val).__name__}.")


def encode_request(request_id: str, command: str, protocol: int, params: dict[str, Any]) -> str:
    lines = [f"protocol={protocol}", f"id={request_id}", f"command={command}"]
    for key, val in flatten(params).items():
        lines.append(f"{key}={escape_value(val)}")
    return "\r\n".join(lines) + "\r\n"


def parse_request(text: str) -> dict[str, str]:
    """Inverse of encode_request, split on the first '=' like TStringList.Values."""
    flat: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        flat[key] = unescape_value(val)
    return flat


def unflatten(flat: dict[str, str]) -> dict[str, Any]:
    """Rebuild lists/objects from a flat request (used by the test emulator)."""
    root: dict[str, Any] = {}
    for key, val in flat.items():
        if key.endswith(".count"):
            continue
        parts = key.split(".")
        node: Any = root
        for idx, part in enumerate(parts):
            last = idx == len(parts) - 1
            nxt = parts[idx + 1] if not last else None
            container: Any = [] if (nxt is not None and nxt.isdigit()) else {}
            if part.isdigit():
                i = int(part)
                while len(node) <= i:
                    node.append(None)
                if last:
                    node[i] = val
                else:
                    if node[i] is None:
                        node[i] = container
                    node = node[i]
            else:
                if last:
                    node[part] = val
                else:
                    node = node.setdefault(part, container)
    return root
