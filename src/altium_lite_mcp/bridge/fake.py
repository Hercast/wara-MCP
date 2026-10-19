"""In-memory stand-in for Altium. Answers the same commands as the DelphiScript.

Used by the tests and by `ALTIUM_LITE_BRIDGE=fake` to try the server in a
client without Altium installed.
"""

from __future__ import annotations

import copy
from typing import Any

from .. import SCRIPT_VERSION
from ..models import E_ALTIUM_NOT_FOUND, E_NO_PROJECT, E_TIMEOUT, AltiumError
from .base import Bridge

IU_PER_MIL = 10000


def sample_design() -> list[dict[str, Any]]:
    def comp(i, des, comment, ref, fp, sheet, params, pins=None):
        return {
            "designator": des,
            "comment": comment,
            "library_ref": ref,
            "footprint": fp,
            "sheet": sheet,
            "parameters": params,
            "pins": pins or [{"number": "1", "name": "1", "net": "NetA"}, {"number": "2", "name": "2", "net": "GND"}],
            "x_iu": i * 100 * IU_PER_MIL,
            "y_iu": 50 * IU_PER_MIL,
            "rotation_cd": 0,
        }

    rows = [
        ("R1", "10k", "RES", "0603", "Power.SchDoc", {"Value": "10k"}),
        ("R2", "4k7", "RES", "0603", "Power.SchDoc", {"Value": "4k7", "MPN": ""}),
        ("R3", "1k", "RES", "0603", "Power.SchDoc", {"Value": "1k"}),
        ("R4", "100R", "RES", "0603", "MCU.SchDoc", {"Value": "100R", "MPN": "RC0603FR-07100RL"}),
        ("C1", "100nF", "CAP", "0603", "Power.SchDoc", {"Value": "100nF", "MPN": "CL10B104KB8NNNC"}),
        ("C2", "10uF", "CAP", "0805", "Power.SchDoc", {"Value": "10uF"}),
        ("C3", "100nF", "CAP", "0603", "MCU.SchDoc", {"Value": "100nF", "MPN": "GRM188R71H104KA93D"}),
        ("D1", "LED", "LED", "0603", "MCU.SchDoc", {"Color": "Green"}),
        ("U1", "LDO", "AP2112K", "SOT-23-5", "Power.SchDoc", {"MPN": "AP2112K-3.3TRG1"}),
        ("U2", "MCU", "STM32G031", "TSSOP-20", "MCU.SchDoc", {"MPN": "STM32G031F6P6"}),
    ]
    return [comp(i, *r) for i, r in enumerate(rows, start=1)]


class FakeBridge(Bridge):
    name = "fake"

    def __init__(self, components: list[dict[str, Any]] | None = None, project: str | None = "Demo.PrjPcb"):
        super().__init__()
        self.components = copy.deepcopy(components if components is not None else sample_design())
        self.project = project
        self.closed = False
        self.hang = False
        self.closed_sheets: set[str] = set()
        self.modified_sheets: set[str] = set()
        self.messages: list[dict[str, str]] = [
            {"severity": "Error", "text": "Duplicate designator R9", "document": "MCU.SchDoc"},
            {"severity": "Warning", "text": "Unconnected pin U2.7", "document": "MCU.SchDoc"},
        ]
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.script_version = SCRIPT_VERSION

    def running(self) -> bool | None:
        return not self.closed

    # -- dispatch ----------------------------------------------------------
    def _call(self, command: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((command, copy.deepcopy(params)))
        if self.closed:
            raise AltiumError(E_ALTIUM_NOT_FOUND, "Altium Designer is not running (fake).")
        if self.hang:
            raise AltiumError(E_TIMEOUT, "No response from Altium within the timeout (fake).")
        if command == "status":
            return {
                "altium_version": "26.11.1 (fake)",
                "script_version": SCRIPT_VERSION,
                "project_name": self.project,
                "project_path": f"C:\\Demo\\{self.project}" if self.project else None,
            }
        if self.project is None:
            raise AltiumError(E_NO_PROJECT, "No project is open in Altium.")
        handler = getattr(self, f"_cmd_{command}", None)
        if handler is None:
            raise AltiumError("E_ALTIUM_ERROR", f"Unknown command {command!r}.")
        return handler(params)

    # -- helpers -----------------------------------------------------------
    def _find(self, des: str) -> dict[str, Any] | None:
        return next((c for c in self.components if c["designator"].upper() == des.upper()), None)

    def _sheets(self) -> list[dict[str, Any]]:
        names = sorted({c["sheet"] for c in self.components})
        return [
            {"name": n, "open": n not in self.closed_sheets, "modified": n in self.modified_sheets} for n in names
        ]

    # -- commands ----------------------------------------------------------
    def _cmd_get_components(self, params: dict[str, Any]) -> dict[str, Any]:
        wanted = params.get("designator")
        wanted_set = {d.upper() for d in wanted} if wanted else None
        pins = _truthy(params.get("include_pins"))
        items = []
        for c in self.components:
            if wanted_set is not None and c["designator"].upper() not in wanted_set:
                continue
            item = {k: v for k, v in c.items() if k not in ("pins", "x_iu", "y_iu", "rotation_cd")}
            item["parameters"] = dict(c["parameters"])
            if pins:
                item["pins"] = copy.deepcopy(c["pins"])
            items.append(item)
        return {"components": items, "sheets": self._sheets(), "project_name": self.project}

    def _cmd_set_parameters(self, params: dict[str, Any]) -> dict[str, Any]:
        create = _truthy(params.get("create_if_missing"))
        results = []
        for ch in params.get("change") or []:
            row = {"designator": ch["designator"], "name": ch["name"]}
            comp = self._find(ch["designator"])
            if comp is None or comp["sheet"] in self.closed_sheets:
                results.append({**row, "status": "not_found"})
                continue
            key = next((k for k in comp["parameters"] if k.lower() == ch["name"].lower()), None)
            if key is None and not create:
                results.append({**row, "status": "refused"})
                continue
            comp["parameters"][key or ch["name"]] = ch["value"]
            self.modified_sheets.add(comp["sheet"])
            results.append({**row, "status": "ok"})
        return {"results": results, "modified_unsaved": True}

    def _cmd_rename_parameters(self, params: dict[str, Any]) -> dict[str, Any]:
        results = []
        for ch in params.get("change") or []:
            row = {"designator": ch["designator"], "name": ch["name"]}
            comp = self._find(ch["designator"])
            key = next((k for k in (comp or {}).get("parameters", {}) if k.lower() == ch["name"].lower()), None)
            if comp is None or key is None or comp["sheet"] in self.closed_sheets:
                results.append({**row, "status": "not_found"})
                continue
            comp["parameters"][ch["new_name"]] = comp["parameters"].pop(key)
            self.modified_sheets.add(comp["sheet"])
            results.append({**row, "status": "ok"})
        return {"results": results}

    def _cmd_delete_parameters(self, params: dict[str, Any]) -> dict[str, Any]:
        results = []
        for ch in params.get("change") or []:
            row = {"designator": ch["designator"], "name": ch["name"]}
            comp = self._find(ch["designator"])
            key = next((k for k in (comp or {}).get("parameters", {}) if k.lower() == ch["name"].lower()), None)
            if comp is None or key is None or comp["sheet"] in self.closed_sheets:
                results.append({**row, "status": "not_found"})
                continue
            del comp["parameters"][key]
            self.modified_sheets.add(comp["sheet"])
            results.append({**row, "status": "ok"})
        return {"results": results}

    def _cmd_get_positions(self, params: dict[str, Any]) -> dict[str, Any]:
        wanted = {d.upper() for d in params.get("designator") or []}
        return {
            "positions": [
                {k: c[k] for k in ("designator", "x_iu", "y_iu", "rotation_cd")}
                for c in self.components
                if c["designator"].upper() in wanted
            ]
        }

    def _cmd_move_components(self, params: dict[str, Any]) -> dict[str, Any]:
        results = []
        for ch in params.get("change") or []:
            comp = self._find(ch["designator"])
            row = {"designator": ch["designator"]}
            if comp is None:
                results.append({**row, "status": "not_found"})
                continue
            comp["x_iu"], comp["y_iu"], comp["rotation_cd"] = int(ch["x_iu"]), int(ch["y_iu"]), int(ch["rotation_cd"])
            results.append({**row, "status": "ok"})
        return {"results": results}

    def _cmd_compile_messages(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"messages": copy.deepcopy(self.messages)}

    def _cmd_save_project(self, params: dict[str, Any]) -> dict[str, Any]:
        saved = sorted(self.modified_sheets - self.closed_sheets)
        self.modified_sheets -= set(saved)
        return {"saved": saved, "failed": []}


def _truthy(v: Any) -> bool:
    return v is True or (isinstance(v, str) and v.lower() == "true")
