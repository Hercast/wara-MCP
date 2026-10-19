import pytest

from altium_lite_mcp.bridge.protocol import (
    encode_request,
    escape_value,
    parse_request,
    unescape_value,
    unflatten,
)
from altium_lite_mcp.models import AltiumError

AWKWARD = ['say "hi"', "back\\slash", "a|b=c", "line1\nline2\r\nx", "café µF", "100%", "=leading"]


@pytest.mark.parametrize("s", AWKWARD)
def test_round_trip(s):
    assert unescape_value(escape_value(s)) == s


def test_escaped_is_single_line_ascii():
    e = escape_value("a\nbé")
    assert "\n" not in e and e.isascii()


def test_above_latin1_rejected():
    with pytest.raises(AltiumError) as e:
        escape_value("€")
    assert e.value.code == "E_INVALID_INPUT"


def test_request_round_trip_lists_and_objects():
    params = {
        "designator": ["R1", "R2"],
        "include_pins": True,
        "change": [{"designator": "R1", "name": "MPN", "value": 'x=y "q"\n'}],
    }
    text = encode_request("abc", "set_parameters", 1, params)
    flat = parse_request(text)
    assert flat["command"] == "set_parameters" and flat["id"] == "abc"
    back = unflatten({k: v for k, v in flat.items() if k not in ("protocol", "id", "command")})
    assert back["designator"] == ["R1", "R2"]
    assert back["include_pins"] == "true"
    assert back["change"] == [{"designator": "R1", "name": "MPN", "value": 'x=y "q"\n'}]
