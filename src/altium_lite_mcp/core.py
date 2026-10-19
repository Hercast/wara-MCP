"""Tool logic (reads and analysis), independent of MCP wiring."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from . import PROTOCOL_VERSION, __version__, analysis, safety
from .bridge.base import Bridge
from .config import Config
from .models import E_INVALID_INPUT, AltiumError
from .writes import WriteMixin

DEFAULT_GROUP_BY = ["comment", "footprint"]


@dataclass
class Snapshot:
    rows: list[dict[str, Any]]
    sheets: list[dict[str, Any]]
    project: str | None
    taken: float


def _clip_item(item: dict[str, Any]) -> dict[str, Any]:
    out = dict(item)
    for k in ("designator", "comment", "library_ref", "footprint", "sheet"):
        if isinstance(out.get(k), str):
            out[k] = safety.clip(out[k])
    if isinstance(out.get("parameters"), dict):
        out["parameters"] = {safety.clip(str(k), 64): safety.clip(str(v)) for k, v in out["parameters"].items()}
    return out


def _clip_sheets(sheets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"name": safety.clip(str(s.get("name", "")), 100), "open": bool(s.get("open")), "modified": bool(s.get("modified"))}
        for s in sheets
    ]


class AltiumService(WriteMixin):
    def __init__(self, config: Config, bridge: Bridge):
        self.config = config
        self.bridge = bridge
        self._lock = threading.RLock()
        self._snap: Snapshot | None = None

    # -- snapshot cache ----------------------------------------------------
    def invalidate(self) -> None:
        self._snap = None

    def snapshot(self, refresh: bool = False) -> Snapshot:
        with self._lock:
            ttl = self.config.cache_ttl_s
            if not refresh and self._snap and ttl > 0 and time.monotonic() - self._snap.taken < ttl:
                return self._snap
            resp = self.bridge.call("get_components", {"include_pins": False})
            rows = [c for c in resp.get("components", []) if isinstance(c, dict)]
            self._snap = Snapshot(
                rows=rows,
                sheets=[s for s in resp.get("sheets", []) if isinstance(s, dict)],
                project=resp.get("project_name"),
                taken=time.monotonic(),
            )
            return self._snap

    # -- status ------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        warnings = list(self.config.warnings)
        data: dict[str, Any] = {
            "server_version": __version__,
            "mode": self.config.mode,
            "altium": {
                "exe_path": str(self.bridge.exe_path) if self.bridge.exe_path else None,
                "version": None,
                "running": self.bridge.running(),
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
            if err.code == "E_ALTIUM_NOT_FOUND":
                data["altium"]["running"] = False
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
        warnings.extend(self.bridge.startup_warnings())
        return data

    # -- reads -------------------------------------------------------------
    def list_components(
        self,
        limit: int = safety.DEFAULT_LIST_LIMIT,
        offset: int = 0,
        designator_prefix: str | None = None,
        missing_parameter: str | None = None,
        refresh: bool = False,
    ) -> dict[str, Any]:
        safety.check_limit_offset(limit, offset)
        if missing_parameter is not None:
            safety.check_parameter_name(missing_parameter)
        rows = self.snapshot(refresh).rows
        if designator_prefix:
            p = designator_prefix.lower()
            rows = [r for r in rows if str(r.get("designator", "")).lower().startswith(p)]
        if missing_parameter:
            rows = [r for r in rows if not (analysis.param(r, missing_parameter)[1] or "").strip()]
        rows = sorted(rows, key=analysis.sort_key)
        return self._page(rows, limit, offset)

    @staticmethod
    def _page(rows: list[dict[str, Any]], limit: int, offset: int) -> dict[str, Any]:
        items = []
        for r in rows[offset : offset + limit]:
            item = _clip_item(r)
            item.pop("parameters", None)
            item.pop("pins", None)
            items.append(item)
        return {"total": len(rows), "items": items, "truncated": offset + limit < len(rows)}

    def get_component(self, designators: list[str], include_pins: bool = False, refresh: bool = False) -> dict[str, Any]:
        if not 1 <= len(designators) <= safety.MAX_GET_DESIGNATORS:
            raise AltiumError(E_INVALID_INPUT, f"Provide 1 to {safety.MAX_GET_DESIGNATORS} designators.")
        wanted = list(dict.fromkeys(safety.check_designator(d) for d in designators))
        if include_pins:
            resp = self.bridge.call("get_components", {"designator": wanted, "include_pins": True})
            rows = [c for c in resp.get("components", []) if isinstance(c, dict)]
        else:
            rows = self.snapshot(refresh).rows
        found: dict[str, dict[str, Any]] = {}
        for r in rows:
            found.setdefault(str(r.get("designator", "")).upper(), r)
        items = [_clip_item(found[d.upper()]) for d in wanted if d.upper() in found]
        return {"items": items, "not_found": [d for d in wanted if d.upper() not in found]}

    # -- analysis (no extra Altium work beyond the cached snapshot) ---------
    def find_components(
        self,
        query: str,
        field: str = "any",
        match: str = "contains",
        designator_prefix: str | None = None,
        missing_parameter: str | None = None,
        limit: int = safety.DEFAULT_LIST_LIMIT,
        offset: int = 0,
        refresh: bool = False,
    ) -> dict[str, Any]:
        safety.check_limit_offset(limit, offset)
        safety.check_query(query)
        safety.check_field(field)
        if match not in ("contains", "exact", "wildcard"):
            raise AltiumError(E_INVALID_INPUT, "match must be contains, exact or wildcard (* and ?).")
        if missing_parameter is not None:
            safety.check_parameter_name(missing_parameter)
        rows = analysis.find(self.snapshot(refresh).rows, query, field, match, designator_prefix, missing_parameter)
        return self._page(rows, limit, offset)

    def bom_summary(
        self, group_by: list[str] | None = None, as_csv: bool = False, limit: int = safety.DEFAULT_LIST_LIMIT, refresh: bool = False
    ) -> dict[str, Any]:
        group_by = [safety.check_group_field(g) for g in (group_by or DEFAULT_GROUP_BY)]
        if not 1 <= len(group_by) <= 5:
            raise AltiumError(E_INVALID_INPUT, "group_by needs 1 to 5 fields.")
        if not 1 <= limit <= safety.MAX_LIST_LIMIT:
            raise AltiumError(E_INVALID_INPUT, f"limit must be between 1 and {safety.MAX_LIST_LIMIT}.")
        rows = self.snapshot(refresh).rows
        groups = analysis.bom_summary(rows, group_by)
        for g in groups:
            g["key"] = {k: safety.clip(v) for k, v in g["key"].items()}
        data: dict[str, Any] = {
            "group_by": group_by,
            "component_count": len(rows),
            "group_count": len(groups),
            "groups": groups[:limit],
            "truncated": len(groups) > limit,
        }
        if as_csv:
            data["csv"] = analysis.bom_csv(groups[:limit], group_by)
        return data

    def check_parameters(
        self, required: list[str], group_by: list[str] | None = None, refresh: bool = False
    ) -> dict[str, Any]:
        if not 1 <= len(required) <= 20:
            raise AltiumError(E_INVALID_INPUT, "Provide 1 to 20 parameter names.")
        names = [safety.check_parameter_name(n) for n in required]
        group_by = [safety.check_group_field(g) for g in (group_by or DEFAULT_GROUP_BY)]
        rows = self.snapshot(refresh).rows
        return {
            "component_count": len(rows),
            "group_by": group_by,
            "parameters": analysis.check_parameters(rows, names, group_by),
        }

    def check_designators(self, refresh: bool = False) -> dict[str, Any]:
        return analysis.check_designators(self.snapshot(refresh).rows)

    def project_overview(self, refresh: bool = False) -> dict[str, Any]:
        snap = self.snapshot(refresh)
        data = analysis.overview(snap.rows, _clip_sheets(snap.sheets), snap.project and safety.clip(str(snap.project)))
        return data

    def get_nets(self, designators: list[str]) -> dict[str, Any]:
        res = self.get_component(designators, include_pins=True)
        return {"nets": analysis.nets_from_components(res["items"]), "not_found": res["not_found"]}

    def compile_messages(
        self, limit: int = safety.DEFAULT_LIST_LIMIT, severity: str | None = None
    ) -> dict[str, Any]:
        if not 1 <= limit <= safety.MAX_LIST_LIMIT:
            raise AltiumError(E_INVALID_INPUT, f"limit must be between 1 and {safety.MAX_LIST_LIMIT}.")
        resp = self.bridge.call("compile_messages", {})
        msgs = [
            {
                "severity": safety.clip(str(m.get("severity", "")), 20),
                "text": safety.clip(str(m.get("text", ""))),
                "document": safety.clip(str(m.get("document", "")), 100),
            }
            for m in resp.get("messages", [])
            if isinstance(m, dict)
        ]
        counts: dict[str, int] = {}
        for m in msgs:
            counts[m["severity"]] = counts.get(m["severity"], 0) + 1
        if severity:
            msgs = [m for m in msgs if m["severity"].lower() == severity.lower()]
        return {"counts": counts, "total": len(msgs), "items": msgs[:limit], "truncated": len(msgs) > limit}
