import pytest

from altium_lite_mcp import analysis
from altium_lite_mcp.bridge.fake import sample_design
from altium_lite_mcp.models import AltiumError

ROWS = sample_design()


def des(rows):
    return [r["designator"] for r in rows]


def test_find_modes():
    assert des(analysis.find(ROWS, "0805")) == ["C2"]
    assert des(analysis.find(ROWS, "res", field="library_ref", match="exact")) == ["R1", "R2", "R3", "R4"]
    assert des(analysis.find(ROWS, "stm*", field="parameter:MPN", match="wildcard")) == ["U2"]


def test_find_combined_filters():
    got = analysis.find(ROWS, "0603", field="footprint", designator_prefix="R", missing_parameter="MPN")
    assert des(got) == ["R1", "R2", "R3"]


def test_bom_groups_and_csv_injection():
    groups = analysis.bom_summary(ROWS, ["comment", "footprint"])
    cap = next(g for g in groups if g["key"]["comment"] == "100nF")
    assert cap["quantity"] == 2 and cap["designators"] == ["C1", "C3"]
    rows = [{"designator": "R1", "comment": "=cmd()", "footprint": "0603", "parameters": {}}]
    csv_text = analysis.bom_csv(analysis.bom_summary(rows, ["comment"]), ["comment"])
    assert "'=cmd()" in csv_text


def test_check_parameters_missing_and_inconsistent():
    res = analysis.check_parameters(ROWS, ["MPN"], ["comment", "footprint"])["MPN"]
    assert res["missing"] == ["C2", "D1", "R1", "R2", "R3"]
    assert len(res["inconsistent"]) == 1
    assert res["inconsistent"][0]["group"] == {"comment": "100nF", "footprint": "0603"}


def test_check_designators():
    rows = ROWS + [{"designator": "R1", "parameters": {}}, {"designator": "R?", "parameters": {}}, {"designator": "R8", "parameters": {}}]
    res = analysis.check_designators(rows)
    assert res["duplicates"] == ["R1"]
    assert res["unannotated"] == ["R?"]
    assert res["gaps"]["R"]["missing_numbers"] == [5, 6, 7]


def test_overview_and_nets():
    ov = analysis.overview(ROWS, [], "P")
    assert ov["component_count"] == 10 and ov["by_prefix"]["R"] == 4
    nets = analysis.nets_from_components(ROWS[:2])
    assert {"net": "GND", "pins": ["R1.2", "R2.2"]} in nets


def test_parse_table_csv():
    ch = analysis.parse_table_csv("Designator,MPN,Value\nR1,ABC,\nR2,,4k7\n\n")
    assert ch == [
        {"designator": "R1", "name": "MPN", "value": "ABC"},
        {"designator": "R2", "name": "Value", "value": "4k7"},
    ]
    for bad in ["", "MPN\nx", "Designator,MPN\nR1", "Designator\n" + "x" * 200_000]:
        with pytest.raises(AltiumError):
            analysis.parse_table_csv(bad)
