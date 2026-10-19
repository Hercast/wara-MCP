# Technical reference

Details for people who want to know exactly what the server does. For setup and a quick tour, see the [README](../README.md).

## Tools

**Read and audit** (always available; reads use a 5 s cache, pass `refresh=true` to re-read):

| Tool | What it does |
|---|---|
| `altium_status` | Server mode, Altium version, open project, problems and how to fix them. Works when Altium is closed. |
| `altium_list_components` | Components of the open project. Filter by designator prefix or a missing parameter (e.g. `MPN`). Paged (default 200, max 500). |
| `altium_get_component` | Details and all parameters for 1 to 25 designators, optionally with pins and nets. |
| `altium_find_components` | Search by text, wildcard or exact match in any field or a parameter. |
| `altium_bom_summary` | BOM grouped by comment/footprint/library ref/parameter, with quantities. Optional CSV. Also the `altium://bom` resource. |
| `altium_check_parameters` | Missing/blank required parameters, and groups with conflicting values. |
| `altium_check_designators` | Duplicate and unannotated (`R?`) designators, numbering gaps. |
| `altium_project_overview` | Counts by prefix, footprint and sheet; which sheets are open or modified. |
| `altium_get_nets` | Nets on the pins of given components. |
| `altium_compile_messages` | The project's compile errors and warnings (does not run ERC/DRC). |

**Edit** (need `read_write` mode; preview by default, `apply=true` writes, read-back verified, never saved):

| Tool | What it does |
|---|---|
| `altium_set_parameter` | Set parameters on up to 50 components. |
| `altium_set_parameters_from_table` | Bulk set from CSV text (Designator column + one column per parameter), up to 500 cells. |
| `altium_rename_parameter` | Rename a parameter on given components or everywhere. |
| `altium_delete_parameter` | Delete a parameter on given components or everywhere (old values shown in the preview). |
| `altium_move_components` | Move/rotate components on the open PCB (relative or absolute, in mil). |

**Save** (needs `read_write_save` mode): `altium_save_project`. `confirm=false` only lists what would be saved.

**Prompts:** `fill_missing_mpns` (never invents MPNs, previews before applying) and `audit_bom`.

## Configuration

Set these in the MCP server's environment (the `env` block in the client config).

| Variable | Default | Meaning |
|---|---|---|
| `ALTIUM_LITE_MODE` | `read_only` | `read_only`, `read_write` or `read_write_save` |
| `ALTIUM_LITE_BRIDGE` | `altium` | `fake` for the built-in demo design |
| `ALTIUM_LITE_EXE` | auto-detected | Full path to Altium's `X2.EXE` (default search: `C:\Program Files\Altium\AD*\`) |
| `ALTIUM_LITE_EXCHANGE_DIR` | `%PROGRAMDATA%\altium_lite_mcp\<user>` | Folder for request/response files and the log. Locked down to your user on first use. Keep it free of spaces. |
| `ALTIUM_LITE_TIMEOUT` | `60` | Seconds to wait for Altium |
| `ALTIUM_LITE_CACHE_TTL` | `5` | Seconds a read snapshot is reused (`0` disables) |

## How it works

Altium has no supported external API, so the server drives it the way other open-source Altium tools do: it writes a request file, launches a small DelphiScript project inside Altium with `X2.EXE -RScriptingSystem:RunScript(...)`, and reads the JSON response the script writes back. One request at a time. Requests are plain `key=value` lines (ASCII-escaped); responses are JSON. Only integers cross the wire for coordinates and angles.

```
MCP client (Claude, ...)  --stdio-->  altium-lite-mcp (Python)
                                         |  request file + X2.EXE -R...
                                         v
                                   Altium Designer (DelphiScript project)
```

## Safety model

- **Read-only by default**; writes need `ALTIUM_LITE_MODE=read_write`, set outside the model's reach.
- **Preview before apply.** Applied edits are read back and reported as `verified`.
- **Never saves by default.** Edits stay in memory in Altium. Review, then save or press Ctrl+Z (once per affected sheet, and once per batch of 50 changes). Saving needs `read_write_save` and `confirm=true`.
- **Per-user exchange folder.** Requests decide what runs inside Altium, so the folder is restricted to your user. The server never launches Altium itself: if `X2.EXE` is not running, calls fail fast.
- **Design text is untrusted.** Component names, comments and values come from your files and may contain instructions aimed at the model. They are returned as data and length-limited.
- **Your design data goes to your AI client** like any tool output. Do not use this with confidential designs unless that is acceptable to you.
- Reserved parameters (`Designator`, `LibReference`, `Comment`, footprint and model links) cannot be edited. Parameters are only created with `create_if_missing=true`.
- A script error or modal dialog in Altium can stall the bridge. The server times out, blocks further writes and tells you how to recover ([TROUBLESHOOTING.md](TROUBLESHOOTING.md)).

## Limits

- Windows and one running Altium instance only.
- Only components of the **compiled project** are read; only schematic parameters are written (plus PCB moves). The PCB is not updated until you run *Update PCB*.
- Sheets must be **open in Altium** to be edited; edits to closed sheets are refused with a reason. PCB moves act on the focused PCB document.
- Text values: at most 255 characters, characters up to U+00FF only.
- Altium's licence or trial terms on scripting have not been reviewed here. Check your own terms.

## Validation status

| Part | State |
|---|---|
| MCP server, tools, safety rules, file protocol | Implemented, covered by automated tests (using a fake Altium) |
| DelphiScript that runs **inside Altium** (`src/altium_lite_mcp/scripts/altium/`) | **Written but never run against a real Altium.** See [ACCEPTANCE.md](ACCEPTANCE.md) |
| Newer tools (`get_nets` pins, `compile_messages`, `delete_parameter`, `move_components`, `save_project`) | Use the least certain Altium API names; expect fixes |
| Altium versions | Intended for 26.x; 25.x best-effort. Nothing verified yet |

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests use a fake bridge and an emulator of the DelphiScript side, so they run anywhere. Work happens on `develop`; `main` gets tagged releases.
