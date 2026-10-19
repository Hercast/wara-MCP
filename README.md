# ⚡ Talk to your Altium schematic

**Ask an AI agent to review your design, find what's missing, and fix it, while Altium stays in your hands.**

![status](https://img.shields.io/badge/status-experimental-orange) ![license](https://img.shields.io/badge/license-Apache--2.0-blue) ![python](https://img.shields.io/badge/python-3.12%2B-blue)

`altium-lite-mcp` connects Altium Designer to AI agents such as Claude through the [Model Context Protocol](https://modelcontextprotocol.io). Open a project, then just ask.

> *"Which parts on the power sheet have no MPN?"*
> *"Do any designators clash?"*
> *"Fill in these MPNs, but show me first."*

> **Experimental.** Unofficial and not affiliated with Altium. The server and its safety rules are tested; the Altium-side script is still being validated on real Altium installs, so expect rough edges. No support commitment.

---

## What you can do

### 🔍 Review
- Get an **overview** of a project: parts by type, footprints, sheets.
- **Search** parts in plain language: "all 0603 caps", "everything from sheet Power".
- Build a **BOM** summary, copy it as CSV.
- **Audit** parameters: missing MPNs, same part with conflicting MPNs.
- Catch **duplicate or unannotated designators** and numbering gaps.
- See which **nets** a part touches, and read the project's **compile errors**.

### ✏️ Edit, safely
- Set, rename or delete **parameters**, one part or hundreds at once (even from a CSV).
- **Move and rotate** parts on the PCB.
- Optionally **save** the project, only if you allow it.

### 🛡️ Built to be trusted with a real design
| | |
|---|---|
| **Read-only by default** | Nothing can change until you switch on edit mode yourself. The AI can't flip that switch. |
| **Preview first** | Every edit shows old and new values before anything is written. |
| **Checked afterwards** | After an edit, the value is read back from Altium and reported as verified. |
| **Unsaved and undoable** | Changes stay in memory. Review them in Altium, then save, or press **Ctrl+Z**. |
| **Local only** | Runs on your machine. No cloud service, no telemetry. |

---

## See it in action

An example session (on the built-in demo design):

> **You:** Is Altium connected? Which project is open?
> **Agent:** Connected. Project **Demo.PrjPcb** is open. The server is in **read-only** mode.
>
> **You:** Which components have no MPN?
> **Agent:** Five: **R1, R2, R3, C2, D1**. R2 has the parameter but it's empty. I also noticed **C1 and C3** are both 100nF 0603 but have different MPNs. That may be intentional, or a mistake worth checking.
>
> **You:** Set the MPN on R1 to R3 to `DEMO-0001`.
> **Agent:** I can't, because the server is read-only. Enable edit mode in the server settings and restart it.
>
> *(you switch to edit mode)*
>
> **You:** Set the MPN on R1 to R3 to `DEMO-0001`. Create the parameter where it's missing, and preview first.
> **Agent:** Preview, nothing changed yet:
> | Part | Old | New |
> |---|---|---|
> | R1 | *(none, will be created)* | DEMO-0001 |
> | R2 | *(empty)* | DEMO-0001 |
> | R3 | *(none, will be created)* | DEMO-0001 |
>
> **You:** Apply it.
> **Agent:** Done and **verified**. The three values were read back from Altium. The sheet is modified but **not saved**; press Ctrl+Z in Altium to undo.

---

## Get started

### What you need
- **For real use:** a Windows PC with Altium Designer and [Python 3.12+](https://www.python.org/downloads/), plus Claude Desktop or Claude Code.
- **To just try it:** any Mac, Linux or Windows machine with Python 3.12+ and Claude Desktop. See [Try it without Altium](#try-it-without-altium).

### 1. Install

```bash
git clone https://github.com/Hercast/wara-MCP.git
cd wara-MCP
python -m venv .venv
.venv\Scripts\activate
pip install .
```

On Mac/Linux, activate with `source .venv/bin/activate` instead. Use `pip install .` (not `-e`) and keep the environment **outside protected folders** such as `Documents` on macOS, or Claude Desktop won't be allowed to start it.

### 2. Connect it to Claude

**Claude Desktop:** open **Settings → Developer → Edit Config** and add this next to any servers you already have, using the real path to your install:

```json
{
  "mcpServers": {
    "wara": {
      "command": "C:\\path\\to\\wara-MCP\\.venv\\Scripts\\altium-lite-mcp.exe",
      "env": { "ALTIUM_LITE_MODE": "read_only" }
    }
  }
}
```

Quit and reopen Claude Desktop. The Altium tools appear in the tools menu.

**Claude Code:**

```bash
claude mcp add wara -- C:\path\to\wara-MCP\.venv\Scripts\altium-lite-mcp.exe
```

### 3. Ask away

Open a project in Altium Designer and ask: *"Is Altium connected? Which project is open?"*

### 4. Turn on editing (when you're ready)

The server starts **read-only**. To let the agent make changes, set `ALTIUM_LITE_MODE` to `read_write` in the `env` block above and restart Claude Desktop. Use `read_write_save` if you also want the agent to be able to save, which still needs your confirmation each time.

---

## Try it without Altium

No Altium? The server includes a small **demo design** (10 parts, some with missing MPNs) so you can try the whole flow, including the safe-edit steps. Add `"ALTIUM_LITE_BRIDGE": "fake"` to the `env` block:

```json
"env": { "ALTIUM_LITE_BRIDGE": "fake", "ALTIUM_LITE_MODE": "read_write" }
```

Then try the prompts from the session above. Everything is simulated, so nothing real is touched.

---

## Good prompts to start with

| Goal | Ask |
|---|---|
| Orientation | "Give me an overview of this project." |
| Find gaps | "Check MPN, Manufacturer and Value across the project. What's missing or inconsistent?" |
| Housekeeping | "Check designators for duplicates, unannotated parts or gaps." |
| Search | "Find all capacitors with a 0603 footprint." |
| BOM | "Summarise the BOM by value and footprint, and give me the CSV." |
| Wiring | "What nets are connected to U1?" |
| Full audit | Use the `audit_bom` prompt from your agent's prompt menu. |
| Fix with care | Use the `fill_missing_mpns` prompt, give it your list, and approve the preview. |

---

## Good to know

- **Windows only for real Altium**, one running Altium instance.
- Sheets you want to edit must be **open** in Altium.
- Your design data is sent to your AI agent like any tool output. Avoid confidential designs unless that's acceptable to you.
- The server never starts Altium; open it yourself first.
- Stuck? See [troubleshooting](docs/TROUBLESHOOTING.md).

More detail: [technical reference](docs/TECHNICAL.md) (all tools, settings, safety model, limits), [acceptance checklist](docs/ACCEPTANCE.md).

## License

Apache-2.0, see [LICENSE](LICENSE). Third-party attributions: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
