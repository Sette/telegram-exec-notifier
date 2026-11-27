"""Minimal stdio MCP server that forwards Claude permission prompts to the notifier service."""

from __future__ import annotations

import json
import os
import sys
from urllib.request import Request, urlopen

PROTOCOL_VERSION = "2024-11-05"
TOOL = {
    "name": "approve",
    "description": "Ask the user on Telegram whether a tool call is allowed.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "tool_name": {"type": "string"},
            "input": {"type": "object"},
        },
        "required": ["tool_name", "input"],
    },
}


def _deny(message: str) -> dict:
    return {"behavior": "deny", "message": message}


def _decide(arguments: dict) -> dict:
    """Ask the local service for a decision; any failure means deny."""
    base = os.getenv("TELEGRAM_NOTIFIER_URL", "http://127.0.0.1:8765").rstrip("/")
    body = {
        "token": os.environ.get("TELEGRAM_PERMISSION_TOKEN", ""),
        "tool_name": arguments.get("tool_name", ""),
        "input": arguments.get("input", {}),
        "cwd": os.getcwd(),
    }
    request = Request(
        f"{base}/permission",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        timeout = int(os.getenv("TELEGRAM_PERMISSION_TIMEOUT", "300")) + 30
        with urlopen(request, timeout=timeout) as response:
            decision = json.load(response)
    except Exception as exc:
        return _deny(f"Permission service unavailable: {exc}")
    if decision.get("behavior") == "allow":
        return {"behavior": "allow", "updatedInput": arguments.get("input", {})}
    return _deny(decision.get("message") or "Denied by the user on Telegram.")


def _handle(request: dict) -> dict | None:
    method = request.get("method")
    request_id = request.get("id")
    if request_id is None:  # notification, no reply
        return None
    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "tgperm", "version": "0.1.0"},
        }
    elif method == "tools/list":
        result = {"tools": [TOOL]}
    elif method == "tools/call":
        params = request.get("params", {})
        if params.get("name") != TOOL["name"]:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": "unknown tool"},
            }
        decision = _decide(params.get("arguments", {}))
        result = {"content": [{"type": "text", "text": json.dumps(decision)}]}
    elif method == "ping":
        result = {}
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "method not found"},
        }
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            response = _handle(json.loads(line))
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(exc)}}
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
