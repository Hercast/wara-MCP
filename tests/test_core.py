import pytest

from altium_lite_mcp.models import AltiumError


def code(exc_info):
    return exc_info.value.code


def test_status_ok(service):
    d = service.status()
    assert d["mode"] == "read_write"
    assert d["active_project"]["name"] == "Demo.PrjPcb"
    assert d["altium"]["running"] is True


def test_status_when_altium_closed(service, backend):
    backend.closed = True
    d = service.status()
    assert d["altium"]["running"] is False
    assert any("E_ALTIUM_NOT_FOUND" in w for w in d["warnings"])


def test_list_and_filters(service):
    d = service.list_components()
    assert d["total"] == 10 and not d["truncated"]
    assert [i["designator"] for i in d["items"]][:5] == ["C1", "C2", "C3", "D1", "R1"]
    assert "parameters" not in d["items"][0]
    miss = service.list_components(missing_parameter="mpn")
    assert {i["designator"] for i in miss["items"]} == {"R1", "R2", "R3", "C2", "C3", "D1"}
    assert service.list_components(designator_prefix="u")["total"] == 2


def test_list_pagination(service):
    d = service.list_components(limit=3, offset=0)
    assert len(d["items"]) == 3 and d["truncated"] and d["total"] == 10


@pytest.mark.parametrize("limit,offset", [(0, 0), (501, 0), (10, -1)])
def test_list_bad_args(service, limit, offset):
    with pytest.raises(AltiumError) as e:
        service.list_components(limit=limit, offset=offset)
    assert code(e) == "E_INVALID_INPUT"


def test_get_component(service):
    d = service.get_component(["r1", "ZZ9"], include_pins=True)
    assert d["items"][0]["designator"] == "R1"
    assert d["items"][0]["pins"]
    assert d["not_found"] == ["ZZ9"]


def test_get_component_limits(service):
    with pytest.raises(AltiumError):
        service.get_component([])
    with pytest.raises(AltiumError):
        service.get_component([f"R{i}" for i in range(26)])
    with pytest.raises(AltiumError):
        service.get_component(["R1; drop"])


def ch(des, name="MPN", value="ABC-123"):
    return {"designator": des, "name": name, "value": value}


def test_set_refused_in_read_only(ro_service, backend):
    with pytest.raises(AltiumError) as e:
        ro_service.set_parameter([ch("R1")])
    assert code(e) == "E_MODE_READ_ONLY"
    assert backend.calls == []


def test_preview_changes_nothing(service, backend):
    d = service.set_parameter([ch("R2"), ch("R4"), ch("ZZ9")], create_if_missing=False)
    st = {r["designator"]: r["status"] for r in d["changes"]}
    assert st == {"R2": "ok", "R4": "ok", "ZZ9": "not_found"}
    assert d["applied"] is False
    assert not any(c == "set_parameters" for c, _ in backend.calls)


def test_apply_and_verify(service, backend):
    d = service.set_parameter([ch("R2"), ch("R4", value="RC0603FR-07100RL")], apply=True)
    st = {r["designator"]: r["status"] for r in d["changes"]}
    assert st == {"R2": "ok", "R4": "no_change"}
    assert d["applied"] and d["verified"] is True
    assert backend.components[1]["parameters"]["MPN"] == "ABC-123"
    assert "NOT saved" in d["note"]


def test_missing_parameter_needs_create_flag(service, backend):
    d = service.set_parameter([ch("R1")], apply=True)
    assert d["changes"][0]["status"] == "refused" and d["applied"] is False
    d = service.set_parameter([ch("R1")], apply=True, create_if_missing=True)
    assert d["changes"][0]["status"] == "ok" and d["verified"] is True


def test_reserved_refused(service):
    d = service.set_parameter([ch("R1", name="Designator", value="R9")], apply=True, create_if_missing=True)
    assert d["changes"][0]["status"] == "refused"


def test_set_validation(service):
    for bad in [ch("R1", value="x" * 256), ch("R1", value="a\nb"), ch("R1", value="€"), ch("R1", name="a=b")]:
        with pytest.raises(AltiumError) as e:
            service.set_parameter([bad])
        assert code(e) == "E_INVALID_INPUT"
    with pytest.raises(AltiumError):
        service.set_parameter([ch("R1"), ch("r1", name="mpn")])
    with pytest.raises(AltiumError):
        service.set_parameter([])


def test_timeout_wedges_and_blocks_apply_until_read(service, backend):
    backend.hang = True
    with pytest.raises(AltiumError) as e:
        service.list_components()
    assert code(e) == "E_TIMEOUT" and backend.suspect_wedged
    backend.hang = False
    with pytest.raises(AltiumError) as e:
        service.set_parameter([ch("R2")], apply=True)
    assert code(e) == "E_BRIDGE_WEDGED"
    service.status()
    assert not backend.suspect_wedged
    assert service.set_parameter([ch("R2")], apply=True)["applied"]


def test_untrusted_text_is_clipped(service, backend):
    backend.components[0]["comment"] = "x" * 1000
    assert len(service.list_components()["items"][0]["comment"]) <= 255
