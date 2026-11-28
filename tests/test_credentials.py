"""Tests for the encrypted credential loader."""

from telegram_exec_notifier import credentials


def test_parse_handles_comments_quotes_and_blank_lines():
    text = '# c\n\nTELEGRAM_BOT_TOKEN="tok"\nTELEGRAM_CHAT_ID=42\nBAD LINE\n'
    assert credentials._parse(text) == {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "42"}


def test_load_credentials_exports_values(tmp_path, monkeypatch):
    (tmp_path / "environment").write_text("TELEGRAM_CHAT_ID=99\n")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    credentials.load_credentials()
    assert credentials.os.environ["TELEGRAM_CHAT_ID"] == "99"
    monkeypatch.delenv("TELEGRAM_CHAT_ID")


def test_load_credentials_without_directory_is_a_noop(monkeypatch):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    credentials.load_credentials()


def test_child_env_hides_the_bot_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", "/run/x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    env = credentials.child_env()
    assert "TELEGRAM_BOT_TOKEN" not in env
    assert "CREDENTIALS_DIRECTORY" not in env
    assert env["TELEGRAM_CHAT_ID"] == "1"
