# altium-lite-mcp

> **Experimental.** No support commitment. Unofficial, and not affiliated with or endorsed by Altium.

A small [MCP](https://modelcontextprotocol.io) server that lets Claude **read** the components of the Altium Designer project you have open and make **one kind of small edit**: setting schematic component parameters, such as filling in missing `MPN` values. You get a preview first, and edits are left unsaved in Altium so one Ctrl+Z undoes them.

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

Expect to debug the Altium side on first use. The [fake mode](#try-it-without-altium) lets you try the whole flow without Altium.

## Tools

| Tool | What it does |
|---|---|
| `altium_status` | Server mode, Altium version, open project, problems and how to fix them. Works when Altium is closed. |
| `altium_list_components` | Components of the open project. Filter by designator prefix or by a missing parameter (e.g. `MPN`). Paged (default 200, max 500). |
| `altium_get_component` | Full details and parameters for 1 to 25 designators, optionally with pins and nets. |
| `altium_set_parameter` | Set parameters on up to 50 components. Preview by default; `apply=true` writes. |

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

The server is **read-only by default**. To allow `altium_set_parameter`, set `ALTIUM_LITE_MODE` to `read_write` in the server's environment (the `env` block above, or `claude mcp add -e ALTIUM_LITE_MODE=read_write ...`) and restart the server. The model cannot change this setting.

### 4. Try it

Open a project in Altium Designer, then ask Claude: *"Is Altium connected? Which project is open?"*

### Try it without Altium

Set `ALTIUM_LITE_BRIDGE=fake` in the server's environment (works on macOS and Linux too). The server then talks to a built-in demo design with 10 components, some missing an `MPN`.

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `ALTIUM_LITE_MODE` | `read_only` | `read_only` or `read_write` |
| `ALTIUM_LITE_EXE` | auto-detected | Full path to Altium's `X2.EXE` (default search: `C:\Program Files\Altium\AD*\`) |
| `ALTIUM_LITE_EXCHANGE_DIR` | `C:\Users\Public\altium_lite_mcp` | Folder for request/response files and the log. Keep it free of spaces. |
| `ALTIUM_LITE_TIMEOUT` | `60` | Seconds to wait for Altium |
| `ALTIUM_LITE_BRIDGE` | `altium` | `fake` for the demo design |

## How it works

Altium has no supported external API, so the server drives it the way other open-source Altium tools do: it writes a request file, launches a small DelphiScript project inside Altium with `X2.EXE -RScriptingSystem:RunScript(...)`, and reads the JSON response the script writes back. One request at a time.

## Safety

- **Read-only by default**; writes need `ALTIUM_LITE_MODE=read_write`, set outside the model's reach.
- **Preview before apply.** Applied edits are read back and reported as `verified`.
- **Never saves.** Edits stay in memory in Altium. Review, then save or press Ctrl+Z (once per affected sheet).
- **Design text is untrusted.** Component names, comments and values come from your files and may contain instructions aimed at the model. They are returned as data and length-limited, but treat results with care.
- **Your design data goes to Claude** like any tool output. Do not use this with confidential designs unless that is acceptable to you.
- Reserved parameters (`Designator`, `LibReference`, `Comment`, footprint and model links) cannot be edited. Parameters are only created if you pass `create_if_missing=true`.

## Limits

- Windows and one running Altium instance only.
- Only components of the **compiled project** are read; only schematic parameters are written. The PCB is not updated until you run *Update PCB*.
- Sheets must be **open in Altium** to be edited; closed sheets are skipped.
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
