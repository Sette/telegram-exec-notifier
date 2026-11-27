"""Local Telegram notification endpoint and authenticated command receiver."""

from __future__ import annotations

import json
import logging
import os
import queue
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from .credentials import child_env, load_credentials
from .formatting import markdown_to_telegram_html

# Must run before the module-level settings below read the environment.
load_credentials()

MAX_OUTPUT = 3500
HEARTBEAT = int(os.getenv("TELEGRAM_HEARTBEAT", "120"))
BACKGROUND_TIMEOUT = int(os.getenv("TELEGRAM_BACKGROUND_TIMEOUT", "86400"))
log = logging.getLogger("telegram_exec_notifier")
COMMAND_TIMEOUT = int(os.getenv("TELEGRAM_COMMAND_TIMEOUT", "1800"))
PERMISSION_TIMEOUT = int(os.getenv("TELEGRAM_PERMISSION_TIMEOUT", "300"))
PERMISSION_TOKEN = secrets.token_hex(16)
PERMISSION_TOOL = "mcp__tgperm__approve"
SESSIONS_DIR = Path.home() / ".claude" / "projects"
STATE_FILE = Path.home() / ".config" / "telegram-exec-notifier" / "state.json"
TAIL_BYTES = 256_000
SYSTEM_HINT = (
    "Você responde via Telegram. Transcrições de outras sessões do Claude Code "
    f"estão em {SESSIONS_DIR}/<projeto>/<session-id>.jsonl; leia-as quando o usuário "
    "perguntar sobre experimentos ou trabalhos de outras sessões. Seja conciso."
)

_state_lock = threading.Lock()
_session_locks: dict[str, threading.Lock] = {}
_last_listing: list[dict] = []
_pending: dict[str, dict] = {}
_pending_lock = threading.Lock()


def _auto_dir() -> Path | None:
    """Folder where Claude runs without asking, from TELEGRAM_CLAUDE_AUTO_DIR."""
    raw = os.getenv("TELEGRAM_CLAUDE_AUTO_DIR", "").strip()
    return Path(raw).expanduser().resolve() if raw else None


def _inside_auto_dir(cwd: str) -> bool:
    auto = _auto_dir()
    if auto is None or not cwd:
        return False
    try:
        return Path(cwd).resolve().is_relative_to(auto)
    except (OSError, ValueError):
        return False


def _describe_tool(tool_name: str, tool_input: dict) -> str:
    detail = (
        tool_input.get("command")
        or tool_input.get("file_path")
        or tool_input.get("path")
        or tool_input.get("url")
        or json.dumps(tool_input, ensure_ascii=False)
    )
    return f"{tool_name}: {str(detail)[:500]}"


def _ask_permission(tool_name: str, tool_input: dict, cwd: str) -> dict:
    """Ask on Telegram and block until answered or timed out."""
    if _inside_auto_dir(cwd):
        return {"behavior": "allow"}
    request_id = secrets.token_hex(6)
    entry = {"event": threading.Event(), "allowed": False}
    with _pending_lock:
        _pending[request_id] = entry
    text = f"🔐 Permissão solicitada\n{_describe_tool(tool_name, tool_input)}\n📁 {cwd}"
    try:
        sent = _telegram(
            "sendMessage",
            {
                "chat_id": os.environ["TELEGRAM_CHAT_ID"],
                "text": text[:4096],
                "reply_markup": {
                    "inline_keyboard": [
                        [
                            {"text": "✅ Permitir", "callback_data": f"p:{request_id}:1"},
                            {"text": "❌ Negar", "callback_data": f"p:{request_id}:0"},
                        ]
                    ]
                },
            },
        )
        message_id = sent["result"]["message_id"]
        answered = entry["event"].wait(PERMISSION_TIMEOUT)
    except Exception as exc:
        with _pending_lock:
            _pending.pop(request_id, None)
        return {"behavior": "deny", "message": f"Could not ask on Telegram: {exc}"}
    with _pending_lock:
        _pending.pop(request_id, None)
    if not answered:
        _edit_message(message_id, f"⏱️ Expirou (negado)\n{text}")
        return {"behavior": "deny", "message": "No answer on Telegram in time; denied."}
    if entry["allowed"]:
        return {"behavior": "allow"}
    return {"behavior": "deny", "message": "The user denied this action on Telegram."}


def _edit_message(message_id: int, text: str) -> None:
    try:
        _telegram(
            "editMessageText",
            {"chat_id": os.environ["TELEGRAM_CHAT_ID"], "message_id": message_id, "text": text[:4096]},
        )
    except Exception:
        return


def _handle_callback(callback: dict, allowed_chat: str) -> None:
    message = callback.get("message") or {}
    if (
        str(message.get("chat", {}).get("id")) != allowed_chat
        or str(callback.get("from", {}).get("id")) != allowed_chat
    ):
        return
    parts = str(callback.get("data", "")).split(":")
    if len(parts) != 3 or parts[0] != "p":
        return
    with _pending_lock:
        entry = _pending.get(parts[1])
    try:
        _telegram("answerCallbackQuery", {"callback_query_id": callback["id"]})
    except Exception:
        pass
    if entry is None:
        return
    entry["allowed"] = parts[2] == "1"
    entry["event"].set()
    verdict = "✅ Permitido" if entry["allowed"] else "❌ Negado"
    _edit_message(message["message_id"], f"{verdict}\n{message.get('text', '')}")


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


def send_markdown(text: str, chat_id: str | int | None = None) -> None:
    """Send Markdown as Telegram HTML, falling back to plain text if it is rejected."""
    target = chat_id or os.environ["TELEGRAM_CHAT_ID"]
    try:
        _telegram(
            "sendMessage",
            {"chat_id": target, "text": markdown_to_telegram_html(text)[:4096], "parse_mode": "HTML"},
        )
    except Exception:
        send_telegram(text, chat_id)


def send_telegram(text: str, chat_id: str | int | None = None) -> None:
    _telegram(
        "sendMessage",
        {"chat_id": chat_id or os.environ["TELEGRAM_CHAT_ID"], "text": text[:4096]},
    )


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path == "/permission":
            self._permission()
            return
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

    def _permission(self) -> None:
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > 64_000:
                self.send_error(413)
                return
            payload = json.loads(self.rfile.read(size))
            if not secrets.compare_digest(str(payload.get("token", "")), PERMISSION_TOKEN):
                self.send_error(403)
                return
            tool_input = payload.get("input")
            decision = _ask_permission(
                str(payload.get("tool_name", "")),
                tool_input if isinstance(tool_input, dict) else {},
                str(payload.get("cwd", "")),
            )
        except Exception as exc:
            decision = {"behavior": "deny", "message": str(exc)}
        body = json.dumps(decision).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def _load_state() -> dict:
    try:
        data = json.loads(STATE_FILE.read_text())
        return {"id": data.get("id"), "cwd": data.get("cwd"), "title": data.get("title")}
    except (OSError, ValueError):
        return {"id": None, "cwd": None, "title": None}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))


def _scan_session(path: Path) -> dict:
    """Extract cwd and title from the head and tail of a session transcript."""
    cwd = title = first_prompt = entrypoint = None
    with path.open("rb") as handle:
        head = handle.read(TAIL_BYTES).decode(errors="replace")
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        tail = ""
        if size > TAIL_BYTES:
            handle.seek(size - TAIL_BYTES)
            tail = handle.read().decode(errors="replace")
    for line in head.splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        cwd = cwd or entry.get("cwd")
        entrypoint = entrypoint or entry.get("entrypoint")
        if first_prompt is None and entry.get("type") == "user":
            content = entry.get("message", {}).get("content")
            if isinstance(content, str) and not content.startswith("<"):
                first_prompt = content
        if entry.get("type") == "ai-title":
            title = entry.get("aiTitle") or title
        if cwd and title:
            break
    for line in reversed((tail or head).splitlines()):
        if '"ai-title"' in line:
            try:
                title = json.loads(line).get("aiTitle") or title
            except ValueError:
                continue
            break
    title = title or (first_prompt or "(sem título)")
    return {"cwd": cwd, "entrypoint": entrypoint, "title": " ".join(title.split())[:70]}


def _list_sessions(limit: int = 10) -> list[dict]:
    """Return the most recent Claude Code sessions, newest first."""
    files = sorted(SESSIONS_DIR.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    sessions = []
    for path in files:
        if len(sessions) >= limit:
            break
        try:
            info = _scan_session(path)
        except OSError:
            continue
        # Skip runs started by this bot itself (headless `claude -p`).
        if not info["cwd"] or info["entrypoint"] == "sdk-cli":
            continue
        sessions.append({"id": path.stem, "mtime": path.stat().st_mtime, **info})
    return sessions


def _ago(timestamp: float) -> str:
    seconds = int(time.time() - timestamp)
    if seconds < 3600:
        return f"há {max(seconds // 60, 1)} min"
    if seconds < 86400:
        return f"há {seconds // 3600} h"
    return f"há {seconds // 86400} d"


def _format_sessions(sessions: list[dict], active_id: str | None) -> str:
    if not sessions:
        return "Nenhuma sessão encontrada."
    lines = []
    for number, item in enumerate(sessions, 1):
        mark = "▶ " if item["id"] == active_id else ""
        lines.append(f"{number}. {mark}[{Path(item['cwd']).name}] {item['title']} — {_ago(item['mtime'])}")
    return "Sessões recentes:\n" + "\n".join(lines) + "\n\nUse /use <número> para continuar uma delas, ou /use new."


def _handle_use(arg: str, chat_id: int) -> None:
    global _last_listing
    arg = arg.strip().lower()
    if arg in {"new", "nova", "0"}:
        with _state_lock:
            _save_state({"id": None, "cwd": None, "title": None})
        send_telegram("Sessão limpa: as próximas mensagens iniciam uma conversa nova.", chat_id)
        return
    if not arg.isdigit() or not _last_listing or not 1 <= int(arg) <= len(_last_listing):
        send_telegram("Envie /sessions e depois /use <número> (ou /use new).", chat_id)
        return
    chosen = _last_listing[int(arg) - 1]
    with _state_lock:
        _save_state({"id": chosen["id"], "cwd": chosen["cwd"], "title": chosen["title"]})
    send_telegram(
        f"Sessão ativa: [{Path(chosen['cwd']).name}] {chosen['title']}\nMensagens sem / vão para ela.",
        chat_id,
    )


def _claude_command(prompt: str, state: dict) -> tuple[list[str], str | None]:
    port = os.getenv("TELEGRAM_NOTIFIER_PORT", "8765")
    host = os.getenv("TELEGRAM_NOTIFIER_HOST", "127.0.0.1")
    mcp_config = {
        "mcpServers": {
            "tgperm": {
                "command": sys.executable,
                "args": ["-m", "telegram_exec_notifier.permission_mcp"],
                "env": {
                    "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                    "TELEGRAM_NOTIFIER_URL": f"http://{host}:{port}",
                    "TELEGRAM_PERMISSION_TOKEN": PERMISSION_TOKEN,
                    "TELEGRAM_PERMISSION_TIMEOUT": str(PERMISSION_TIMEOUT),
                },
            }
        }
    }
    command = [
        "claude", "-p", prompt, "--add-dir", str(Path.home()),
        "--output-format", "stream-json", "--verbose",
        "--mcp-config", json.dumps(mcp_config),
        "--permission-prompt-tool", PERMISSION_TOOL,
    ]
    if state.get("id"):
        return command + ["--resume", state["id"]], state.get("cwd")
    auto = _auto_dir()
    return command + ["--append-system-prompt", SYSTEM_HINT], str(auto) if auto else None


def _run_cli(tool: str, prompt: str, chat_id: int) -> None:
    with _state_lock:
        state = _load_state()
    claude_command, claude_cwd = _claude_command(prompt, state)
    session_lock = _session_locks.setdefault(state.get("id") or "", threading.Lock())
    holds_lock = tool == "claude" and bool(state.get("id"))
    if holds_lock and not session_lock.acquire(blocking=False):
        send_telegram("⏳ A sessão ainda está respondendo à mensagem anterior. Aguarde.", chat_id)
        return
    released = threading.Event()

    def release() -> None:
        """Free the session once the first answer is out, even if background tasks linger."""
        if holds_lock and not released.is_set():
            released.set()
            session_lock.release()

    try:
        if tool == "claude":
            _stream_claude(claude_command, claude_cwd, chat_id, state, release)
        else:
            _execute_cli(tool, prompt, chat_id, claude_command, claude_cwd, state)
    finally:
        release()


def _reader(stream, events: queue.Queue) -> None:
    for line in stream:
        events.put(line)
    events.put(None)


def _stream_claude(
    command: list[str], cwd: str | None, chat_id: int, state: dict, release
) -> None:
    """Run `claude -p` and relay each assistant message as it appears, with heartbeats."""
    label = f"claude [{state['title']}]" if state.get("id") else "claude"
    started = time.monotonic()
    log.info("start %s cwd=%s", label, cwd)
    stderr_file = tempfile.TemporaryFile(mode="w+", errors="replace")
    try:
        proc = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=stderr_file, stdin=subprocess.DEVNULL,
            env=child_env(), text=True, cwd=cwd,
        )
    except Exception as exc:
        send_telegram(f"❌ falha ao iniciar {label}: {exc}", chat_id)
        log.error("spawn failed: %s", exc)
        return
    events: queue.Queue = queue.Queue()
    threading.Thread(target=_reader, args=(proc.stdout, events), daemon=True).start()
    last_text = ""
    last_tool = ""
    last_ping = started
    answered = False
    status = ""
    while True:
        now = time.monotonic()
        limit = BACKGROUND_TIMEOUT if answered else COMMAND_TIMEOUT
        if now - started > limit:
            proc.kill()
            status = f"⏱️ tempo limite ({limit}s)"
            break
        try:
            line = events.get(timeout=min(HEARTBEAT, 15))
        except queue.Empty:
            if not answered and time.monotonic() - last_ping >= HEARTBEAT:
                minutes = int((time.monotonic() - started) // 60)
                suffix = f" — {last_tool}" if last_tool else ""
                _safe_send(f"⏳ ainda trabalhando ({minutes} min){suffix}", chat_id)
                last_ping = time.monotonic()
            continue
        if line is None:
            break
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get("type")
        if kind == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    last_tool = f"executando {block.get('name', 'ferramenta')}"
                elif block.get("type") == "text" and block.get("text", "").strip():
                    last_text = block["text"].strip()
                    _safe_markdown(last_text, chat_id)
                    last_ping = time.monotonic()
        elif kind == "result":
            final = str(event.get("result") or "").strip()
            failed = bool(event.get("is_error"))
            if final and final != last_text:
                _safe_markdown(final, chat_id)
            minutes = (time.monotonic() - started) / 60
            _safe_send(f"{'❌ erro' if failed else '✅ concluído'} ({minutes:.1f} min)", chat_id)
            answered = True
            last_text = final or last_text
            release()
    try:
        code = proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        code = proc.wait()
    stderr_file.seek(0)
    err = stderr_file.read().strip()
    stderr_file.close()
    log.info("end %s code=%s secs=%.0f answered=%s", label, code, time.monotonic() - started, answered)
    if status:
        _safe_send(f"{status}\n{label}", chat_id)
    elif not answered:
        _safe_send(f"❌ {label} terminou sem resposta (código {code})\n{err[-MAX_OUTPUT:]}", chat_id)


def _safe_send(text: str, chat_id: int) -> None:
    try:
        send_telegram(text, chat_id)
    except Exception:
        log.warning("telegram send failed")


def _safe_markdown(text: str, chat_id: int) -> None:
    if len(text) > MAX_OUTPUT:
        text = text[:MAX_OUTPUT] + "\n… (saída truncada)"
    try:
        send_markdown(text, chat_id)
    except Exception:
        log.warning("telegram send failed")


def _execute_cli(
    tool: str, prompt: str, chat_id: int, claude_command: list[str], claude_cwd: str | None, state: dict
) -> None:
    commands = {
        "claude": claude_command,
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
            env=child_env(),
            stdin=subprocess.DEVNULL,
            text=True,
            timeout=COMMAND_TIMEOUT,
            cwd=claude_cwd if tool == "claude" else (Path.home() if tool == "kiro" else None),
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
    label = f"claude [{state['title']}]" if tool == "claude" and state.get("id") else tool
    try:
        send_markdown(f"**{label}** {status}\n\n{output}", chat_id)
    except Exception:
        # Telegram outages must not terminate the polling service.
        return


HELP_TEXT = (
    "Mensagens sem / vão para o Claude.\n"
    "/sessions — lista sessões recentes do Claude\n"
    "/use <n> — continua a sessão n; /use new (ou /new) começa do zero\n"
    "/codex <prompt> e /kiro <prompt> — outros agentes\n"
    "O Claude pede permissão aqui no Telegram (botões Permitir/Negar).\n"
    "O CLI roda neste computador."
)


def _poll_commands() -> None:
    allowed_chat = str(os.environ["TELEGRAM_CHAT_ID"])
    offset = 0
    while True:
        try:
            updates = _telegram("getUpdates", {"offset": offset, "timeout": 25}, timeout=35)
            for update in updates.get("result", []):
                offset = max(offset, update["update_id"] + 1)
                if "callback_query" in update:
                    _handle_callback(update["callback_query"], allowed_chat)
                    continue
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
                if text.startswith("/"):
                    command, _, prompt = text.partition(" ")
                    tool = command.split("@", 1)[0].lstrip("/").lower()
                    prompt = prompt.strip()
                else:
                    tool, prompt = "claude", text
                if tool in {"start", "help"}:
                    send_telegram(HELP_TEXT, chat["id"])
                elif tool == "sessions":
                    global _last_listing
                    _last_listing = _list_sessions()
                    with _state_lock:
                        active = _load_state().get("id")
                    send_telegram(_format_sessions(_last_listing, active), chat["id"])
                elif tool in {"use", "new"}:
                    _handle_use(prompt if tool == "use" else "new", chat["id"])
                elif tool in {"claude", "codex", "kiro"} and prompt:
                    send_telegram(f"⏳ Iniciando {tool}…", chat["id"])
                    threading.Thread(target=_run_cli, args=(tool, prompt, chat["id"]), daemon=True).start()
                else:
                    send_telegram("Comando inválido. Envie /help para ver as opções.", chat["id"])
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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _import_personal_skills_for_kiro()
    threading.Thread(target=_poll_commands, daemon=True).start()
    address = os.getenv("TELEGRAM_NOTIFIER_HOST", "127.0.0.1")
    port = int(os.getenv("TELEGRAM_NOTIFIER_PORT", "8765"))
    with ThreadingHTTPServer((address, port), Handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
