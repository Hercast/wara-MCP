"""Tool logic, independent of MCP wiring."""

from __future__ import annotations

import re
from typing import Any

from . import PROTOCOL_VERSION, SCRIPT_VERSION, __version__
from .bridge.base import Bridge
from .config import Config
from .models import (
    E_BRIDGE_WEDGED,
    E_INVALID_INPUT,
    AltiumError,
)
from . import safety


def _natural(s: str) -> list[Any]:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _clip_item(item: dict[str, Any]) -> dict[str, Any]:
    out = dict(item)
    for k in ("designator", "comment", "library_ref", "footprint", "sheet"):
        if isinstance(out.get(k), str):
            out[k] = safety.clip(out[k])
    if isinstance(out.get("parameters"), dict):
        out["parameters"] = {safety.clip(str(k), 64): safety.clip(str(v)) for k, v in out["parameters"].items()}
    return out


def _param(item: dict[str, Any], name: str) -> tuple[str | None, str | None]:
    """Case-insensitive lookup -> (actual_name, value)."""
    for k, v in (item.get("parameters") or {}).items():
        if k.lower() == name.lower():
            return k, v
    return None, None


class AltiumService:
    def __init__(self, config: Config, bridge: Bridge):
        self.config = config
        self.bridge = bridge

    # -- status ------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        warnings = list(self.config.warnings)
        data: dict[str, Any] = {
            "server_version": __version__,
            "mode": self.config.mode,
            "altium": {
                "exe_path": str(self.bridge.exe_path) if self.bridge.exe_path else None,
                "version": None,
                "running": None,
            },
            "bridge": {
                "name": self.bridge.name,
                "script_version": None,
                "protocol_version": PROTOCOL_VERSION,
                "last_ok": self.bridge.last_ok,
                "suspect_wedged": self.bridge.suspect_wedged,
            },
            "active_project": None,
            "warnings": warnings,
        }
        try:
            resp = self.bridge.call("status")
        except AltiumError as err:
            data["altium"]["running"] = False if err.code != "E_TIMEOUT" else None
            warnings.append(f"{err.code}: {err.message} {err.hint or ''}".strip())
        else:
            data["altium"]["running"] = True
            data["altium"]["version"] = safety.clip(str(resp.get("altium_version") or ""), 64) or None
            data["bridge"]["script_version"] = resp.get("script_version") or self.bridge.script_version
            data["bridge"]["last_ok"] = self.bridge.last_ok
            data["bridge"]["suspect_wedged"] = False
            if resp.get("project_name"):
                data["active_project"] = {
                    "name": safety.clip(str(resp["project_name"])),
                    "path": safety.clip(str(resp.get("project_path") or ""), 300),
                }
            else:
                warnings.append("Altium is running but no project is open (E_NO_PROJECT).")
        return data

    # -- reads -------------------------------------------------------------
    def _fetch(self, designators: list[str] | None = None, include_pins: bool = False) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"include_pins": include_pins}
        if designators:
            params["designator"] = designators
        resp = self.bridge.call("get_components", params)
        return [c for c in resp.get("components", []) if isinstance(c, dict)]

    def list_components(
        self,
        limit: int = safety.DEFAULT_LIST_LIMIT,
        offset: int = 0,
        designator_prefix: str | None = None,
        missing_parameter: str | None = None,
    ) -> dict[str, Any]:
        safety.check_limit_offset(limit, offset)
        if missing_parameter is not None:
            safety.check_parameter_name(missing_parameter)
        rows = self._fetch()
        if designator_prefix:
            p = designator_prefix.lower()
            rows = [r for r in rows if str(r.get("designator", "")).lower().startswith(p)]
        if missing_parameter:
            rows = [r for r in rows if not (_param(r, missing_parameter)[1] or "").strip()]
        rows.sort(key=lambda r: _natural(str(r.get("designator", ""))))
        total = len(rows)
        page = rows[offset : offset + limit]
        items = []
        for r in page:
            item = _clip_item(r)
            item.pop("parameters", None)
            item.pop("pins", None)
            items.append(item)
        return {"total": total, "items": items, "truncated": offset + limit < total}

    def get_component(self, designators: list[str], include_pins: bool = False) -> dict[str, Any]:
        if not 1 <= len(designators) <= safety.MAX_GET_DESIGNATORS:
            raise AltiumError(E_INVALID_INPUT, f"Provide 1 to {safety.MAX_GET_DESIGNATORS} designators.")
        wanted = list(dict.fromkeys(safety.check_designator(d) for d in designators))
        rows = self._fetch(wanted, include_pins)
        found = {str(r.get("designator", "")).upper(): r for r in rows}
        items = [_clip_item(found[d.upper()]) for d in wanted if d.upper() in found]
        return {"items": items, "not_found": [d for d in wanted if d.upper() not in found]}

    # -- write -------------------------------------------------------------
    def set_parameter(
        self, changes: list[dict[str, str]], apply: bool = False, create_if_missing: bool = False
    ) -> dict[str, Any]:
        safety.require_writable(self.config)
        if not 1 <= len(changes) <= safety.MAX_CHANGES:
            raise AltiumError(E_INVALID_INPUT, f"Provide 1 to {safety.MAX_CHANGES} changes.")
        clean: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for ch in changes:
            des = safety.check_designator(ch.get("designator", ""))
            name = safety.check_parameter_name(ch.get("name", ""))
            value = safety.check_value(ch.get("value", ""))
            key = (des.upper(), name.lower())
            if key in seen:
                raise AltiumError(E_INVALID_INPUT, f"Duplicate change for {des} / {name}.")
            seen.add(key)
            clean.append({"designator": des, "name": name, "value": value})

        if apply and self.bridge.suspect_wedged:
            raise AltiumError(E_BRIDGE_WEDGED, "A previous call timed out; writes are blocked until Altium answers a read.")

        current = {
            str(r.get("designator", "")).upper(): r
            for r in self._fetch(list(dict.fromkeys(c["designator"] for c in clean)))
        }
        rows: list[dict[str, Any]] = []
        for ch in clean:
            row: dict[str, Any] = {"designator": ch["designator"], "name": ch["name"], "old": None, "new": ch["value"]}
            comp = current.get(ch["designator"].upper())
            if comp is None:
                row.update(status="not_found", reason="No such component in the project.")
            elif safety.is_reserved(ch["name"]):
                row.update(status="refused", reason="Reserved parameter; not editable in this version.")
            else:
                actual, old = _param(comp, ch["name"])
                row["old"] = old
                if actual is None and not create_if_missing:
                    row.update(status="refused", reason="Parameter does not exist; pass create_if_missing=true to add it.")
                elif actual is not None and old == ch["value"]:
                    row.update(status="no_change")
                else:
                    row.update(status="ok")
            rows.append(row)

        if not apply:
            return {
                "changes": rows,
                "applied": False,
                "verified": None,
                "note": "Preview only. Nothing was changed in Altium. Call again with apply=true to write.",
            }

        to_write = [r for r in rows if r["status"] == "ok"]
        if to_write:
            resp = self.bridge.call(
                "set_parameters",
                {
                    "change": [{"designator": r["designator"], "name": r["name"], "value": r["new"]} for r in to_write],
                    "create_if_missing": create_if_missing,
                },
            )
            script_status = {
                (str(x.get("designator", "")).upper(), str(x.get("name", "")).lower()): x.get("status")
                for x in resp.get("results", [])
            }
            after = {
                str(r.get("designator", "")).upper(): r
                for r in self._fetch(list(dict.fromkeys(r["designator"] for r in to_write)))
            }
            for r in to_write:
                st = script_status.get((r["designator"].upper(), r["name"].lower()))
                if st != "ok":
                    r["status"] = "error"
                    r["reason"] = f"Altium reported status {st!r}."
                    r["verified"] = False
                    continue
                _, val = _param(after.get(r["designator"].upper(), {}), r["name"])
                r["verified"] = val == r["new"]
        for r in rows:
            r.setdefault("verified", None)
        verified = all(r["verified"] for r in to_write) if to_write else None
        return {
            "changes": rows,
            "applied": bool(to_write),
            "verified": verified,
            "note": "Edits are in memory only: the schematic is modified but NOT saved. "
            "Press Ctrl+Z in Altium to undo (once per affected sheet). "
            "The PCB is not updated until you run Update PCB.",
        }
