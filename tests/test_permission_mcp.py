"""Tests for the stdio MCP permission bridge."""

import json

from telegram_exec_notifier import permission_mcp


def test_initialize_and_tools_list():
    init = permission_mcp._handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init["result"]["serverInfo"]["name"] == "tgperm"
    tools = permission_mcp._handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert [t["name"] for t in tools["result"]["tools"]] == ["approve"]


def test_notifications_get_no_reply():
    assert permission_mcp._handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_unknown_method_and_tool_are_errors():
    assert permission_mcp._handle({"jsonrpc": "2.0", "id": 3, "method": "nope"})["error"]["code"] == -32601
    call = {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "other"}}
    assert permission_mcp._handle(call)["error"]["code"] == -32602


def test_unreachable_service_denies(monkeypatch):
    monkeypatch.setenv("TELEGRAM_NOTIFIER_URL", "http://127.0.0.1:1")
    call = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "approve", "arguments": {"tool_name": "Bash", "input": {"command": "ls"}}},
    }
    decision = json.loads(permission_mcp._handle(call)["result"]["content"][0]["text"])
    assert decision["behavior"] == "deny"
