import os
import stat
import sys

import pytest

from altium_lite_mcp.bridge.altium import AltiumBridge, secure_exchange_dir
from altium_lite_mcp.config import READ_WRITE_SAVE, Config, default_exchange_dir
from altium_lite_mcp.core import AltiumService
from altium_lite_mcp.models import AltiumError
from conftest import ScriptEmulator, make_config
from altium_lite_mcp.bridge.fake import FakeBridge


@pytest.mark.skipif(sys.platform == "win32", reason="posix permissions")
def test_exchange_dir_locked_down_to_owner(tmp_path):
    d = tmp_path / "ex"
    d.mkdir(mode=0o777)
    d.chmod(0o777)
    secure_exchange_dir(d)
    assert stat.S_IMODE(d.stat().st_mode) == 0o700


@pytest.mark.skipif(sys.platform == "win32", reason="posix ownership")
def test_foreign_owned_dir_refused(tmp_path, monkeypatch):
    d = tmp_path / "ex"
    d.mkdir()
    monkeypatch.setattr(os, "getuid", lambda: os.stat(d).st_uid + 1)
    with pytest.raises(AltiumError):
        secure_exchange_dir(d)


def test_default_exchange_dir_is_per_user_not_public(monkeypatch):
    if os.name == "nt":
        monkeypatch.setenv("USERNAME", "Jane Doe")
        p = str(default_exchange_dir())
        assert "Public" not in p and " " not in p.split("altium_lite_mcp")[1]
    else:
        assert "Public" not in str(default_exchange_dir())


def test_bridge_never_launches_when_altium_not_running(tmp_path):
    cfg = make_config(tmp_path)
    launched = []
    bridge = AltiumBridge(cfg, launcher=launched.append, process_check=lambda: False)
    with pytest.raises(AltiumError) as e:
        bridge.call("status")
    assert e.value.code == "E_ALTIUM_NOT_FOUND" and launched == []
    assert not bridge.suspect_wedged


def test_status_reports_not_running_without_launch(tmp_path):
    cfg = make_config(tmp_path)
    launched = []
    svc = AltiumService(cfg, AltiumBridge(cfg, launcher=launched.append, process_check=lambda: False))
    d = svc.status()
    assert d["altium"]["running"] is False and launched == []


def test_unreadable_response_marks_wedged(emulated):
    _, bridge, emu = emulated
    emu.mode = "garbage"
    with pytest.raises(AltiumError):
        bridge.call("status")
    assert bridge.suspect_wedged


def test_config_modes_and_ttl():
    c = Config.from_env({"ALTIUM_LITE_MODE": "READ_WRITE_SAVE", "ALTIUM_LITE_CACHE_TTL": "0"})
    assert c.mode == READ_WRITE_SAVE and c.can_save and c.writable and c.cache_ttl_s == 0
    bad = Config.from_env({"ALTIUM_LITE_MODE": "root", "ALTIUM_LITE_CACHE_TTL": "-1"})
    assert bad.mode == "read_only" and not bad.writable and len(bad.warnings) == 2


def test_new_commands_round_trip_through_files(emulated):
    cfg, bridge, emu = emulated
    svc = AltiumService(cfg, bridge)
    d = svc.move_components([{"designator": "R1", "x_mil": 5, "y_mil": 6, "rotation_deg": 45.5}], apply=True)
    assert d["verified"] is True
    assert emu.backend.components[0]["x_iu"] == 50000 and emu.backend.components[0]["rotation_cd"] == 4550
    d = svc.rename_parameter("Value", "Val", ["R1"], apply=True)
    assert d["verified"] is True
