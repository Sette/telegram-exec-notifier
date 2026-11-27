"""Local Telegram notification endpoint and authenticated command receiver."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

MAX_OUTPUT = 3500
COMMAND_TIMEOUT = 300


def _telegram(method: str, payload: dict, *, timeout: int = 35) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    request = Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=timeout) as response:
        result = json.load(response)
    if not result.get("ok"):
        raise RuntimeError(f"Telegram {method} request failed")
    return result


def send_telegram(text: str, chat_id: str | int | None = None) -> None:
    _telegram(
        "sendMessage",
        {"chat_id": chat_id or os.environ["TELEGRAM_CHAT_ID"], "text": text[:4096]},
    )


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/notify":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > 64_000:
                self.send_error(413)
                return
            payload = json.loads(self.rfile.read(size))
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip():
                self.send_error(400, "JSON body must contain non-empty text")
                return
            send_telegram(text)
        except Exception as exc:
            self.send_error(502, str(exc))
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"sent\n")

    def log_message(self, format: str, *args: object) -> None:
        return


def _run_cli(tool: str, prompt: str, chat_id: int) -> None:
    commands = {
        "claude": ["claude", "-p", prompt, "--add-dir", str(Path.home())],
        "codex": [
            "codex",
            "--ask-for-approval",
            "never",
            "exec",
            "--sandbox",
            "workspace-write",
            "--add-dir",
            str(Path.home()),
            "--skip-git-repo-check",
            prompt,
        ],
        "kiro": [
            "kiro-cli", "chat", "--no-interactive", "--trust-tools=fs_read,fs_write", prompt
        ],
    }
    try:
        proc = subprocess.run(
            commands[tool],
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
            cwd=Path.home() if tool == "kiro" else None,
        )
        output = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()
        output = output or "(sem resposta do CLI)"
        status = "✅" if proc.returncode == 0 else f"❌ código {proc.returncode}"
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        output = (stdout + stderr).strip()
        status = f"⏱️ tempo limite ({COMMAND_TIMEOUT}s)"
    except Exception as exc:
        output = str(exc)
        status = "❌ falha ao iniciar"
    if len(output) > MAX_OUTPUT:
        output = output[:MAX_OUTPUT] + "\n… (saída truncada)"
    try:
        send_telegram(f"{tool} {status}\n\n{output}", chat_id)
    except Exception:
        # Telegram outages must not terminate the polling service.
        return


def _poll_commands() -> None:
    allowed_chat = str(os.environ["TELEGRAM_CHAT_ID"])
    offset = 0
    while True:
        try:
            updates = _telegram("getUpdates", {"offset": offset, "timeout": 25}, timeout=35)
            for update in updates.get("result", []):
                offset = max(offset, update["update_id"] + 1)
                message = update.get("message") or update.get("edited_message") or {}
                chat = message.get("chat", {})
                sender = message.get("from", {})
                if (
                    str(chat.get("id")) != allowed_chat
                    or chat.get("type") != "private"
                    or str(sender.get("id")) != allowed_chat
                ):
                    continue
                text = message.get("text", "").strip()
                if not text:
                    continue
                command, _, prompt = text.partition(" ")
                tool = command.split("@", 1)[0].lstrip("/").lower()
                prompt = prompt.strip()
                if tool in {"start", "help"}:
                    send_telegram("Envie /claude <prompt>, /codex <prompt> ou /kiro <prompt>. O CLI roda neste computador, na pasta configurada no serviço.", chat["id"])
                elif tool in {"claude", "codex", "kiro"} and prompt:
                    send_telegram(f"⏳ Iniciando {tool}…", chat["id"])
                    threading.Thread(target=_run_cli, args=(tool, prompt, chat["id"]), daemon=True).start()
                else:
                    send_telegram("Comando inválido. Use /claude <prompt>, /codex <prompt> ou /kiro <prompt>.", chat["id"])
        except Exception:
            time.sleep(3)


def _import_personal_skills_for_kiro() -> None:
    """Copy Codex and Claude personal skills into Kiro's global skill directory."""
    home = Path.home()
    destination = home / ".kiro" / "skills"
    sources = (home / ".codex" / "skills", home / ".claude" / "skills")
    for source in sources:
        if not source.is_dir():
            continue
        for skill in source.iterdir():
            if not skill.is_dir() or not (skill / "SKILL.md").is_file():
                continue
            target = destination / skill.name
            if target.exists() or target.is_symlink():
                continue
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copytree(skill, target)


def main() -> None:
    _import_personal_skills_for_kiro()
    threading.Thread(target=_poll_commands, daemon=True).start()
    address = os.getenv("TELEGRAM_NOTIFIER_HOST", "127.0.0.1")
    port = int(os.getenv("TELEGRAM_NOTIFIER_PORT", "8765"))
    with ThreadingHTTPServer((address, port), Handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
