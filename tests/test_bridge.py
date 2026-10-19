import pytest

from altium_lite_mcp.core import AltiumService
from altium_lite_mcp.models import AltiumError


def test_round_trip_through_files(emulated):
    cfg, bridge, emu = emulated
    svc = AltiumService(cfg, bridge)
    assert svc.list_components()["total"] == 10
    d = svc.set_parameter(
        [{"designator": "R2", "name": "MPN", "value": 'A "B"=C|D µ'}], apply=True
    )
    assert d["verified"] is True
    assert emu.backend.components[1]["parameters"]["MPN"] == 'A "B"=C|D µ'
    assert 'ProcName="Main>Run"' in emu.cmdlines[0] and "Altium_Lite.PrjScr" in emu.cmdlines[0]


def test_scripts_staged_with_exchange_dir_substituted(emulated):
    cfg, bridge, _ = emulated
    staged = bridge.stage_scripts()
    cfgpas = (staged / "Config.pas").read_text()
    assert str(cfg.exchange_dir) in cfgpas and "@@EXCHANGE_DIR@@" not in cfgpas
    assert (staged / "Altium_Lite.PrjScr").exists()
    assert bridge.stage_scripts() == staged  # stable hash


def test_silent_altium_times_out_and_wedges(emulated):
    cfg, bridge, emu = emulated
    emu.mode = "silent"
    with pytest.raises(AltiumError) as e:
        bridge.call("status")
    assert e.value.code == "E_TIMEOUT" and bridge.suspect_wedged
    assert not (cfg.exchange_dir / "request.txt").exists()


def test_version_mismatch(emulated):
    _, bridge, emu = emulated
    emu.mode = "badversion"
    with pytest.raises(AltiumError) as e:
        bridge.call("status")
    assert e.value.code == "E_SCRIPT_VERSION"


def test_unreadable_response_is_an_error_not_success(emulated):
    _, bridge, emu = emulated
    emu.mode = "garbage"
    with pytest.raises(AltiumError) as e:
        bridge.call("status")
    assert e.value.code == "E_ALTIUM_ERROR"


def test_script_error_codes_pass_through(emulated):
    _, bridge, emu = emulated
    emu.backend.project = None
    with pytest.raises(AltiumError) as e:
        bridge.call("get_components", {})
    assert e.value.code == "E_NO_PROJECT"


def test_lock_file_removed_after_call(emulated):
    cfg, bridge, _ = emulated
    bridge.call("status")
    assert not (cfg.exchange_dir / "bridge.lock").exists()


def test_not_windows_without_launcher(tmp_path):
    from altium_lite_mcp.bridge.altium import AltiumBridge
    import sys

    from conftest import make_config

    if sys.platform == "win32":
        pytest.skip("windows")
    with pytest.raises(AltiumError) as e:
        AltiumBridge(make_config(tmp_path)).call("status")
    assert e.value.code == "E_ALTIUM_NOT_FOUND"
