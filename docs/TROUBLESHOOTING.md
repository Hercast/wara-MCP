# Troubleshooting

Start with `altium_status`; it lists problems and fixes. Server log: `<exchange dir>\altium_lite_mcp.log`.

| Symptom | Cause and fix |
|---|---|
| `E_ALTIUM_NOT_FOUND` | Not on Windows, `X2.EXE` not found (set `ALTIUM_LITE_EXE`), or Altium is not running. The server never starts Altium itself; start it and open a project. |
| `E_NO_PROJECT` | Open a project in Altium. |
| `E_TIMEOUT` | A modal dialog is open, or a script is stuck. Close dialogs, press **Ctrl+F3** (Stop Running Script), or restart Altium. A script runtime error parks the script in the debugger and later runs silently do nothing until it is stopped. |
| `E_BRIDGE_WEDGED` | An earlier call timed out and writes are blocked. Fix Altium, then call `altium_status` (or any read) to clear it. |
| `E_SCRIPT_VERSION` | Altium used a cached older script. Restart Altium. |
| `E_MODE_READ_ONLY` | Set `ALTIUM_LITE_MODE=read_write` (or `read_write_save` for saving) in the server's environment and restart the server. |
| Edit refused: "Sheet ... is not open" | Open that sheet in Altium and retry. |
| Reads look stale | Reads are cached for 5 s and refreshed after every write; pass `refresh=true` or set `ALTIUM_LITE_CACHE_TTL=0`. |
| PCB tools say no PCB is open | Focus the PCB document in Altium. |
| Warning about exchange folder permissions | The server could not restrict the folder to your user (icacls failed). Fix the ACL by hand so only you can write there. |
| Request files never get picked up (Claude Desktop) | The Microsoft Store build of Claude can redirect writes under `%APPDATA%`. Keep `ALTIUM_LITE_EXCHANGE_DIR` on a plain path outside `%APPDATA%`, such as the default under `%PROGRAMDATA%`. If the default does not work, `C:\Users\Public` is a fallback but is writable by other users, so only use it on a single-user machine. |
| Launch fails on paths | Avoid spaces and UNC paths in the exchange folder. |
| Claude Desktop on macOS: "Server disconnected", log says `Operation not permitted` | macOS blocks Claude Desktop from reading `~/Documents`. Install the server into a venv outside protected folders (e.g. `~/.local/share/altium-lite-mcp/venv`) with a normal `pip install .` (not `-e`), and point `command` at it. Logs: `~/Library/Logs/Claude/mcp-server-altium.log`. |
