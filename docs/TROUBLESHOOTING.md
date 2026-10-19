# Troubleshooting

Start with `altium_status`; it lists problems and fixes. Server log: `<exchange dir>\altium_lite_mcp.log`.

| Symptom | Cause and fix |
|---|---|
| `E_ALTIUM_NOT_FOUND` | Not on Windows, or `X2.EXE` not found. Set `ALTIUM_LITE_EXE` to its full path. |
| `E_NO_PROJECT` | Open a project in Altium. |
| `E_TIMEOUT` | A modal dialog is open, or a script is stuck. Close dialogs, press **Ctrl+F3** (Stop Running Script), or restart Altium. A script runtime error parks the script in the debugger and later runs silently do nothing until it is stopped. |
| `E_BRIDGE_WEDGED` | An earlier call timed out and writes are blocked. Fix Altium, then call `altium_status` (or any read) to clear it. |
| `E_SCRIPT_VERSION` | Altium used a cached older script. Restart Altium. |
| `E_MODE_READ_ONLY` | Set `ALTIUM_LITE_MODE=read_write` in the server's environment and restart the server. |
| Edits do not show up on a sheet | The sheet must be open in Altium; closed sheets are skipped. |
| Request files never get picked up (Claude Desktop) | The Microsoft Store build of Claude can redirect writes under `%APPDATA%`. Keep `ALTIUM_LITE_EXCHANGE_DIR` on a plain path such as `C:\Users\Public\altium_lite_mcp`. |
| Launch fails on paths | Avoid spaces and UNC paths in the exchange folder. |
