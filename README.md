# altium-lite-mcp

> **Experimental.** No support commitment. Unofficial, and not affiliated with or endorsed by Altium.

A small [MCP](https://modelcontextprotocol.io) server that lets Claude **read and audit** the Altium Designer project you have open (components, BOM, parameters, designators, nets) and make **small, reviewable edits**: schematic parameters (such as filling in missing `MPN` values) and PCB component moves. Every edit is previewed first and left unsaved in Altium, so Ctrl+Z undoes it. Saving to disk is a separate, opt-in mode.

```
You: List the components and tell me which have no MPN.
You: Set MPN to ABC-123 on R1 to R3.      -> preview of old/new values
You: Apply it.                             -> written to Altium (unsaved), read back and verified
```

Everything runs on **your Windows machine**: Claude, this server and Altium, connected over stdio. There is no cloud service, no telemetry and no network access from this code.

## Status: what is and isn't tested

| Part | State |
|---|---|
| MCP server, tools, safety rules, file protocol | Implemented, covered by automated tests (using a fake Altium) |
| DelphiScript that runs **inside Altium** (`src/altium_lite_mcp/scripts/altium/`) | **Written but never run against a real Altium.** It still has to be validated on a Windows machine with Altium (see [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)) |
| Altium versions | Intended for 26.x; 25.x best-effort. Nothing verified yet |
| Newer tools (`get_nets` pins, `compile_messages`, `delete_parameter`, `move_components`, `save_project`) | Use the least certain Altium API names; expect them to need fixes first |

Expect to debug the Altium side on first use. The [fake mode](#try-it-without-altium) lets you try the whole flow without Altium.

## Tools

**Read and audit** (always available; reads use a 5 s cache, pass `refresh=true` to re-read):

| Tool | What it does |
|---|---|
| `altium_status` | Server mode, Altium version, open project, problems and how to fix them. Works when Altium is closed. |
| `altium_list_components` | Components of the open project. Filter by designator prefix or a missing parameter (e.g. `MPN`). Paged. |
| `altium_get_component` | Details and all parameters for 1 to 25 designators, optionally with pins and nets. |
| `altium_find_components` | Search by text, wildcard or exact match in any field or a parameter, e.g. "0603 caps without an MPN". |
| `altium_bom_summary` | BOM grouped by comment/footprint/library ref/parameter, with quantities. Optional CSV. Also available as the `altium://bom` resource. |
| `altium_check_parameters` | Missing/blank required parameters, and groups with conflicting values (same part, different MPN). |
| `altium_check_designators` | Duplicate, unannotated (`R?`) designators and numbering gaps. |
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

**Save** (needs `read_write_save` mode):

| Tool | What it does |
|---|---|
| `altium_save_project` | Save the open, modified sheets. `confirm=false` only lists what would be saved. |

**Prompts:** `fill_missing_mpns` (never invents MPNs, previews before applying) and `audit_bom`.

## Set it up locally

You need Python 3.12+ and Git. On Windows, with Altium Designer installed and a project open.

### 1. Get the code and install it

```bash
git clone https://github.com/<owner>/altium-lite-mcp.git
cd altium-lite-mcp
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -e .
```

(With [uv](https://docs.astral.sh/uv/) you can skip the clone and use `uvx --from git+https://github.com/<owner>/altium-lite-mcp altium-lite-mcp` as the command below.)

Check it starts (it waits for an MCP client on stdin, press Ctrl+C to quit):

```bash
altium-lite-mcp
```

### 2. Add it to Claude

**Claude Desktop**: edit `claude_desktop_config.json` (Settings > Developer > Edit Config) and add the server. Use the full path to the executable in your venv:

```json
{
  "mcpServers": {
    "altium": {
      "command": "C:\\path\\to\\altium-lite-mcp\\.venv\\Scripts\\altium-lite-mcp.exe",
      "env": { "ALTIUM_LITE_MODE": "read_only" }
    }
  }
}
```

Restart Claude Desktop.

**Claude Code**:

```bash
claude mcp add altium -- C:\path\to\altium-lite-mcp\.venv\Scripts\altium-lite-mcp.exe
```

### 3. Enable edits (optional)

The server is **read-only by default**. To allow the edit tools, set `ALTIUM_LITE_MODE` to `read_write` in the server's environment (the `env` block above, or `claude mcp add -e ALTIUM_LITE_MODE=read_write ...`) and restart the server. Use `read_write_save` to also allow `altium_save_project`. The model cannot change this setting.

### 4. Try it

Open a project in Altium Designer, then ask Claude: *"Is Altium connected? Which project is open?"*

### Try it without Altium

Set `ALTIUM_LITE_BRIDGE=fake` in the server's environment (works on macOS and Linux too). The server then talks to a built-in demo design with 10 components, some missing an `MPN`.

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `ALTIUM_LITE_MODE` | `read_only` | `read_only`, `read_write` or `read_write_save` |
| `ALTIUM_LITE_EXE` | auto-detected | Full path to Altium's `X2.EXE` (default search: `C:\Program Files\Altium\AD*\`) |
| `ALTIUM_LITE_EXCHANGE_DIR` | `%PROGRAMDATA%\altium_lite_mcp\<user>` | Folder for request/response files and the log. Locked down to your user on first use. Keep it free of spaces. |
| `ALTIUM_LITE_CACHE_TTL` | `5` | Seconds a read snapshot is reused (`0` disables) |
| `ALTIUM_LITE_TIMEOUT` | `60` | Seconds to wait for Altium |
| `ALTIUM_LITE_BRIDGE` | `altium` | `fake` for the demo design |

## How it works

Altium has no supported external API, so the server drives it the way other open-source Altium tools do: it writes a request file, launches a small DelphiScript project inside Altium with `X2.EXE -RScriptingSystem:RunScript(...)`, and reads the JSON response the script writes back. One request at a time.

## Safety

- **Read-only by default**; writes need `ALTIUM_LITE_MODE=read_write`, set outside the model's reach.
- **Preview before apply.** Applied edits are read back and reported as `verified`.
- **Never saves by default.** Edits stay in memory in Altium. Review, then save or press Ctrl+Z (once per affected sheet, and once per batch of 50 changes). Saving needs `read_write_save` and `confirm=true`.
- **Per-user exchange folder.** Requests decide what runs inside Altium, so the folder is restricted to your user (not `C:\Users\Public`). The server never launches Altium itself: if `X2.EXE` is not running, calls fail fast.
- **Design text is untrusted.** Component names, comments and values come from your files and may contain instructions aimed at the model. They are returned as data and length-limited, but treat results with care.
- **Your design data goes to Claude** like any tool output. Do not use this with confidential designs unless that is acceptable to you.
- Reserved parameters (`Designator`, `LibReference`, `Comment`, footprint and model links) cannot be edited. Parameters are only created if you pass `create_if_missing=true`.

## Limits

- Windows and one running Altium instance only.
- Only components of the **compiled project** are read; only schematic parameters are written. The PCB is not updated until you run *Update PCB*.
- Sheets must be **open in Altium** to be edited; edits to closed sheets are refused with a reason. PCB moves act on the focused PCB document.
- Text values: at most 255 characters, characters up to U+00FF only.
- A script error or modal dialog in Altium can stall the bridge. The server times out, blocks further writes and tells you how to recover ([docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)).
- Altium's licence or trial terms on scripting have not been reviewed here. Check your own terms.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests use a fake bridge and an emulator of the DelphiScript side, so they run anywhere. Work happens on `develop`; `main` gets tagged releases.

## License

Apache-2.0, see [LICENSE](LICENSE). Third-party attributions: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
