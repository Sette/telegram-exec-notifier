"""Tests for server helpers that do not need Telegram."""

import json

from telegram_exec_notifier import server


def test_inside_auto_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CLAUDE_AUTO_DIR", str(tmp_path))
    (tmp_path / "proj").mkdir()
    assert server._inside_auto_dir(str(tmp_path / "proj"))
    assert not server._inside_auto_dir(str(tmp_path.parent))
    assert not server._inside_auto_dir("")


def test_auto_dir_disabled_without_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_CLAUDE_AUTO_DIR", raising=False)
    assert not server._inside_auto_dir("/tmp")


def test_ask_permission_allows_inside_auto_dir_without_telegram(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CLAUDE_AUTO_DIR", str(tmp_path))
    assert server._ask_permission("Bash", {"command": "ls"}, str(tmp_path)) == {"behavior": "allow"}


def test_describe_tool_prefers_command_then_path():
    assert server._describe_tool("Bash", {"command": "ls"}) == "Bash: ls"
    assert server._describe_tool("Edit", {"file_path": "/a"}) == "Edit: /a"


def test_scan_session_reads_cwd_and_title(tmp_path):
    path = tmp_path / "s.jsonl"
    lines = [
        {"type": "user", "cwd": "/work", "entrypoint": "cli", "message": {"content": "hello there"}},
        {"type": "ai-title", "aiTitle": "My title"},
    ]
    path.write_text("\n".join(json.dumps(line) for line in lines))
    assert server._scan_session(path) == {"cwd": "/work", "entrypoint": "cli", "title": "My title"}


def test_format_sessions_marks_the_active_one():
    sessions = [{"id": "a", "cwd": "/x/proj", "title": "T", "mtime": 0}]
    assert "▶" in server._format_sessions(sessions, "a")
    assert "▶" not in server._format_sessions(sessions, "b")
