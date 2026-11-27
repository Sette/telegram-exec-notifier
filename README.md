# Telegram Execution Notifier

[![CI](https://github.com/Sette/telegram-exec-notifier/actions/workflows/ci.yml/badge.svg)](https://github.com/Sette/telegram-exec-notifier/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/telegram-exec-notifier)](https://pypi.org/project/telegram-exec-notifier/)

Run command-line AI agents from Telegram and get their results back on your phone. Telegram Execution Notifier connects a Telegram bot to Claude Code, Codex CLI, and Kiro CLI running on your computer, so you can delegate coding, troubleshooting, documentation, and other tasks without staying at your terminal.

Send a prompt to your bot and choose which agent should handle it. The request is forwarded to the selected CLI on your computer, and the bot sends the final output to your authorized Telegram chat. This is especially useful when your agents can access local project files and skills: you can trigger workflows remotely and let an agent use the context and capabilities already configured in your CLI environment.

The project also provides a `notify-telegram` command for shell scripts, pipelines, and other tools to report when work finishes or fails. A small `systemd --user` service keeps the Telegram integration running in the background. Built-in prompt routing supports Claude Code, Codex CLI, and Kiro CLI; the notification command can also be used by other command-line tools, including AI CLIs that support skills.

## Features

- Send prompts from Telegram to Claude Code, Codex CLI, or Kiro CLI on your computer.
- Receive an acknowledgment when a task starts and the agent's final output when it finishes.
- Run agents with access to local files and configured skills, making remote task delegation practical.
- Send success or failure notifications from the shell, scripts, pipelines, or Python code.
- Process messages only from the configured Telegram chat.
- Keep the integration running as a `systemd --user` service, with its local endpoint bound to `127.0.0.1`.

## 1. Create and configure the Telegram bot

1. In Telegram, message [@BotFather](https://t.me/BotFather), run `/newbot`, and save the token it gives you.
2. Open your new bot and send it `/start`.
3. Find your numeric chat ID and configure it as the authorized recipient. Only messages from this chat are processed.
4. Create the plain file `~/.config/telegram-exec-notifier/environment` with the variables below ([`.env.example`](.env.example) lists every supported one). You encrypt it in step 3, so it does not stay on disk in plain text:

```sh
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
```

## 2. Install

From this project directory:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

### Install from PyPI

```sh
pip install telegram-exec-notifier
```

This provides the `notify-telegram` command and `telegram-exec-notifier` (the bot service). The systemd unit and the scripts below are in this repository.

## 3. Start the user service

Encrypt the environment file, then start the service. Both commands run from the project directory:

```sh
./encrypt-credentials.sh
./start-service.sh
```

`encrypt-credentials.sh` uses `systemd-creds` (user scope, host key plus TPM2) to write `environment.cred`, checks that it decrypts to the same content, and then securely deletes the plain file. The service loads the credential with `LoadCredentialEncrypted=`, so the token is no longer stored in plain text on disk and is decrypted only on this computer. It needs a TPM2 (`systemd-analyze has-tpm2`) and systemd 256 or newer. To change a value, recreate the plain file and run `./encrypt-credentials.sh` again, then restart the service.

The script installs the user service unit (filling in this project's path), sets the environment file permissions to `600`, enables the service at startup, and restarts it.

The service expects to find `claude`, `codex`, and `kiro-cli` in `$HOME/.local/bin` or `/usr/local/bin`. Adjust `PATH` in the service unit if your CLI binaries are elsewhere. Claude and Codex receive the home directory as an additional working directory; Kiro runs with the home directory as its workspace and has read and write tools enabled. This lets the agents work with files across your home directory while the service unit keeps the rest of the system protected from writes. On startup, the service also copies personal skills from `~/.codex/skills` and `~/.claude/skills` to `~/.kiro/skills`, preserving any skills already present in Kiro.

## Send prompts from Telegram

Send a direct message to the bot from the authorized chat. Messages without a leading `/` go to Claude Code. Prefix with `/codex` or `/kiro` to use another agent:

```text
explique o estado deste projeto
/codex encontre e corrija o bug no parser
/kiro revise a documentação
```

### Continue an existing Claude session

By default each message starts a new Claude conversation that knows where other session transcripts live (`~/.claude/projects`). To continue a real session, for example the one running your experiment:

```text
/sessions       list the 10 most recent interactive sessions
/use 2          make session 2 active; later messages resume it with full context
/use new        go back to a fresh conversation (also: /new)
```

The active session is saved in `~/.config/telegram-exec-notifier/state.json` and survives service restarts. Sessions started by the bot itself are not listed. If the same session is open in a terminal, the bot's replies continue it separately from what you type there.

Claude replies are streamed: each message arrives as soon as it is written, a "still working" note appears every `TELEGRAM_HEARTBEAT` seconds while it runs, and a final message reports completion and elapsed time. Your next message is accepted as soon as the final answer is out, even if background tasks are still running.

The bot confirms when the task starts and sends the final output when it finishes. Each run has a time limit (30 minutes by default), and long responses are truncated to fit Telegram. Send `/help` to see the available commands. Messages from other chats are ignored.

### Approve Claude permissions from Telegram

When Claude wants to run a command or edit a file that needs permission, the bot sends a message with the tool and its command or path, plus **Permitir** / **Negar** buttons. Claude continues or adapts according to your answer. If you do not answer within `TELEGRAM_PERMISSION_TIMEOUT` seconds (default 300), the request is denied. Only the authorized chat can answer. `/codex` and `/kiro` do not use this flow.

Optional settings in `~/.config/telegram-exec-notifier/environment`:

```sh
# Claude runs without asking when its working directory is inside this folder.
# New conversations also start in this folder. Everything else still asks.
TELEGRAM_CLAUDE_AUTO_DIR=/home/you/sandbox
TELEGRAM_PERMISSION_TIMEOUT=300   # seconds to wait for a Telegram answer
TELEGRAM_COMMAND_TIMEOUT=1800     # seconds before a run is stopped
TELEGRAM_HEARTBEAT=120            # seconds between "still working" messages
TELEGRAM_BACKGROUND_TIMEOUT=86400 # seconds a run may continue after its final answer
```

The folder check uses the session's working directory, so a shell command inside that folder can still reach outside it (for example `cd ..`). Use a dedicated folder.

## Run with Docker

As an alternative to systemd, run the bot as a container. The image only contains the service; the agent CLIs (`claude`, `codex`, `kiro-cli`) stay on your computer, so the compose file mounts your home directory at the same path and runs as your user.

```sh
cp .env.example .env          # set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
HOST_UID=$(id -u) HOST_GID=$(id -g) docker compose up -d
```

The image is published at `ghcr.io/sette/telegram-exec-notifier`. The port is published on `127.0.0.1` only; do not expose it to the network. Credentials come from `.env` through the environment, so the systemd encrypted-credential flow does not apply; the bot token is still hidden from the agents it starts. The CLI binaries must run inside the image (a glibc Linux image); if yours do not, build a custom image from this one.

## 4. Send a notification

```sh
notify-telegram "Codex finished running."
notify-telegram --tool Codex "Training completed successfully."
notify-telegram --tool Claude --failed "The run failed."
some-command 2>&1 | notify-telegram --tool Codex
```

## Call from Python

```python
import asyncio
from telegram_exec_notifier import TelegramNotifier

asyncio.run(
    TelegramNotifier().execution_finished("Codex", "Training completed")
)
```

The same call works in an existing async function with `await`.

## Development and releases

```sh
uv run --group dev ruff check .
uv run --group dev pytest
```

CI runs lint, tests on Python 3.10 to 3.13, a package build check and a Docker build on every pull request. Commits follow `type(scope): emoji description`. [release-please](https://github.com/googleapis/release-please) reads them on `main` and keeps a release pull request up to date; merging it creates the tag and the GitHub release, which publishes the package to PyPI and the image to GHCR.

One-time repository setup:

1. Add the `RELEASE_PLEASE_TOKEN` secret (a personal access token with contents and pull request write access) so the release it creates can trigger the publish workflows.
2. On PyPI, add a [trusted publisher](https://docs.pypi.org/trusted-publishers/) for `telegram-exec-notifier`: owner `Sette`, repository `telegram-exec-notifier`, workflow `python-publish.yml`, environment `pypi`. Create the `pypi` environment in the repository settings.
3. Do not edit `.release-please-manifest.json`, the version in `pyproject.toml` or the changelog by hand; the release PR does it.

## Security notes

- The service processes commands only from the configured Telegram chat ID.
- Its local endpoint listens on `127.0.0.1`; do not expose the port to the network.
- The bot token is stored encrypted (`environment.cred`), and the agent CLIs started by the bot do not inherit it in their environment.
- While the service runs, systemd keeps the decrypted credential in `/run/user/<uid>/credentials/`, readable by your user. An agent running as your user that knows this path could still read it, so encryption protects the token at rest (disk theft, backups, other users), not from a process running as you. Revoke the token with BotFather `/revoke` if you suspect a leak.
- Never commit your bot token.
