"""Write operations. All of them: refused unless the server mode allows it, preview by
default, read back after applying, never save (except altium_save_project)."""

from __future__ import annotations

from typing import Any

from . import analysis, safety
from .models import E_BRIDGE_WEDGED, E_INVALID_INPUT, AltiumError

IU_PER_MIL = 10000
EDIT_NOTE = (
    "Edits are in memory only: the sheet is modified but NOT saved. "
    "Press Ctrl+Z in Altium to undo (once per affected sheet, and once per batch of {chunk} changes). "
    "The PCB is not updated until you run Update PCB."
).format(chunk=safety.BRIDGE_CHUNK)


class WriteMixin:
    # Provided by AltiumService
    config: Any
    bridge: Any

    # -- shared plumbing ---------------------------------------------------
    def _begin_write(self, apply: bool) -> None:
        safety.require_writable(self.config)
        if apply and self.bridge.suspect_wedged:
            raise AltiumError(
                E_BRIDGE_WEDGED, "A previous call timed out; writes are blocked until Altium answers a read."
            )

    def _fresh(self):
        """Fresh snapshot plus lookup maps."""
        snap = self.snapshot(refresh=True)  # type: ignore[attr-defined]
        by_des: dict[str, dict[str, Any]] = {}
        for r in snap.rows:
            by_des.setdefault(str(r.get("designator", "")).upper(), r)
        sheet_open = {str(s.get("name")): bool(s.get("open")) for s in snap.sheets}
        return snap, by_des, sheet_open

    @staticmethod
    def _closed(comp: dict[str, Any], sheet_open: dict[str, bool]) -> str | None:
        sheet = str(comp.get("sheet") or "")
        if sheet and sheet_open.get(sheet) is False:
            return f"Sheet {safety.clip(sheet, 60)} is not open in Altium; open it first."
        return None

    def _send(self, command: str, items: list[dict[str, Any]], key_fields: tuple[str, ...], extra: dict[str, Any]) -> dict[tuple, Any]:
        statuses: dict[tuple, Any] = {}
        for i in range(0, len(items), safety.BRIDGE_CHUNK):
            resp = self.bridge.call(command, {"change": items[i : i + safety.BRIDGE_CHUNK], **extra})
            for x in resp.get("results", []):
                statuses[tuple(str(x.get(f, "")).lower() for f in key_fields)] = x.get("status")
        return statuses

    def _finish(self, rows: list[dict[str, Any]], applied: bool, verified: bool | None, preview_note: str) -> dict[str, Any]:
        snap = self.snapshot()  # type: ignore[attr-defined]
        return {
            "changes": rows,
            "applied": applied,
            "verified": verified,
            "sheets_modified": [str(s.get("name")) for s in snap.sheets if s.get("modified")],
            "note": EDIT_NOTE if applied else preview_note,
        }

    @staticmethod
    def _validate_changes(changes: list[dict[str, str]], cap: int) -> list[dict[str, str]]:
        if not 1 <= len(changes) <= cap:
            raise AltiumError(E_INVALID_INPUT, f"Provide 1 to {cap} changes.")
        clean, seen = [], set()
        for ch in changes:
            des = safety.check_designator(ch.get("designator", ""))
            name = safety.check_parameter_name(ch.get("name", ""))
            value = safety.check_value(ch.get("value", ""))
            key = (des.upper(), name.lower())
            if key in seen:
                raise AltiumError(E_INVALID_INPUT, f"Duplicate change for {des} / {name}.")
            seen.add(key)
            clean.append({"designator": des, "name": name, "value": value})
        return clean

    # -- set parameter -----------------------------------------------------
    def set_parameter(
        self,
        changes: list[dict[str, str]],
        apply: bool = False,
        create_if_missing: bool = False,
        max_changes: int = safety.MAX_CHANGES,
    ) -> dict[str, Any]:
        self._begin_write(apply)
        clean = self._validate_changes(changes, max_changes)
        with self._lock:  # type: ignore[attr-defined]
            _, current, sheet_open = self._fresh()
            rows: list[dict[str, Any]] = []
            for ch in clean:
                row: dict[str, Any] = {"designator": ch["designator"], "name": ch["name"], "old": None, "new": ch["value"]}
                comp = current.get(ch["designator"].upper())
                if comp is None:
                    row.update(status="not_found", reason="No such component in the project.")
                elif safety.is_reserved(ch["name"]):
                    row.update(status="refused", reason="Reserved parameter; not editable in this version.")
                elif (closed := self._closed(comp, sheet_open)) is not None:
                    row.update(status="refused", reason=closed)
                else:
                    actual, old = analysis.param(comp, ch["name"])
                    row["old"] = old
                    if actual is None and not create_if_missing:
                        row.update(status="refused", reason="Parameter does not exist; pass create_if_missing=true to add it.")
                    elif actual is not None and old == ch["value"]:
                        row.update(status="no_change")
                    else:
                        row.update(status="ok")
                rows.append(row)

            to_write = [r for r in rows if r["status"] == "ok"]
            if not apply:
                return self._finish(
                    rows, False, None,
                    "Preview only. Nothing was changed in Altium. Call again with apply=true to write.",
                )
            verified = None
            if to_write:
                statuses = self._send(
                    "set_parameters",
                    [{"designator": r["designator"], "name": r["name"], "value": r["new"]} for r in to_write],
                    ("designator", "name"),
                    {"create_if_missing": create_if_missing},
                )
                _, after, _ = self._fresh()
                for r in to_write:
                    st = statuses.get((r["designator"].lower(), r["name"].lower()))
                    if st != "ok":
                        r.update(status="error", reason=f"Altium reported status {st!r}.", verified=False)
                        continue
                    r["verified"] = analysis.param(after.get(r["designator"].upper(), {}), r["name"])[1] == r["new"]
                verified = all(r.get("verified") for r in to_write)
            for r in rows:
                r.setdefault("verified", None)
            return self._finish(rows, bool(to_write), verified, "Nothing needed writing; no changes were applied.")

    def set_parameters_from_table(self, csv_text: str, apply: bool = False, create_if_missing: bool = False) -> dict[str, Any]:
        safety.require_writable(self.config)
        changes = analysis.parse_table_csv(csv_text)
        return self.set_parameter(changes, apply, create_if_missing, max_changes=safety.MAX_BULK_CHANGES)

    # -- rename / delete parameter ----------------------------------------
    def _targets(self, name: str, designators: list[str] | None, current: dict[str, dict[str, Any]]) -> list[str]:
        if designators:
            if len(designators) > safety.MAX_BULK_CHANGES:
                raise AltiumError(E_INVALID_INPUT, f"At most {safety.MAX_BULK_CHANGES} designators.")
            return list(dict.fromkeys(safety.check_designator(d) for d in designators))
        found = [str(r["designator"]) for r in current.values() if analysis.param(r, name)[0] is not None]
        if len(found) > safety.MAX_BULK_CHANGES:
            raise AltiumError(
                E_INVALID_INPUT,
                f"{len(found)} components have {name!r}; pass designators to narrow it to {safety.MAX_BULK_CHANGES} or fewer.",
            )
        return sorted(found, key=analysis.natural)

    def rename_parameter(
        self, old_name: str, new_name: str, designators: list[str] | None = None, apply: bool = False
    ) -> dict[str, Any]:
        self._begin_write(apply)
        safety.check_parameter_name(old_name)
        safety.check_parameter_name(new_name)
        if old_name.lower() == new_name.lower():
            raise AltiumError(E_INVALID_INPUT, "old_name and new_name are the same.")
        if safety.is_reserved(old_name) or safety.is_reserved(new_name):
            raise AltiumError(E_INVALID_INPUT, "Reserved parameters cannot be renamed.")
        with self._lock:  # type: ignore[attr-defined]
            _, current, sheet_open = self._fresh()
            rows = []
            for des in self._targets(old_name, designators, current):
                row: dict[str, Any] = {"designator": des, "old_name": old_name, "new_name": new_name, "value": None}
                comp = current.get(des.upper())
                if comp is None:
                    row.update(status="not_found", reason="No such component in the project.")
                elif (closed := self._closed(comp, sheet_open)) is not None:
                    row.update(status="refused", reason=closed)
                else:
                    actual, val = analysis.param(comp, old_name)
                    row["value"] = val
                    if actual is None:
                        row.update(status="refused", reason="Parameter does not exist on this component.")
                    elif analysis.param(comp, new_name)[0] is not None:
                        row.update(status="refused", reason="A parameter with the new name already exists.")
                    else:
                        row.update(status="ok")
                rows.append(row)
            return self._apply_simple(
                rows, apply, "rename_parameters",
                lambda r: {"designator": r["designator"], "name": r["old_name"], "new_name": r["new_name"]},
                lambda r, after: analysis.param(after, r["new_name"])[0] is not None and analysis.param(after, r["old_name"])[0] is None,
            )

    def delete_parameter(self, name: str, designators: list[str] | None = None, apply: bool = False) -> dict[str, Any]:
        self._begin_write(apply)
        safety.check_parameter_name(name)
        if safety.is_reserved(name):
            raise AltiumError(E_INVALID_INPUT, "Reserved parameters cannot be deleted.")
        with self._lock:  # type: ignore[attr-defined]
            _, current, sheet_open = self._fresh()
            rows = []
            for des in self._targets(name, designators, current):
                row: dict[str, Any] = {"designator": des, "name": name, "old": None}
                comp = current.get(des.upper())
                if comp is None:
                    row.update(status="not_found", reason="No such component in the project.")
                elif (closed := self._closed(comp, sheet_open)) is not None:
                    row.update(status="refused", reason=closed)
                else:
                    actual, val = analysis.param(comp, name)
                    row["old"] = val
                    if actual is None:
                        row.update(status="no_change", reason="Parameter does not exist on this component.")
                    else:
                        row.update(status="ok")
                rows.append(row)
            return self._apply_simple(
                rows, apply, "delete_parameters",
                lambda r: {"designator": r["designator"], "name": r["name"]},
                lambda r, after: analysis.param(after, r["name"])[0] is None,
            )

    def _apply_simple(self, rows, apply, command, to_item, verify) -> dict[str, Any]:
        to_write = [r for r in rows if r["status"] == "ok"]
        if not apply:
            return self._finish(rows, False, None, "Preview only. Nothing was changed in Altium. Call again with apply=true to write.")
        verified = None
        if to_write:
            name_key = "old_name" if "old_name" in to_write[0] else "name"
            statuses = self._send(command, [to_item(r) for r in to_write], ("designator", "name"), {})
            _, after, _ = self._fresh()
            for r in to_write:
                st = statuses.get((r["designator"].lower(), r[name_key].lower()))
                if st != "ok":
                    r.update(status="error", reason=f"Altium reported status {st!r}.", verified=False)
                else:
                    r["verified"] = bool(verify(r, after.get(r["designator"].upper(), {})))
            verified = all(r.get("verified") for r in to_write)
        for r in rows:
            r.setdefault("verified", None)
        return self._finish(rows, bool(to_write), verified, "Nothing needed writing; no changes were applied.")

    # -- move components (PCB) --------------------------------------------
    def move_components(self, changes: list[dict[str, Any]], apply: bool = False) -> dict[str, Any]:
        self._begin_write(apply)
        if not 1 <= len(changes) <= safety.MAX_CHANGES:
            raise AltiumError(E_INVALID_INPUT, f"Provide 1 to {safety.MAX_CHANGES} changes.")
        plan, seen = [], set()
        for ch in changes:
            des = safety.check_designator(ch.get("designator", ""))
            if des.upper() in seen:
                raise AltiumError(E_INVALID_INPUT, f"Duplicate change for {des}.")
            seen.add(des.upper())
            rel = [ch.get("dx_mil"), ch.get("dy_mil")]
            ab = [ch.get("x_mil"), ch.get("y_mil")]
            rot = ch.get("rotation_deg")
            if any(v is not None for v in rel) and any(v is not None for v in ab):
                raise AltiumError(E_INVALID_INPUT, f"{des}: use either dx/dy (relative) or x/y (absolute), not both.")
            if all(v is None for v in rel + ab) and rot is None:
                raise AltiumError(E_INVALID_INPUT, f"{des}: give a position change or a rotation.")
            for label, v in zip(("dx_mil", "dy_mil", "x_mil", "y_mil"), rel + ab):
                if v is not None:
                    safety.check_mil(v, f"{des} {label}")
            if rot is not None:
                safety.check_mil(rot, f"{des} rotation_deg")
                if not 0 <= rot < 360:
                    raise AltiumError(E_INVALID_INPUT, f"{des}: rotation_deg must be 0 to <360.")
            plan.append((des, rel, ab, rot))

        with self._lock:  # type: ignore[attr-defined]
            resp = self.bridge.call("get_positions", {"designator": [p[0] for p in plan]})
            pos = {str(p["designator"]).upper(): p for p in resp.get("positions", [])}
            rows, targets = [], []
            for des, rel, ab, rot in plan:
                cur = pos.get(des.upper())
                row: dict[str, Any] = {"designator": des, "old": None, "new": None}
                if cur is None:
                    row.update(status="not_found", reason="Component not found on the open PCB.")
                    rows.append(row)
                    continue
                x, y, r = int(cur["x_iu"]), int(cur["y_iu"]), int(cur["rotation_cd"])
                nx, ny = x, y
                if rel[0] is not None or rel[1] is not None:
                    nx, ny = x + round((rel[0] or 0) * IU_PER_MIL), y + round((rel[1] or 0) * IU_PER_MIL)
                elif ab[0] is not None or ab[1] is not None:
                    nx = round(ab[0] * IU_PER_MIL) if ab[0] is not None else x
                    ny = round(ab[1] * IU_PER_MIL) if ab[1] is not None else y
                nr = round(rot * 100) if rot is not None else r
                row["old"] = _pos_dict(x, y, r)
                row["new"] = _pos_dict(nx, ny, nr)
                row["status"] = "no_change" if (nx, ny, nr) == (x, y, r) else "ok"
                rows.append(row)
                targets.append((row, {"designator": des, "x_iu": nx, "y_iu": ny, "rotation_cd": nr}))

            to_write = [(r, t) for r, t in targets if r["status"] == "ok"]
            if not apply:
                return {
                    "changes": rows, "applied": False, "verified": None,
                    "note": "Preview only. Nothing was moved. Positions are mil relative to the board origin. Call again with apply=true.",
                }
            verified = None
            if to_write:
                statuses = self._send("move_components", [t for _, t in to_write], ("designator",), {})
                after = {
                    str(p["designator"]).upper(): p
                    for p in self.bridge.call("get_positions", {"designator": [t["designator"] for _, t in to_write]}).get("positions", [])
                }
                for r, t in to_write:
                    if statuses.get((r["designator"].lower(),)) != "ok":
                        r.update(status="error", reason="Altium did not confirm the move.", verified=False)
                        continue
                    a = after.get(r["designator"].upper(), {})
                    r["verified"] = (a.get("x_iu"), a.get("y_iu"), a.get("rotation_cd")) == (t["x_iu"], t["y_iu"], t["rotation_cd"])
                verified = all(r.get("verified") for r, _ in to_write)
            for r in rows:
                r.setdefault("verified", None)
            return {
                "changes": rows, "applied": bool(to_write), "verified": verified,
                "note": "Moves are in memory on the open PCB and NOT saved. Press Ctrl+Z in Altium to undo (once per batch of "
                f"{safety.BRIDGE_CHUNK}).",
            }

    # -- save --------------------------------------------------------------
    def save_project(self, confirm: bool = False) -> dict[str, Any]:
        self._begin_write(confirm)
        safety.require_save(self.config)
        with self._lock:  # type: ignore[attr-defined]
            snap = self.snapshot(refresh=True)  # type: ignore[attr-defined]
            pending = [str(s["name"]) for s in snap.sheets if s.get("open") and s.get("modified")]
            if not confirm:
                return {
                    "saved": [], "would_save": pending, "verified": None,
                    "note": "Preview only; nothing was saved. Call again with confirm=true to save these open, modified sheets.",
                }
            if not pending:
                return {"saved": [], "would_save": [], "verified": True, "note": "Nothing to save."}
            resp = self.bridge.call("save_project", {})
            saved = [str(x) for x in resp.get("saved", [])]
            failed = [str(x) for x in resp.get("failed", [])]
            still = {str(s["name"]) for s in self.snapshot(refresh=True).sheets if s.get("modified")}  # type: ignore[attr-defined]
            return {
                "saved": saved, "failed": failed, "would_save": pending,
                "verified": not (set(saved) & still) and not failed,
                "note": "Saved to disk. This cannot be undone with Ctrl+Z.",
            }


def _pos_dict(x: int, y: int, r: int) -> dict[str, float]:
    return {"x_mil": round(x / IU_PER_MIL, 4), "y_mil": round(y / IU_PER_MIL, 4), "rotation_deg": round(r / 100, 2)}
