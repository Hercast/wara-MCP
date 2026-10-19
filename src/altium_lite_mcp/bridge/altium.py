"""Real bridge: stage the DelphiScript project, launch it in Altium, exchange files.

Per request (one in flight, serialized by a lock file):
  1. write `request.txt` (temp name + rename) into the exchange dir
  2. launch `X2.EXE -RScriptingSystem:RunScript(...)` on the staged script project
  3. poll for `resp_<id>.json`

UNTESTED against a real Altium install; see docs/ACCEPTANCE.md (spikes S1-S5).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .. import PROTOCOL_VERSION, SCRIPT_VERSION
from ..config import Config
from ..models import (
    E_ALTIUM_ERROR,
    E_ALTIUM_NOT_FOUND,
    E_SCRIPT_VERSION,
    E_TIMEOUT,
    ERROR_CODES,
    AltiumError,
)
from .base import Bridge
from .protocol import encode_request

log = logging.getLogger("altium_lite_mcp")

SCRIPTS_SRC = Path(__file__).resolve().parent.parent / "scripts" / "altium"
STALE_FILE_AGE_S = 60
_lock = threading.Lock()


def find_x2_exe(program_files: Path = Path(r"C:\Program Files\Altium")) -> Path | None:
    """Newest AD*/X2.EXE under Program Files, or None."""
    candidates = [p for p in program_files.glob("AD*/X2.EXE") if p.is_file()]
    if not candidates:
        return None

    def key(p: Path) -> list[int]:
        return [int(n) for n in re.findall(r"\d+", p.parent.name)]

    return sorted(candidates, key=key)[-1]


def x2_running() -> bool | None:
    """Is X2.EXE running? None when it cannot be determined (non-Windows or tasklist failed)."""
    if os.name != "nt":
        return None
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq X2.EXE", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return "x2.exe" in out.lower()


def secure_exchange_dir(path: Path) -> list[str]:
    """Create the exchange dir and restrict it to the current user. Returns warnings.

    Request files decide what runs inside Altium, so other local users must not be
    able to write there. On POSIX an unowned or foreign directory is refused.
    """
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        user = os.environ.get("USERNAME")
        if not user:
            return ["Could not determine USERNAME; exchange folder permissions were not restricted."]
        try:
            subprocess.run(
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F"],
                capture_output=True, check=True, timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return [f"Could not restrict permissions on {path}; make sure only your user can write there."]
        return []
    st = path.stat()
    if st.st_uid != os.getuid():
        err = AltiumError(E_ALTIUM_ERROR, f"Exchange folder {path} is owned by another user; refusing to use it.")
        raise err
    if st.st_mode & 0o077:
        path.chmod(0o700)
    return []


def default_launcher(cmdline: str) -> None:
    # Passed as a single string on purpose: Altium parses its own command line,
    # and list2cmdline would escape the inner quotes.
    subprocess.Popen(cmdline, close_fds=True)  # noqa: S603


class AltiumBridge(Bridge):
    name = "altium"

    def __init__(
        self,
        config: Config,
        launcher: Callable[[str], None] | None = None,
        process_check: Callable[[], bool | None] | None = None,
    ):
        super().__init__()
        self.config = config
        self.exchange = config.exchange_dir
        self._launcher = launcher
        # An injected launcher (tests) implies "Altium is running" unless told otherwise.
        self._process_check = process_check or ((lambda: True) if launcher is not None else x2_running)
        self._secured = False
        self._warnings: list[str] = []
        self.exe_path = config.exe_path
        self._staged: Path | None = None

    # -- setup -------------------------------------------------------------
    def running(self) -> bool | None:
        return self._process_check()

    def startup_warnings(self) -> list[str]:
        return list(self._warnings)

    def _resolve_exe(self) -> Path | None:
        if self._launcher is not None:
            return self.exe_path or Path("X2.EXE")  # injected launcher (tests)
        if self.exe_path is None:
            self.exe_path = find_x2_exe() if os.name == "nt" else None
        if self.exe_path is not None and not Path(self.exe_path).is_file():
            return None
        return self.exe_path

    def stage_scripts(self) -> Path:
        """Copy the script project to a content-hashed folder (defeats Altium's script cache)."""
        h = hashlib.sha256()
        files = sorted(p for p in SCRIPTS_SRC.iterdir() if p.is_file())
        for p in files:
            h.update(p.name.encode())
            h.update(p.read_bytes())
        h.update(str(self.exchange).encode())
        dest = self.exchange / "scripts" / h.hexdigest()[:12]
        if not dest.exists():
            tmp = dest.with_name(dest.name + ".tmp")
            shutil.rmtree(tmp, ignore_errors=True)
            tmp.mkdir(parents=True)
            for p in files:
                text = p.read_text(encoding="utf-8").replace("@@EXCHANGE_DIR@@", str(self.exchange))
                (tmp / p.name).write_text(text, encoding="utf-8", newline="\r\n")
            tmp.rename(dest)
        self._staged = dest
        return dest

    def _cleanup(self) -> None:
        now = time.time()
        for pattern in ("resp_*.json", "request*.txt"):
            for p in self.exchange.glob(pattern):
                try:
                    if now - p.stat().st_mtime > STALE_FILE_AGE_S:
                        p.unlink()
                except OSError:
                    pass

    # -- lock file ---------------------------------------------------------
    def _acquire_lockfile(self, deadline: float) -> Path:
        lock = self.exchange / "bridge.lock"
        stale_after = self.config.timeout_s + 30
        while True:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return lock
            except FileExistsError:
                try:
                    if time.time() - lock.stat().st_mtime > stale_after:
                        lock.unlink()
                        continue
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    raise AltiumError(E_TIMEOUT, "Another request is in flight and did not finish in time.")
                time.sleep(0.1)

    # -- call --------------------------------------------------------------
    def _call(self, command: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._launcher is None and sys.platform != "win32":
            raise AltiumError(
                E_ALTIUM_NOT_FOUND,
                "The Altium bridge only works on Windows. Set ALTIUM_LITE_BRIDGE=fake to try the server without Altium.",
                hint="Run the server on the Windows machine where Altium is installed.",
            )
        exe = self._resolve_exe()
        if exe is None:
            raise AltiumError(E_ALTIUM_NOT_FOUND, "Could not find Altium's X2.EXE.")

        # Launching X2.EXE with no running Altium would start a new instance. Never do that.
        if self._process_check() is False:
            raise AltiumError(
                E_ALTIUM_NOT_FOUND,
                "Altium Designer is not running; the bridge will not start it.",
            )

        with _lock:
            if not self._secured:
                self._warnings = secure_exchange_dir(self.exchange)
                self._secured = True
            self._cleanup()
            deadline = time.monotonic() + self.config.timeout_s
            lockfile = self._acquire_lockfile(deadline)
            try:
                return self._round_trip(exe, command, params, deadline)
            finally:
                try:
                    lockfile.unlink()
                except OSError:
                    pass

    def _round_trip(self, exe: Path, command: str, params: dict[str, Any], deadline: float) -> dict[str, Any]:
        staged = self._staged or self.stage_scripts()
        req_id = uuid.uuid4().hex
        body = encode_request(req_id, command, PROTOCOL_VERSION, params)

        tmp = self.exchange / f"request.{req_id}.tmp"
        tmp.write_text(body, encoding="ascii", newline="")
        os.replace(tmp, self.exchange / "request.txt")

        resp_path = self.exchange / f"resp_{req_id}.json"
        prj = staged / "Altium_Lite.PrjScr"
        cmdline = f'"{exe}" -RScriptingSystem:RunScript(ProjectName="{prj}"|ProcName="Main>Run")'
        log.info("launch command=%s id=%s", command, req_id)
        (self._launcher or default_launcher)(cmdline)

        parse_error: str | None = None
        while time.monotonic() < deadline:
            if resp_path.exists():
                try:
                    resp = json.loads(resp_path.read_text(encoding="utf-8", errors="replace"))
                    parse_error = None
                except (OSError, ValueError) as e:  # partial write: retry
                    parse_error = str(e)
                else:
                    resp_path.unlink(missing_ok=True)
                    return self._unwrap(resp, req_id)
            time.sleep(self.config.poll_interval_s)

        if parse_error:
            err = AltiumError(E_ALTIUM_ERROR, f"Altium wrote an unreadable response: {parse_error}")
            err.wedges = True  # type: ignore[attr-defined]
            raise err
        (self.exchange / "request.txt").unlink(missing_ok=True)
        raise AltiumError(E_TIMEOUT, f"No response from Altium within {self.config.timeout_s:g}s.")

    def _unwrap(self, resp: dict[str, Any], req_id: str) -> dict[str, Any]:
        if not isinstance(resp, dict) or resp.get("id") != req_id:
            raise AltiumError(E_ALTIUM_ERROR, "Response did not match the request.")
        sv = resp.get("script_version")
        if resp.get("protocol_version") != PROTOCOL_VERSION or sv != SCRIPT_VERSION:
            raise AltiumError(
                E_SCRIPT_VERSION,
                f"Script/server version mismatch (script {sv}, protocol {resp.get('protocol_version')}; "
                f"server {SCRIPT_VERSION}, protocol {PROTOCOL_VERSION}).",
            )
        self.script_version = sv
        if not resp.get("success"):
            err = resp.get("error") or {}
            code = err.get("code")
            raise AltiumError(
                code if code in ERROR_CODES else E_ALTIUM_ERROR,
                str(err.get("message") or "Altium reported an error."),
            )
        data = resp.get("data")
        return data if isinstance(data, dict) else {}
