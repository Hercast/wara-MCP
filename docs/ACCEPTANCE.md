# Manual acceptance (Windows + Altium)

The DelphiScript has never run in Altium. Do these in order and record results. Use a small test project you own (about 10 components, 2 sheets, a few without `MPN`), with **all sheets open**.

## Spikes

| ID | Check | Pass |
|---|---|---|
| S1 | Run `altium_status` with Altium open. Does `X2.EXE -R...` run the script in the existing instance (no second instance, no seat prompt, no modal)? Time 10 calls. | Median latency 5 s or less; two back-to-back calls raise no dialog. Failing: move to a resident pump (see plan section 5.4). |
| S2 | `altium_list_components` vs Altium's own component list | All designators and parameters match |
| S3 | Set a value containing quotes, backslash, `\|`, `=`, and `µ` | Read back identically |
| S4 | Apply a parameter change | Value changes, no dialog, one Ctrl+Z per sheet reverts it, nothing saved to disk |
| S5 | Close Altium; open a modal dialog; cause a script error | Structured error with recovery steps; never hangs |
| S6 | Repeat the demo in Claude Desktop (check the exchange folder is visible if Claude is the Microsoft Store/MSIX build) and Claude Code | Works in both |
| S7 | Read Altium's EULA/trial terms on scripting | Note the result in the README |

## Newer tools (check after the spikes pass)

| Tool | Check |
|---|---|
| `altium_get_nets`, `altium_compile_messages` | Match Altium's connectivity and Messages panel |
| `altium_rename_parameter`, `altium_delete_parameter` | Preview, apply, Ctrl+Z; `delete` uses the least certain API (`RemoveSchObject`) |
| `altium_move_components` | Focus the PCB. Units (mil from board origin), rotation and one Ctrl+Z revert |
| `altium_save_project` | Needs `read_write_save`. Only modified open sheets are saved; verify files on disk |
| Closed sheets | Close a sheet; the edit is refused with a reason and `sheets` shows `open: false` |
| Exchange folder | Check the ACL (`icacls`) shows only your user |

Known open points in `Main.pas`: Altium version lookup returns `unknown`; closed sheets are skipped; undo grouping across sheets; every Altium API call is unverified.

## Demo (definition of done)

1. "Is Altium connected? Which project is open?" -> status shows version, project, `read_only`.
2. "List the components and which have no MPN." -> matches Altium.
3. "Set MPN to ABC-123 on R1 to R3." -> refused (read-only).
4. Switch to `read_write`, restart the server, repeat -> preview only, Altium unchanged (use `create_if_missing` if the parameter does not exist yet).
5. "Apply it." -> Altium shows new values, sheet modified but unsaved, Ctrl+Z reverts, read-back `verified: true`.
6. Close Altium or leave a modal dialog open, then read -> timeout or not-reachable error with recovery steps, no hang.
