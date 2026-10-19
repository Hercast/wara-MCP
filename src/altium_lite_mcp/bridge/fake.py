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


def sample_design() -> list[dict[str, Any]]:
    def comp(des, comment, ref, fp, sheet, params, pins=None):
        return {
            "designator": des,
            "comment": comment,
            "library_ref": ref,
            "footprint": fp,
            "sheet": sheet,
            "parameters": params,
            "pins": pins or [{"number": "1", "name": "1", "net": "NetA"}, {"number": "2", "name": "2", "net": "GND"}],
        }

    return [
        comp("R1", "10k", "RES", "0603", "Power.SchDoc", {"Value": "10k"}),
        comp("R2", "4k7", "RES", "0603", "Power.SchDoc", {"Value": "4k7", "MPN": ""}),
        comp("R3", "1k", "RES", "0603", "Power.SchDoc", {"Value": "1k"}),
        comp("R4", "100R", "RES", "0603", "MCU.SchDoc", {"Value": "100R", "MPN": "RC0603FR-07100RL"}),
        comp("C1", "100nF", "CAP", "0603", "Power.SchDoc", {"Value": "100nF", "MPN": "CL10B104KB8NNNC"}),
        comp("C2", "10uF", "CAP", "0805", "Power.SchDoc", {"Value": "10uF"}),
        comp("C3", "100nF", "CAP", "0603", "MCU.SchDoc", {"Value": "100nF"}),
        comp("D1", "LED", "LED", "0603", "MCU.SchDoc", {"Color": "Green"}),
        comp("U1", "LDO", "AP2112K", "SOT-23-5", "Power.SchDoc", {"MPN": "AP2112K-3.3TRG1"}),
        comp("U2", "MCU", "STM32G031", "TSSOP-20", "MCU.SchDoc", {"MPN": "STM32G031F6P6"}),
    ]


class FakeBridge(Bridge):
    name = "fake"

    def __init__(self, components: list[dict[str, Any]] | None = None, project: str | None = "Demo.PrjPcb"):
        super().__init__()
        self.components = copy.deepcopy(components if components is not None else sample_design())
        self.project = project
        self.closed = False
        self.hang = False
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.script_version = SCRIPT_VERSION

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
        if command == "get_components":
            return self._get(params)
        if command == "set_parameters":
            return self._set(params)
        raise AltiumError("E_ALTIUM_ERROR", f"Unknown command {command!r}.")

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        wanted = params.get("designator")
        wanted_set = {d.upper() for d in wanted} if wanted else None
        pins = _truthy(params.get("include_pins"))
        items = []
        for c in self.components:
            if wanted_set is not None and c["designator"].upper() not in wanted_set:
                continue
            item = {k: v for k, v in c.items() if k != "pins"}
            item["parameters"] = dict(c["parameters"])
            if pins:
                item["pins"] = copy.deepcopy(c["pins"])
            items.append(item)
        return {"components": items}

    def _set(self, params: dict[str, Any]) -> dict[str, Any]:
        create = _truthy(params.get("create_if_missing"))
        results = []
        for ch in params.get("change") or []:
            comp = next((c for c in self.components if c["designator"].upper() == ch["designator"].upper()), None)
            row = {"designator": ch["designator"], "name": ch["name"]}
            if comp is None:
                results.append({**row, "status": "not_found"})
                continue
            key = next((k for k in comp["parameters"] if k.lower() == ch["name"].lower()), None)
            if key is None and not create:
                results.append({**row, "status": "refused"})
                continue
            key = key or ch["name"]
            comp["parameters"][key] = ch["value"]
            results.append({**row, "status": "ok"})
        return {"results": results, "modified_unsaved": True}


def _truthy(v: Any) -> bool:
    return v is True or (isinstance(v, str) and v.lower() == "true")
