# Plan: Altium MCP, experimental MVP

- **Status: PLAN ONLY - nothing in this document has been executed.** No code, directories, packages, installs or repository changes were made while writing it.
- **Date:** 2026-10-19. Supersedes the KiCad + Altium plan `EDA_MCP_PLAN.md` (2026-10-07), which is kept only for reference.
- **Working name:** `altium-lite-mcp` (placeholder).
- **Project type:** new, standalone, open-source, experimental. Python. No relationship to AllSpice or the Hub codebase, and nothing from either is used. This file sits in the Hub working directory only because that is where the planning session ran; move it into the new repository.
- **Inputs:** the earlier research reports (2026-10-07) plus a re-check of the key open-source projects and Altium pages on 2026-10-19. Facts verified in that re-check are marked **[V]**. Anything not verified stays marked **UNVERIFIED** and gets a spike.

---

## 1. Summary

1. Build **one small Python MCP server that drives Altium Designer on a Windows machine**. KiCad, Altium 365, offline file parsing and everything AllSpice-related are out.
2. The MVP is a **vertical slice**: an LLM can **read** the components of an open Altium project and **edit** one simple thing (schematic component parameters, for example filling in missing `MPN` values), with a preview first and a single undo step afterwards.
3. **Reuse, do not reinvent.** Altium has no supported external API, so every open-source Altium MCP drives it by running DelphiScript inside Altium and exchanging files with a Python server. We copy and adapt the working DelphiScript and bridge ideas from two permissively licensed projects (coffeenmusic/altium-mcp, MIT; salitronic/eda-agent, Apache-2.0), with attribution. We write our own thin MCP layer. We copy **no** GPL or AGPL code.
4. **Everything runs on the user's Windows laptop**: Claude (Desktop or Code), the MCP server and Altium on one machine, over stdio. No remote bridge, no HTTP, no cloud.
5. **Four tools** in the MVP: `altium_status`, `altium_list_components`, `altium_get_component`, `altium_set_parameter`. Two more are stretch.
6. **Read-only by default.** Writes need a mode the user sets in config, the write tool previews unless told to apply, edits stay unsaved in Altium, and each call is one undo step.
7. **Work order is built around the Altium trial.** Everything that does not need Altium (server, fake bridge, tests, packaging) is built first. The trial is started only for a short, time-boxed window to write the DelphiScript, run the spikes and run the acceptance demo.
8. **Effort:** about 12 engineer-days for one engineer (range 8 to 20). The biggest unknown is DelphiScript itself (hard to debug, crash-prone, documentation in flux), not the Python.

---

## 2. Your decisions and what they changed

| # | Topic | Your answer | Effect on the plan |
|---|---|---|---|
| 1 | Audience and license | Open source | Permissive license, proposed **Apache-2.0** (compatible with vendoring MIT and Apache-2.0 code, includes a patent grant). Never copy GPL or AGPL code. Confirm in section 13. |
| 2, 3 | Scope | Altium first, vertical MVP: read a design and edit it simply. Drop KiCad. Leverage other open-source MCPs. | KiCad removed completely. MVP is read plus one simple edit. Prior art is copied and adapted, not rebuilt. |
| 4, 16 | AllSpice | No relation at all | No Hub changes, no AllSpice MCP, no Crysknife. The old "relation to the Hub" question is deleted. |
| 2 (build) | Language | Python | Python 3.12+, official `mcp` SDK, packaged with `uv`. |
| 3 (build) | Build vs adopt | Not understood, then "leverage other open-source MCPs" | Explained below. Decision: **write our own thin server, copy and adapt small parts of two permissive projects.** |
| 12 | Offline parser | Nothing from AllSpice or Crysknife | No offline parsing in the MVP at all. This also avoids the AGPL and GPL parser libraries. |
| 4 | Altium seat | None available. Use the online viewer; manual testing later on a trial. | No Altium in CI. Automated tests use a fake bridge. Real acceptance is manual on the user's Windows laptop. The free online viewer is used only to eyeball results. |
| 5 | Altium 365 | Not available, not part of the MVP | Dropped. |
| 6 | Windows host | The user's Windows laptop | The server and Altium run on that laptop. No remote agent. |
| 7 | Versions | Two latest Altium releases, no KiCad | Target the 26.x line (current release 26.11.1, 2026-10-14 **[V]**) and the previous major line 25.x. Only the version the trial installs can actually be tested, so 25.x is best-effort and documented as such. |
| 9 | Clients | Claude | Claude Desktop and Claude Code on Windows. No other client testing. |
| 10 | Data handling | Use the default | Local-only server, no telemetry, no network calls from our code. Design data in tool results goes to the user's Claude session. README states this plainly. |
| 11 | Distribution | Simplest, `uvx` | `uvx --from git+https://github.com/<owner>/altium-lite-mcp altium-lite-mcp`. No PyPI, `.mcpb` or Docker in the MVP. |
| 13 | Fixtures | Nothing from Hub or AllSpice | Primary fixture is a tiny test project the user builds in the trial. See section 9. |
| 14 | Ownership | Experimental, no maintenance | README says "experimental, no support commitment". No version-matrix promises. |

### Build vs adopt, in plain words

When a similar open-source project already exists there are three options:

- **Build from scratch.** Write everything ourselves. Slowest, and DelphiScript is the hard part, so we would relearn lessons others already paid for.
- **Adopt or fork.** Use someone else's project as the product. Fast, but we inherit its size (eda-agent has hundreds of tools), its design choices and its maintenance state.
- **Copy and adapt (vendor).** Write our own small project, and copy specific files or ideas from permissively licensed projects into it, keeping their copyright notices.

You asked to leverage the other MCPs, so this plan takes the third option, with one rule: only copy from projects whose license allows it (MIT, Apache-2.0), and list every copied piece in `THIRD_PARTY_NOTICES.md`.

---

## 3. MVP definition

### 3.1 Goal

An LLM, connected through Claude on the user's Windows laptop, can inspect the components of the Altium project that is open and make a small, reviewable edit to it, without the user leaving Claude except to look at Altium.

### 3.2 Acceptance demo (the definition of done)

Run in Claude Desktop on the Windows laptop with the user's tiny test project open in Altium (about 10 components, 2 sheets, some components missing an `MPN` parameter):

| Step | Prompt | Expected result |
|---|---|---|
| 1 | "Is Altium connected? Which project is open?" | `altium_status` reports the version, the project name and `read_only` mode. |
| 2 | "List the components and tell me which have no MPN." | The list matches Altium's own component list for the project. The missing-MPN answer is correct. |
| 3 | "Set MPN to `ABC-123` on R1 to R3." | Refused with a clear message, because the server is in read-only mode. |
| 4 | (User switches the config to read-write and restarts the server.) Same prompt. | A preview showing old and new values for R1 to R3. Nothing changed in Altium. |
| 5 | "Apply it." | Altium shows the new values. The schematic is marked modified but **not saved**. One Ctrl+Z reverts all three. A read-back confirms the new values. |
| 6 | (User closes Altium or leaves a modal dialog open.) Any read. | A structured timeout or "Altium not reachable" error with recovery steps. No hang. |

### 3.3 In scope (the cut line)

- Windows only, Altium running with a project loaded, one Altium instance.
- Four tools (section 6): status, list components, get component, set parameter.
- Read-only default, preview-then-apply write, no auto-save, single undo step per write.
- Install with `uvx`, a README with limits and a troubleshooting section, a manual acceptance checklist.

### 3.4 Stretch (only if Phase 2 finishes early)

- `altium_move_components`: PCB placement by offset or absolute position. This is the best-proven write in prior art, but units, rotation and origin conventions are a known source of confusion.
- `altium_get_nets`: net names and connected pins for given components.

### 3.5 Out of scope

KiCad. Altium 365 and the Platform API. Offline parsing or writing of SchDoc, PcbDoc and libraries. ERC, DRC and OutJob runs. Screenshots. Library creation. Schematic placement or wiring. ECO or PCB sync. Auto-save and file-level backups. macOS or Linux hosts and any remote bridge. A resident DelphiScript pump (it is the fallback, not the plan). MCP resources, prompts and a tool-catalog mode. Windows on ARM. Anything beyond `uvx` distribution.

---

## 4. Prior art we leverage

Only Altium projects matter now. Stars and activity are from the 2026-10-07 research.

| Project | License | What we take | How |
|---|---|---|---|
| [coffeenmusic/altium-mcp](https://github.com/coffeenmusic/altium-mcp) **[V]**: Python FastMCP, about 29 tools, 179 stars | MIT | The launch mechanism (`X2.EXE -RScriptingSystem:RunScript(...)`), the request/response file exchange, the shape of the DelphiScript command dispatcher, the proven component read commands (`get_project_components`, `get_component_data`, `get_all_designators`), config discovery of `X2.EXE`, the Claude Desktop MSIX path workaround, the idea of a separate sandbox script project | **Copy and adapt** the small parts we need. Keep the MIT notice. Do not take its Python server (pinned old `mcp==1.5.0`, Tk file dialogs, `.dxt` packaging, 29 tools). |
| [salitronic/eda-agent](https://github.com/salitronic/eda-agent) **[V]**: resident DelphiScript pump, hundreds of tools, "experimental", 241 stars | Apache-2.0 | The schematic parameter-edit logic (`sch_set_components_parameters` and `obj_modify` equivalents), `PreProcess`/`PostProcess` handling, the live-tested DelphiScript notes in `docs/altium-delphiscript`, the response envelope, atomic request writes, modal-dialog lessons, `scripts/altium/*.pas` as reference source | **Copy and adapt** the parameter-edit handler. Keep the Apache-2.0 license and NOTICE text and mark changes. It is also the **fallback bridge design** (section 5.4). Do not adopt it wholesale. |
| [flaco-source/altium-mcp](https://github.com/flaco-source/altium-mcp) (TypeScript port of coffeenmusic) | MIT | Idea only: a `.bridge.lock` file to serialize calls across several server processes | Idea only |
| [brandons-cs/altium-schdoc-mcp](https://github.com/brandons-cs/altium-schdoc-mcp), [IntelligentElectron/universal-netlist](https://github.com/IntelligentElectron/universal-netlist) | MIT, Apache-2.0 | Nothing now. Offline parsers, deferred. | None |
| altium-monkey (AGPL-3.0), embedded-society/altium-designer-mcp (GPL-3.0), EasyEDALoader (GPL-3.0) | Copyleft | Nothing | **Do not copy or link.** |

**Copy rules (apply to every copied file):**

1. Check the license file of the source at the commit we copy from, and record the commit SHA.
2. Keep the original copyright and license text in the file header and in `THIRD_PARTY_NOTICES.md`. For Apache-2.0 sources, state what we changed.
3. Prefer adapting small functions over copying large files, and keep the adapted `.pas` files in one directory (`scripts/altium/`) so provenance is obvious.
4. Altium's own guidance says DelphiScript generated from scratch is unreliable and that modifying a working example works better, so every `.pas` handler starts from a working upstream example.

---

## 5. Architecture

### 5.1 Decisions

| # | Decision | Recommendation | Why | Rejected |
|---|---|---|---|---|
| D1 | Shape | One local MCP server on stdio, Windows only, driving the Altium already running on the same machine | Simplest possible deployment. No auth, no network surface. | Remote Windows agent over HTTP (needed only for macOS hosts, deferred) |
| D2 | Language and stack | Python 3.12+, official `mcp` SDK (FastMCP), Pydantic v2, `uv` | You asked for Python. Matches all Python prior art. | TypeScript, Rust |
| D3 | Altium control | DelphiScript project running inside Altium, file exchange with the server | The only broadly usable live-control route. Both prior-art bridges use it. | Official SDK (closed beta), C# in-process extensions (version-fragile, can stop Altium starting), GUI automation |
| D4 | Launch model | **Per-request launch** of `X2.EXE -R...` (coffeenmusic model) | Nothing resident, no manual "start pump" step, least code. | Resident pump as the first choice (more to build, manual start each session) |
| D5 | Fallback if D4 fails spike S1 | **Resident timer-driven pump** started from File > Run Script (eda-agent model), same adapter interface | Avoids relaunching `X2.EXE` against a running instance. | Rebuilding on another mechanism |
| D6 | Wire protocol | **Request: plain `key=value` lines. Response: JSON.** | DelphiScript has no JSON library. Both prior bridges hit bugs in hand-rolled Pascal JSON parsing. Reading `key=value` with `TStringList.Values` is trivial and writing JSON by string concatenation is easy to get right. Proposal, validated in S3. | JSON both ways (coffeenmusic approach, known fragile) |
| D7 | Edit model | One `altium_set_parameter` tool with `apply=false` default | Two-step preview/apply in one tool is enough for an MVP. | The earlier plan's separate `plan_apply` machinery (overkill here) |
| D8 | Persistence | Never save from the server. Edits stay in memory in Altium. | The user reviews in Altium, saves or undoes. No file corruption risk from us. | Auto-save, `.bak` management |

### 5.2 Component diagram

```
 Claude Desktop / Claude Code (on the Windows laptop)
        |  stdio
        v
+----------------------------------------------------------+
| altium-lite-mcp (Python, uvx)                            |
|   MCP layer     4 tools, annotations, structured errors  |
|   Safety        mode flag, preview/apply, input limits   |
|   Bridge client request writer, launcher, response poller|
|                 (interface: real bridge | fake bridge)   |
+-------------------------+--------------------------------+
                          |  files in a space-free exchange dir
                          |  + launch X2.EXE -RScriptingSystem:RunScript(...)
                          v
+----------------------------------------------------------+
| Altium Designer (already running, project open)          |
|   DelphiScript project (Altium_Lite.PrjScr, vendored)    |
|   Dispatcher -> status | list | get | set_parameter      |
+----------------------------------------------------------+
```

### 5.3 Bridge protocol (proposal, validated in spikes S1 to S3)

- **Exchange directory:** a space-free, non-virtualized path such as `C:\Users\Public\altium_lite_mcp\`. Reasons from prior art: the `-R` argument parser reportedly splits on spaces (UNVERIFIED, from a third-party wiki), and Claude Desktop installed as an MSIX app can redirect writes under `%APPDATA%` into a package-private folder that Altium cannot see (coffeenmusic works around this; to be confirmed in S6).
- **Request:** `req_<uuid>.txt`, written to a temp name and renamed so Altium never reads a half-written file. Content: `protocol=1`, `id=<uuid>`, `command=set_parameter`, then `key=value` lines, with lists as `designator.0=R1`, `designator.1=R2`. Values are ASCII-escaped (`\uXXXX`), because characters above U+00FF become `?` in DelphiScript.
- **Response:** `resp_<uuid>.json`: `{id, success, protocol_version, script_version, data, error{code,message,details}}`. Written by DelphiScript with a proper string-escaping function. The server treats a missing or unparsable file as an error, never a success.
- **Completion:** the server polls for the response file (about 0.5 s interval, default timeout 60 s, configurable) and ignores partial reads by retrying parse failures for a short window.
- **Script cache:** Altium can serve stale script code from a cached path. On first run the server copies `scripts/altium/` to a **content-hashed** folder under the exchange directory and launches from there (technique used by Altium-MCP-Suite per the research).
- **Version handshake:** every response carries `script_version` and `protocol_version`. A mismatch with the server returns `E_SCRIPT_VERSION` with the fix ("restart Altium or clear the script cache").
- **Serialization:** one request in flight, enforced by an in-process lock plus a lock file in the exchange dir, so two Claude clients cannot interleave.
- **Cleanup:** request and response files older than 60 s are deleted on startup and on each call.

### 5.4 Launch model and the fallback rule

The single biggest unknown is what `X2.EXE -R...` does when Altium is already running: forwarded to the open instance, a second instance, or an error, and whether it takes a second license seat. Prior-art projects use exactly this against an open session, so it likely works, but no document says so. **Spike S1 decides:**

- **Pass:** keep D4.
- **Fail** (second instance, seat prompt, modal dialog, or latency over about 5 s median): switch to D5. The user runs `StartMCPServer`-style pump from File > Run Script once per Altium session, and the bridge client polls the same mailbox files without launching anything. The adapter interface and the four tools do not change.

### 5.5 Windows specifics

- **Find `X2.EXE`:** config value, else env var, else newest `C:\Program Files\Altium\AD*\X2.EXE`, validated by file existence. A 26.x install may use a different folder layout (UNVERIFIED), so discovery failure returns an explicit "set `ALTIUM_LITE_EXE`" error.
- **Locale:** decimal separators break number parsing in Pascal (coffeenmusic issue #2). The MVP only exchanges strings, so it avoids the problem. Stretch tools must pass numbers as integers (mils) to stay safe.
- **Paths:** no UNC paths (they fail in scripts), no spaces.
- **Do not auto-dismiss dialogs** in the MVP. Prior art closes error dialogs with WM_CLOSE after a delay, which is risky. The MVP reports a timeout with recovery steps instead.

### 5.6 Module layout (text only, nothing created)

```
altium-lite-mcp/
  pyproject.toml  LICENSE (Apache-2.0)  README.md  THIRD_PARTY_NOTICES.md
  src/altium_lite_mcp/
    server.py        MCP wiring and tool definitions
    config.py        mode, exchange dir, exe path, timeouts
    bridge/          base.py (interface)  altium.py (launch + files)  fake.py (tests)
    models.py        Pydantic request and response types, error codes
    safety.py        mode check, input limits, text sanitising
    scripts/altium/  vendored DelphiScript project (.PrjScr, .pas) with provenance headers
  tests/             unit, bridge contract, MCP protocol, golden fixtures
  docs/              ACCEPTANCE.md, TROUBLESHOOTING.md
```

---

## 6. Tool surface

### 6.1 Conventions

- All tool names start with `altium_`. All results use one envelope: `{ok, data, error{code,message,hint}, meta{bridge, script_version, elapsed_ms}}`.
- Every response says which mode the server is in. Tool descriptions state the exact conventions: what is read from (the compiled project, not a saved file), that edits are in memory only, and that the PCB is not updated until the user runs Update PCB in Altium.
- MCP annotations: reads are `readOnlyHint=true`; `altium_set_parameter` is `readOnlyHint=false, destructiveHint=false, idempotentHint=true` (it overwrites a value, which the undo step reverses). Annotations are hints for clients, not a security boundary. The real gate is the server-side mode flag.
- Lists are bounded: default `limit=200`, hard maximum 500, with `truncated=true` when cut. Text fields are length-limited.
- Error codes: `E_MODE_READ_ONLY`, `E_ALTIUM_NOT_FOUND`, `E_NO_PROJECT`, `E_TIMEOUT`, `E_BRIDGE_WEDGED`, `E_SCRIPT_VERSION`, `E_NOT_FOUND`, `E_INVALID_INPUT`, `E_ALTIUM_ERROR`.

### 6.2 MVP tools

| Tool | Kind | Input | Output |
|---|---|---|---|
| `altium_status` | read | none | `server_version`, `mode` (`read_only` or `read_write`), `altium{exe_path, version, running}`, `bridge{script_version, protocol_version, last_ok}`, `active_project{name, path}` or null, `warnings[]`. This is the only tool that works when Altium is closed, and it tells the user what to fix. |
| `altium_list_components` | read | `limit`, `offset`, `designator_prefix?`, `missing_parameter?` (for example `"MPN"`) | `total`, `items[{designator, comment, library_ref, footprint, sheet}]`, `truncated`. Source: components of the compiled project (as coffeenmusic's `get_project_components`). |
| `altium_get_component` | read | `designators` (1 to 25 strings), `include_pins=false` | `items[{designator, comment, library_ref, footprint, sheet, parameters{name: value}, pins?[{number, name, net}]}]`. Unknown designators come back in `not_found[]`. |
| `altium_set_parameter` | write | `changes` (1 to 50 of `{designator, name, value}`), `apply=false` | Preview: `changes[{designator, name, old, new, status}]` with status `ok`, `no_change`, `not_found` or `refused`, and `applied=false`. With `apply=true`: the same rows, `applied=true`, and `verified` from a read-back of every changed value. One undo step for the whole call. Refused in read-only mode. |

`altium_set_parameter` rules:

- Edits **schematic component parameters only**. Reserved names (`Designator`, `LibReference`, footprint and model links) are `refused` in the MVP.
- Creating a parameter that does not exist is allowed only if the call says so (`create_if_missing=true`, default false), because a typo should not silently add a new parameter.
- Values must be ASCII or escaped, at most 255 characters, no control characters. Anything else is `E_INVALID_INPUT`.
- No save. The result tells the user the schematic is modified and unsaved.

### 6.3 Stretch tools

| Tool | Notes |
|---|---|
| `altium_move_components` | `{designator, dx_mil, dy_mil, rotation?}` list, `apply=false` preview default, one undo step, mils relative to the board origin, stated in the description. Adapt coffeenmusic's `move_components` and `set_component_position`. |
| `altium_get_nets` | Net names and pads for given components. Adapt `get_net_connections`. |

---

## 7. Safety and reliability (sized for an MVP)

- **Read-only by default.** `ALTIUM_LITE_MODE=read_write` must be set in the server's environment (Claude Desktop config `env`, or `claude mcp add -e`). The model cannot change it, and tool arguments cannot override it.
- **Preview before apply**, no auto-save, one undo step per write, read-back verification after apply. A failed read-back is reported as `verified=false`, never as success.
- **Untrusted text.** Component names, comments and parameter values come from design files and can contain instructions aimed at the model. The server returns them as data fields, never concatenates them into prose messages, truncates long strings, and the README tells users to treat results as untrusted. No tool takes a file path from the model, so there is no path traversal surface.
- **Wedged script handling.** A DelphiScript runtime error parks the script in the debugger, and later runs silently do nothing until the user presses Stop (Ctrl+F3) or restarts Altium. On `E_TIMEOUT` the server marks the bridge `suspect_wedged`, refuses writes until a plain `altium_status` read succeeds, and returns recovery steps. It does not try to hide this.
- **No network.** Our code makes no outbound connections and has no credentials or tokens.
- **Logging.** A rotating log file under the exchange directory records tool calls and errors, with parameter values truncated.
- **Data handling default.** Tool results are sent to the user's Claude session like any other tool output. No telemetry. The README warns against using confidential designs unless that is acceptable to the user.
- **Licensing and terms.** The Altium EULA and trial terms on scripting and automation were not retrievable (UNVERIFIED). The README states that this is an unofficial, experimental tool, not affiliated with Altium, and that the user is responsible for their license terms.

---

## 8. Environment, install and distribution

- **Machine:** the user's Windows laptop (Windows 10 or 11, x64) with Altium Designer from the trial. Altium requires an account to download **[V]**. The trial length was not confirmed (UNVERIFIED), so check it before starting the clock.
- **Versions:** target Altium Designer 26.x (current 26.11.1 **[V]**; the best prior-art bridge reports testing on 26.10.1.6) and the previous major line, 25.x, best-effort. Prior-art projects recommend AD 22 or newer. Treat the version the trial installs as the only tested one.
- **Prerequisites:** Python 3.12+ is fetched by `uv`; install `uv` once.
- **Run from git (no PyPI):**

```
uvx --from git+https://github.com/<owner>/altium-lite-mcp altium-lite-mcp
```

- **Claude Desktop:** one `mcpServers` entry running the command above, with `env` containing `ALTIUM_LITE_MODE` (`read_only` by default).
- **Claude Code:** `claude mcp add altium -- uvx --from git+https://github.com/<owner>/altium-lite-mcp altium-lite-mcp`, with `-e ALTIUM_LITE_MODE=read_write` when writes are wanted.
- **First run:** the server copies the vendored scripts to the content-hashed folder in the exchange dir and prints the path. No Altium Global Projects registration is needed in the per-request model, because `-R` points `ProjectName` directly at the script project (coffeenmusic does the same). The fallback pump model needs the one-time registration.
- **Development machine:** the user develops on macOS and syncs to the Windows laptop through git. Everything except the real bridge runs on macOS.

---

## 9. Testing

| Layer | Where | What | Needs Altium |
|---|---|---|---|
| L1 Automated | macOS, Linux and Windows CI (GitHub Actions) | Unit tests, bridge contract tests, MCP protocol tests (list tools, schemas, annotations, error envelope), mode and input-limit tests, timeout and wedge-state tests. All use `bridge/fake.py`, a Python stand-in that answers the same request files. | No |
| L2 Golden | CI | Real responses recorded from the user's trial in Phase 2, stored as JSON fixtures and replayed by the fake bridge, so parsing and formatting regressions are caught without Altium. | No (after recording) |
| L3 Manual acceptance | The user's Windows laptop and trial | `docs/ACCEPTANCE.md`: the six-step demo in section 3.2, plus the spike checks. Run before tagging a release. | Yes |

**Fixtures policy:**

- **Primary fixture: a tiny test project the user builds in the trial** (about 10 components, 2 sheets, a few missing `MPN` parameters). It is the user's own work, so it can be committed under the project license.
- Nothing from the AllSpice Hub repository or any AllSpice source is used.
- Third-party open-hardware designs may be used for extra manual checks only if their license is verified first and the files are **not committed**. Candidates seen in search results, both UNVERIFIED and to be checked individually: [IRNAS/PCB-Antenna](https://github.com/IRNAS/PCB-Antenna) (CERN-OHL v1.2 per the search snippet) and the Omi hardware files ([license page](https://docs.omi.me/doc/hardware/consumer/license), MIT per the snippet). Altium's own example designs ship with the install and should not be redistributed.
- **The free online viewer** ([altium.com/viewer](https://www.altium.com/viewer/)) accepts SchDoc and PcbDoc in the browser without installing anything, and uploads last only for the browser session **[V]**. Use it to eyeball a design and cross-check what the MCP reports. It cannot drive any automation. Do not upload anything confidential.
- **What cannot be tested automatically:** the DelphiScript itself. It only runs inside Altium, which is why Phase 2 needs a real session and why `.pas` handlers start from working upstream examples.

---

## 10. Roadmap

Work order is chosen to keep the Altium trial window short: do everything that does not need Altium first.

### Phase 1: no Altium needed (about 4 engineer-days)

- Repository scaffold: `pyproject.toml`, Apache-2.0 `LICENSE`, `THIRD_PARTY_NOTICES.md`, README stub.
- Server skeleton on stdio with the four tools, the envelope, the error codes and the config.
- Bridge interface, the real bridge client (written against the protocol in 5.3) and `fake.py`.
- Safety layer: mode flag, input limits, preview/apply logic, wedge state.
- L1 tests and a GitHub Actions workflow on Ubuntu and Windows.
- **Exit:** tests green; the four tools appear in MCP Inspector and in Claude with the fake bridge; the read-only refusal and the preview flow work against the fake.

### Phase 2: Altium trial window, time-boxed (about 5 engineer-days)

Start the trial only now. Install Altium, build the tiny test project, adapt the vendored `.pas` files, and run the spikes:

| Spike | Question | Pass criterion | If it fails |
|---|---|---|---|
| S1 Launch model | Does `X2.EXE -R...` run the script inside the already-open Altium without a second instance, seat prompt or modal? Is the path with spaces a problem? What is the latency? | Runs in the existing instance, writes a response file, median latency of 5 s or less over 10 calls, two back-to-back calls do not raise a modal. | Switch to the pump (D5). |
| S2 Read | Can the script list compiled project components and their parameters? | Designators and parameters match Altium's own component list for all test components. | Adapt the coffeenmusic command differently, or read from the PCB side instead. |
| S3 Protocol | Do `key=value` requests via `TStringList` and JSON responses survive awkward strings? | Exact round trip for quotes, backslashes, pipes, equals signs, newlines, and characters up to U+00FF. Characters above U+00FF are rejected by the server with `E_INVALID_INPUT`. | Fall back to coffeenmusic's JSON request format and its parsing. |
| S4 Write | Can a parameter be set inside `PreProcess`/`PostProcess`, with one undo step, no modal, and a correct read-back? | Value changes, Ctrl+Z reverts all changes in one step, no dialog, read-back equals the new value, nothing saved to disk. | Try eda-agent's alternative property path, or reduce the MVP to read-only and say so. |
| S5 Failure modes | What happens on a script error, a modal dialog, or Altium being closed? | The server returns `E_TIMEOUT`, `E_BRIDGE_WEDGED` or `E_ALTIUM_NOT_FOUND` with recovery steps and never hangs. | Shorten timeouts and tighten the wedge detection. |
| S7 Terms (no code) | What do the trial terms and EULA say about scripting and automation? | Findings recorded in the README. | Not blocking for a personal experimental tool, but the README must reflect it. |

- Record real responses as golden fixtures (layer L2).
- **Exit:** the acceptance demo in section 3.2 passes on the laptop.

### Phase 3: package and publish (about 3 engineer-days)

- **S6** end to end: Claude Desktop (MSIX path behavior, exchange dir) and Claude Code, both launching through `uvx` on Windows. Pass: the demo works in both.
- README (what it is, what it is not, limits, data handling, "experimental, no support"), `ACCEPTANCE.md`, `TROUBLESHOOTING.md` (stuck script, modal dialog, wrong Altium version, MSIX paths).
- Tag `0.1.0`. **Exit:** a clean Windows user profile can follow the README to a working demo.

**Total:** about 12 engineer-days (range 8 to 20). Assumptions: one engineer comfortable with Python and MCP, new to DelphiScript, and a trial long enough to cover Phase 2. If the trial is short, the fake-bridge work in Phase 1 is still reusable. If S1 or S4 fail outright, the plan degrades to a read-only MVP rather than a dead end.

---

## 11. Risks and mitigations

| Risk | Likelihood and impact | Mitigation |
|---|---|---|
| `X2.EXE -R` misbehaves when Altium is already running | Medium, high | Spike S1 first, with the pump as a pre-designed fallback behind the same adapter. |
| DelphiScript crashes or wedges (an undeclared identifier halts the script, some property reads crash `ScriptingSystem.DLL` on specific builds) | High, medium | Adapt working upstream handlers, keep handlers small, wedge detection and recovery guidance, never auto-save. |
| Altium API drift between 25.x and 26.x | Medium, medium | Version-tag responses, test only on the trial version, document 25.x as best-effort. |
| Trial expires mid-project | Medium, medium | Do Phase 1 first, start the trial for Phase 2 only, record golden fixtures early. |
| Altium EULA or trial terms restrict scripting or automation | Unknown, medium | S7 reads the terms. README disclaims affiliation. Personal experimental use only. |
| License contamination from copied code | Low, high | Copy only MIT and Apache-2.0 sources, record SHAs, keep notices, never touch AGPL or GPL projects. |
| Prompt injection through design data | Medium, medium | Data-only result fields, length limits, README warning, read-only default. |
| Claude Desktop MSIX path virtualization hides the exchange files | Medium, low | Public exchange dir, verified in S6. |
| Project is abandoned | High (stated), low | README says experimental. The bridge is isolated behind an interface so anyone can swap it. |

---

## 12. Explicitly deferred (to prevent scope creep)

KiCad. Altium 365 and the Platform API (needs a workspace and tokens you do not have). Offline SchDoc and PcbDoc parsing or writing (and the AGPL, GPL licensing questions that come with it). ERC and DRC. OutJob and manufacturing outputs. Screenshots. Library and footprint creation. Schematic placement and wiring. ECO and PCB sync. A resident pump as the default. A Windows bridge agent for macOS or Linux hosts. HTTP transport and authentication. Tool-catalog mode. MCP resources and prompts. `.mcpb`, PyPI, Docker. Windows on ARM. Support for Altium versions older than the previous major line.

---

## 13. Remaining decisions

Only items that still need an answer:

1. **Project name and repo owner.** `altium-lite-mcp` is a placeholder, and the repo name appears in the install command.
2. **License.** Apache-2.0 is proposed. MIT is also compatible if you prefer it.
3. **Second write tool.** Is `altium_move_components` wanted in the MVP, or only if time allows (the plan default)?
4. **Trial length and version.** When you start the trial, note its duration and installed version so the support statement in the README is accurate.
5. **Per-request launch as the default.** The plan chooses it for simplicity and falls back to the pump if S1 fails. Say so if you would rather start with the pump.

---

## 14. References and verification register

**Verified on 2026-10-19 [V]**

- coffeenmusic/altium-mcp: MIT, Python 3.10+, Windows, install steps, file layout (`server/`, `AltiumScript/`, `SandboxScript/`), the full tool list, the exchange files and launch command line. [README](https://github.com/coffeenmusic/altium-mcp), [server/main.py](https://raw.githubusercontent.com/coffeenmusic/altium-mcp/main/server/main.py).
- salitronic/eda-agent: Apache-2.0, Python 3.11+, install via `pip install -e .`, script project at `scripts/altium/` (`Dispatcher.pas`, `Main.pas`, `Utils.pas`, `PCB.pas`, `Project.pas`, and others), `StartMCPServer` run from File > Run Script, minimal toolset mode, `sch_set_components_parameters`, `obj_modify`, `pcb_move_components` named in the README. [Repository](https://github.com/salitronic/eda-agent). The mapping from tool names to `.pas` source files was **not** read and is a Phase 2 task.
- Altium downloads page lists 26.11.1 (2026-10-14) and requires sign-in to download. [Downloads](https://www.altium.com/downloads).
- Altium online viewer: SchDoc and PcbDoc supported, no install, session-only uploads, no price listed. [Viewer](https://www.altium.com/viewer).

**From the 2026-10-07 research (not re-fetched)**

- Altium scripting: [Running Scripts](https://www.altium.com/documentation/altium-designer/scripting/running-scripts), [CI with Altium Designer](https://resources.altium.com/p/continuous-integration-implementation-using-altium-designer), [instance and seat KB](https://www.altium.com/documentation/knowledge-base/altium-designer/installing-multiple-instances-of-ad-versions), [API change KB](https://altium.com/documentation/knowledge-base/altium-designer/edit-a-script-to-accomodate-the-latest-changes-in-altium-api), [Altium MCP for Arduinos blog](https://resources.altium.com/p/building-model-context-protocol-server-arduinos).
- DelphiScript lessons: [eda-agent altium-delphiscript docs](https://github.com/salitronic/eda-agent/tree/main/docs/altium-delphiscript), [coffeenmusic placement review](https://github.com/coffeenmusic/altium-mcp/blob/main/PLACEMENT_TOOL_REVIEW.md).
- Third-party failure notes: [Adom wiki](https://wiki.adom.inc/p/pg_15q9ad25nt) (space splitting in `-R`, overlapping launch modals; UNVERIFIED).

**UNVERIFIED items and their owner**

| ID | Item | Owner |
|---|---|---|
| U1 | `X2.EXE -R...` behavior and seat use when Altium is already running | S1 |
| U2 | `-R` parser splitting on spaces | S1 |
| U3 | `TStringList.Values` request parsing and string-escaping behavior in the installed Altium build | S3 |
| U4 | Parameter write path, undo grouping and absence of modal dialogs | S4 |
| U5 | Behavior of the script engine after errors, and how reliably the server can detect it | S5 |
| U6 | Claude Desktop MSIX path virtualization | S6 |
| U7 | Altium EULA and trial terms on scripting and automation | S7 |
| U8 | Trial duration and which Altium version it installs | Before Phase 2 |
| U9 | Whether 25.x works at all with the vendored scripts | Not tested unless a 25.x install is available |
| U10 | Whether the candidate open-hardware fixtures are really under the licenses the search snippets claim | Before any use |
