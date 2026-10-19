"""Pure functions over component rows. No Altium access."""

from __future__ import annotations

import csv
import fnmatch
import io
import re
from collections import Counter, defaultdict
from typing import Any

from . import safety

Row = dict[str, Any]


def natural(s: str) -> list[Any]:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def sort_key(row: Row) -> list[Any]:
    return natural(str(row.get("designator", "")))


def param(row: Row, name: str) -> tuple[str | None, str | None]:
    """Case-insensitive parameter lookup -> (actual_name, value)."""
    for k, v in (row.get("parameters") or {}).items():
        if k.lower() == name.lower():
            return k, v
    return None, None


def field_value(row: Row, field: str) -> str:
    if field.startswith("parameter:"):
        return (param(row, field[len("parameter:") :])[1]) or ""
    return str(row.get(field) or "")


def _matches(value: str, query: str, match: str) -> bool:
    v, q = value.lower(), query.lower()
    if match == "exact":
        return v == q
    if match == "wildcard":
        return fnmatch.fnmatchcase(v, q)
    return q in v


def find(
    rows: list[Row],
    query: str,
    field: str = "any",
    match: str = "contains",
    designator_prefix: str | None = None,
    missing_parameter: str | None = None,
) -> list[Row]:
    out = []
    for r in rows:
        if designator_prefix and not str(r.get("designator", "")).lower().startswith(designator_prefix.lower()):
            continue
        if missing_parameter and (param(r, missing_parameter)[1] or "").strip():
            continue
        if field == "any":
            hay = [field_value(r, f) for f in ("designator", "comment", "library_ref", "footprint", "sheet")]
            hay += [str(v) for v in (r.get("parameters") or {}).values()]
            hit = any(_matches(h, query, match) for h in hay)
        else:
            hit = _matches(field_value(r, field), query, match)
        if hit:
            out.append(r)
    return sorted(out, key=sort_key)


def bom_summary(rows: list[Row], group_by: list[str]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for r in rows:
        groups[tuple(field_value(r, f) for f in group_by)].append(str(r.get("designator", "")))
    out = []
    for key, dess in groups.items():
        dess.sort(key=natural)
        out.append(
            {"key": dict(zip(group_by, key)), "quantity": len(dess), "designators": dess}
        )
    out.sort(key=lambda g: natural(g["designators"][0]))
    return out


def _csv_cell(v: Any) -> str:
    s = str(v)
    # Design text is untrusted: neutralise spreadsheet formula injection.
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def bom_csv(groups: list[dict[str, Any]], group_by: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(list(group_by) + ["Quantity", "Designators"])
    for g in groups:
        w.writerow([_csv_cell(g["key"][f]) for f in group_by] + [g["quantity"], _csv_cell(" ".join(g["designators"]))])
    return buf.getvalue()


def check_parameters(
    rows: list[Row], required: list[str], group_by: list[str], cap: int = 200
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in required:
        missing = sorted(
            (str(r["designator"]) for r in rows if not (param(r, name)[1] or "").strip()), key=natural
        )
        groups: dict[tuple[str, ...], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for r in rows:
            val = (param(r, name)[1] or "").strip()
            if val:
                groups[tuple(field_value(r, f) for f in group_by)][val].append(str(r["designator"]))
        inconsistent = []
        for key, vals in groups.items():
            if len(vals) > 1:
                inconsistent.append(
                    {
                        "group": dict(zip(group_by, key)),
                        "values": {v: sorted(d, key=natural) for v, d in sorted(vals.items())},
                    }
                )
        result[name] = {
            "missing_count": len(missing),
            "missing": missing[:cap],
            "missing_truncated": len(missing) > cap,
            "inconsistent": inconsistent[:50],
            "inconsistent_truncated": len(inconsistent) > 50,
        }
    return result


_UNANNOTATED_RE = re.compile(r"\?")
_SPLIT_RE = re.compile(r"^([A-Za-z_]+)(\d+)$")


def check_designators(rows: list[Row], cap: int = 50) -> dict[str, Any]:
    counts = Counter(str(r.get("designator", "")).upper() for r in rows)
    duplicates = sorted((d for d, n in counts.items() if n > 1), key=natural)
    unannotated = sorted((str(r["designator"]) for r in rows if _UNANNOTATED_RE.search(str(r["designator"]))), key=natural)
    nums: dict[str, set[int]] = defaultdict(set)
    for d in counts:
        m = _SPLIT_RE.match(d)
        if m:
            nums[m.group(1)].add(int(m.group(2)))
    gaps = {}
    for prefix, have in sorted(nums.items()):
        missing = [n for n in range(min(have), max(have) + 1) if n not in have]
        if missing:
            gaps[prefix] = {"missing_numbers": missing[:cap], "truncated": len(missing) > cap}
    return {
        "duplicates": duplicates[:cap],
        "unannotated": unannotated[:cap],
        "gaps": gaps,
        "note": "Gaps are informational (numbers missing between the lowest and highest used).",
    }


def overview(rows: list[Row], sheets: list[dict[str, Any]], project: str | None, top: int = 20) -> dict[str, Any]:
    prefixes = Counter(re.match(r"[A-Za-z_]*", str(r["designator"])).group(0).upper() or "?" for r in rows)
    footprints = Counter(str(r.get("footprint") or "") or "(none)" for r in rows)
    per_sheet = Counter(str(r.get("sheet") or "") or "(unknown)" for r in rows)
    return {
        "project_name": project,
        "component_count": len(rows),
        "by_prefix": dict(prefixes.most_common()),
        "top_footprints": dict(footprints.most_common(top)),
        "components_per_sheet": dict(per_sheet.most_common()),
        "sheets": sheets,
    }


def nets_from_components(items: list[Row]) -> list[dict[str, Any]]:
    nets: dict[str, list[str]] = defaultdict(list)
    for it in items:
        for p in it.get("pins") or []:
            net = str(p.get("net") or "")
            if net:
                nets[net].append(f"{it['designator']}.{p.get('number', '?')}")
    return [
        {"net": n, "pins": sorted(pins, key=natural)} for n, pins in sorted(nets.items(), key=lambda kv: natural(kv[0]))
    ]


def parse_table_csv(text: str) -> list[dict[str, str]]:
    """CSV with a Designator column; other columns are parameter names."""
    from .models import E_INVALID_INPUT, AltiumError

    if len(text.encode("utf-8", errors="replace")) > safety.MAX_CSV_BYTES:
        raise AltiumError(E_INVALID_INPUT, f"CSV is larger than {safety.MAX_CSV_BYTES} bytes.")
    reader = csv.reader(io.StringIO(text))
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        raise AltiumError(E_INVALID_INPUT, "CSV is empty.") from None
    lower = [h.lower() for h in header]
    if "designator" not in lower:
        raise AltiumError(E_INVALID_INPUT, "CSV needs a 'Designator' column.")
    di = lower.index("designator")
    changes = []
    for lineno, row in enumerate(reader, start=2):
        if not row or not any(c.strip() for c in row):
            continue
        if len(row) != len(header):
            raise AltiumError(E_INVALID_INPUT, f"CSV line {lineno} has {len(row)} columns, expected {len(header)}.")
        for i, name in enumerate(header):
            if i == di or not name or row[i] == "":
                continue  # empty cell: leave the parameter alone
            changes.append({"designator": row[di].strip(), "name": name, "value": row[i]})
    return changes
