import json
import time
from pathlib import Path

import pytest

from altium_lite_mcp import PROTOCOL_VERSION, SCRIPT_VERSION
from altium_lite_mcp.bridge.altium import AltiumBridge
from altium_lite_mcp.bridge.fake import FakeBridge
from altium_lite_mcp.bridge.protocol import parse_request, unflatten
from altium_lite_mcp.config import READ_ONLY, READ_WRITE, Config
from altium_lite_mcp.core import AltiumService
from altium_lite_mcp.models import AltiumError


def make_config(tmp_path: Path, mode: str = READ_WRITE, **kw) -> Config:
    return Config(mode=mode, exchange_dir=tmp_path / "ex", timeout_s=kw.pop("timeout_s", 2.0), poll_interval_s=0.02, **kw)


class ScriptEmulator:
    """Plays the DelphiScript's role: reads request.txt, answers with resp_<id>.json."""

    def __init__(self, exchange: Path, backend: FakeBridge):
        self.exchange = exchange
        self.backend = backend
        self.mode = "normal"  # normal | silent | garbage | badversion
        self.cmdlines: list[str] = []

    def __call__(self, cmdline: str) -> None:
        self.cmdlines.append(cmdline)
        if self.mode == "silent":
            return
        flat = parse_request((self.exchange / "request.txt").read_text())
        (self.exchange / "request.txt").unlink()
        rid = flat["id"]
        params = unflatten({k: v for k, v in flat.items() if k not in ("protocol", "id", "command")})
        resp = {"id": rid, "protocol_version": PROTOCOL_VERSION, "script_version": SCRIPT_VERSION}
        try:
            data = self.backend._call(flat["command"], params)
            resp.update(success=True, data=data, error=None)
        except AltiumError as e:
            resp.update(success=False, data=None, error={"code": e.code, "message": e.message})
        if self.mode == "badversion":
            resp["script_version"] = "0.0.0"
        body = "{not json" if self.mode == "garbage" else json.dumps(resp)
        (self.exchange / f"resp_{rid}.json").write_text(body)


@pytest.fixture
def backend():
    return FakeBridge()


@pytest.fixture
def emulated(tmp_path, backend):
    cfg = make_config(tmp_path)
    emu = ScriptEmulator(cfg.exchange_dir, backend)
    cfg.exchange_dir.mkdir(parents=True)
    bridge = AltiumBridge(cfg, launcher=emu)
    return cfg, bridge, emu


@pytest.fixture
def service(tmp_path, backend):
    return AltiumService(make_config(tmp_path), backend)


@pytest.fixture
def ro_service(tmp_path, backend):
    return AltiumService(make_config(tmp_path, READ_ONLY), backend)
