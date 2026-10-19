import pytest

from altium_lite_mcp.config import READ_WRITE_SAVE
from altium_lite_mcp.core import AltiumService
from altium_lite_mcp.models import AltiumError
from conftest import make_config


def test_closed_sheet_is_refused_with_reason(service, backend):
    backend.closed_sheets.add("MCU.SchDoc")
    d = service.set_parameter([{"designator": "U2", "name": "MPN", "value": "X"}], apply=True)
    r = d["changes"][0]
    assert r["status"] == "refused" and "not open" in r["reason"] and d["applied"] is False
    assert backend.components[9]["parameters"]["MPN"] == "STM32G031F6P6"


def test_apply_reports_modified_sheets(service):
    d = service.set_parameter([{"designator": "R2", "name": "MPN", "value": "Z"}], apply=True)
    assert d["sheets_modified"] == ["Power.SchDoc"]


def test_snapshot_cache_and_invalidation(tmp_path, backend):
    svc = AltiumService(make_config(tmp_path), backend)
    svc.list_components()
    svc.list_components()
    svc.find_components("R")
    assert sum(c == "get_components" for c, _ in backend.calls) == 1
    svc.list_components(refresh=True)
    assert sum(c == "get_components" for c, _ in backend.calls) == 2
    svc.set_parameter([{"designator": "R2", "name": "MPN", "value": "Q"}], apply=True)
    assert svc.get_component(["R2"])["items"][0]["parameters"]["MPN"] == "Q"


def test_cache_disabled_with_zero_ttl(tmp_path, backend):
    from dataclasses import replace

    svc = AltiumService(replace(make_config(tmp_path), cache_ttl_s=0), backend)
    svc.list_components()
    svc.list_components()
    assert sum(c == "get_components" for c, _ in backend.calls) == 2


def test_from_table_chunks_and_applies(service, backend):
    rows = "\n".join(f"R{i}" for i in (1, 2, 3, 4))
    d = service.set_parameters_from_table("Designator,MPN\n" + "\n".join(f"{r},M-{r}" for r in rows.split()), apply=True, create_if_missing=True)
    assert d["verified"] is True
    assert backend.components[0]["parameters"]["MPN"] == "M-R1"


def test_from_table_chunking_sends_multiple_requests(service, backend):
    backend.components = [
        {"designator": f"R{i}", "comment": "", "library_ref": "", "footprint": "", "sheet": "A.SchDoc",
         "parameters": {"MPN": ""}, "pins": []} for i in range(1, 121)
    ]
    csv_text = "Designator,MPN\n" + "\n".join(f"R{i},V{i}" for i in range(1, 121))
    d = service.set_parameters_from_table(csv_text, apply=True)
    assert d["verified"] is True
    assert sum(c == "set_parameters" for c, _ in backend.calls) == 3


def test_rename_project_wide(service, backend):
    service.set_parameter([{"designator": "R1", "name": "Mfr Part", "value": "X"}], apply=True, create_if_missing=True)
    pre = service.rename_parameter("Mfr Part", "MPN")
    assert [r["designator"] for r in pre["changes"]] == ["R1"] and pre["changes"][0]["status"] == "ok"
    assert pre["applied"] is False
    d = service.rename_parameter("Mfr Part", "MPN", apply=True)
    assert d["verified"] is True
    assert backend.components[0]["parameters"]["MPN"] == "X" and "Mfr Part" not in backend.components[0]["parameters"]


def test_rename_refuses_when_target_exists_and_reserved(service):
    d = service.rename_parameter("Value", "MPN", ["U1", "R2"], apply=True)
    st = {r["designator"]: r["status"] for r in d["changes"]}
    assert st["R2"] == "refused" and st["U1"] == "refused"
    with pytest.raises(AltiumError):
        service.rename_parameter("Comment", "X")
    with pytest.raises(AltiumError):
        service.rename_parameter("MPN", "mpn")


def test_delete_parameter(service, backend):
    pre = service.delete_parameter("Color")
    assert pre["changes"][0]["old"] == "Green" and not pre["applied"]
    d = service.delete_parameter("Color", apply=True)
    assert d["verified"] is True and "Color" not in backend.components[7]["parameters"]
    with pytest.raises(AltiumError):
        service.delete_parameter("Designator")


def test_bulk_target_cap(service, backend):
    backend.components = [
        {"designator": f"R{i}", "comment": "", "library_ref": "", "footprint": "", "sheet": "A", "parameters": {"X": "1"}, "pins": []}
        for i in range(1, 502)
    ]
    with pytest.raises(AltiumError) as e:
        service.delete_parameter("X")
    assert e.value.code == "E_INVALID_INPUT"


def test_move_preview_apply_and_verify(service, backend):
    chg = [{"designator": "R1", "dx_mil": 25.5, "dy_mil": -10}, {"designator": "U1", "rotation_deg": 90}, {"designator": "ZZ", "x_mil": 1, "y_mil": 1}]
    pre = service.move_components(chg)
    assert not pre["applied"] and backend.components[0]["x_iu"] == 1_000_000
    assert pre["changes"][0]["new"]["x_mil"] == pre["changes"][0]["old"]["x_mil"] + 25.5
    assert pre["changes"][2]["status"] == "not_found"
    d = service.move_components(chg, apply=True)
    assert d["verified"] is True
    assert backend.components[0]["x_iu"] == 1_000_000 + 255_000 and backend.components[0]["y_iu"] == 500_000 - 100_000
    assert backend.components[8]["rotation_cd"] == 9000


@pytest.mark.parametrize(
    "bad",
    [
        {"designator": "R1"},
        {"designator": "R1", "dx_mil": 1, "x_mil": 2},
        {"designator": "R1", "dx_mil": float("nan")},
        {"designator": "R1", "dx_mil": 1e9},
        {"designator": "R1", "rotation_deg": 360},
    ],
)
def test_move_validation(service, bad):
    with pytest.raises(AltiumError) as e:
        service.move_components([bad])
    assert e.value.code == "E_INVALID_INPUT"


def test_move_no_change(service):
    d = service.move_components([{"designator": "R1", "dx_mil": 0}], apply=True)
    assert d["changes"][0]["status"] == "no_change" and d["applied"] is False


def test_save_requires_save_mode(service):
    with pytest.raises(AltiumError) as e:
        service.save_project(confirm=True)
    assert e.value.code == "E_MODE_READ_ONLY" and "read_write_save" in e.value.message


def test_save_preview_and_confirm(tmp_path, backend):
    svc = AltiumService(make_config(tmp_path, READ_WRITE_SAVE), backend)
    svc.set_parameter([{"designator": "R2", "name": "MPN", "value": "S"}], apply=True)
    pre = svc.save_project()
    assert pre["would_save"] == ["Power.SchDoc"] and pre["saved"] == [] and "save_project" not in [c for c, _ in backend.calls]
    d = svc.save_project(confirm=True)
    assert d["saved"] == ["Power.SchDoc"] and d["verified"] is True
    assert svc.save_project(confirm=True)["note"] == "Nothing to save."


def test_compile_messages_and_nets(service):
    d = service.compile_messages(severity="error")
    assert d["total"] == 1 and d["counts"] == {"Error": 1, "Warning": 1}
    n = service.get_nets(["R1", "R2", "QQ"])
    assert n["not_found"] == ["QQ"] and any(x["net"] == "NetA" for x in n["nets"])


def test_service_analysis_validation(service):
    for call in (
        lambda: service.find_components("x", field="bogus"),
        lambda: service.find_components(""),
        lambda: service.find_components("x", match="regex"),
        lambda: service.bom_summary(group_by=["designator"]),
        lambda: service.check_parameters([]),
    ):
        with pytest.raises(AltiumError) as e:
            call()
        assert e.value.code == "E_INVALID_INPUT"
    assert service.project_overview()["component_count"] == 10
    assert service.check_parameters(["MPN"])["parameters"]["MPN"]["missing_count"] == 5
