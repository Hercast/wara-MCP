"""MCP protocol-level tests using an in-memory client session."""

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from altium_lite_mcp.bridge.fake import FakeBridge
from altium_lite_mcp.config import READ_ONLY, READ_WRITE
from altium_lite_mcp.server import build_server
from conftest import make_config

READ_TOOLS = {
    "altium_status", "altium_list_components", "altium_get_component", "altium_find_components",
    "altium_bom_summary", "altium_check_parameters", "altium_check_designators",
    "altium_project_overview", "altium_get_nets", "altium_compile_messages",
}
WRITE_TOOLS = {
    "altium_set_parameter", "altium_set_parameters_from_table", "altium_rename_parameter",
    "altium_delete_parameter", "altium_move_components", "altium_save_project",
}
TOOLS = READ_TOOLS | WRITE_TOOLS


async def session(tmp_path, mode):
    server = build_server(make_config(tmp_path, mode), FakeBridge())
    return create_connected_server_and_client_session(server._mcp_server)


async def call(client, name, args=None):
    res = await client.call_tool(name, args or {})
    return res.structuredContent


async def test_tools_and_annotations(tmp_path):
    async with await session(tmp_path, READ_ONLY) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert set(tools) == TOOLS
        for n in READ_TOOLS:
            assert tools[n].annotations.readOnlyHint is True
        for n in WRITE_TOOLS:
            assert tools[n].annotations.readOnlyHint is False
        a = tools["altium_set_parameter"].annotations
        assert a.destructiveHint is False and a.idempotentHint is True
        assert tools["altium_delete_parameter"].annotations.destructiveHint is True
        assert tools["altium_save_project"].annotations.destructiveHint is True


async def test_read_only_demo_flow(tmp_path):
    async with await session(tmp_path, READ_ONLY) as client:
        st = await call(client, "altium_status")
        assert st["ok"] and st["data"]["mode"] == "read_only"
        lst = await call(client, "altium_list_components", {"missing_parameter": "MPN"})
        assert lst["ok"] and lst["data"]["total"] == 5
        r = await call(client, "altium_set_parameter", {"changes": [{"designator": "R1", "name": "MPN", "value": "ABC-123"}]})
        assert not r["ok"] and r["error"]["code"] == "E_MODE_READ_ONLY" and r["error"]["hint"]


async def test_read_write_preview_then_apply(tmp_path):
    async with await session(tmp_path, READ_WRITE) as client:
        changes = [{"designator": d, "name": "MPN", "value": "ABC-123"} for d in ("R2", "R3")]
        pre = await call(client, "altium_set_parameter", {"changes": changes, "create_if_missing": True})
        assert pre["ok"] and pre["data"]["applied"] is False
        app = await call(client, "altium_set_parameter", {"changes": changes, "apply": True, "create_if_missing": True})
        assert app["data"]["applied"] and app["data"]["verified"] is True
        got = await call(client, "altium_get_component", {"designators": ["R3"]})
        assert got["data"]["items"][0]["parameters"]["MPN"] == "ABC-123"


async def test_errors_are_envelopes_not_crashes(tmp_path):
    async with await session(tmp_path, READ_ONLY) as client:
        r = await call(client, "altium_list_components", {"limit": 9999})
        assert not r["ok"] and r["error"]["code"] == "E_INVALID_INPUT"


async def test_new_tools_over_mcp(tmp_path):
    async with await session(tmp_path, READ_WRITE) as client:
        r = await call(client, "altium_bom_summary", {"as_csv": True})
        assert r["ok"] and r["data"]["csv"].startswith("comment,footprint,Quantity")
        r = await call(client, "altium_find_components", {"query": "stm*", "match": "wildcard", "field": "parameter:MPN"})
        assert [i["designator"] for i in r["data"]["items"]] == ["U2"]
        r = await call(client, "altium_check_designators")
        assert r["ok"] and "duplicates" in r["data"]
        r = await call(client, "altium_move_components", {"changes": [{"designator": "U1", "dx_mil": 100}]})
        assert r["ok"] and r["data"]["changes"][0]["status"] == "ok"
        r = await call(client, "altium_save_project", {})
        assert not r["ok"] and r["error"]["code"] == "E_MODE_READ_ONLY"


async def test_prompts_and_resource(tmp_path):
    async with await session(tmp_path, READ_ONLY) as client:
        prompts = {p.name for p in (await client.list_prompts()).prompts}
        assert {"fill_missing_mpns", "audit_bom"} <= prompts
        got = await client.get_prompt("fill_missing_mpns", {"mpn_list": "R2=ABC"})
        assert "Never guess" in got.messages[0].content.text
        res = await client.read_resource("altium://bom")
        assert "Quantity" in res.contents[0].text
