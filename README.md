# Telegram Execution Notifier

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
4. Set the variables in `~/.config/telegram-exec-notifier/environment`. Keep this file private and do not commit it:

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

## 3. Start the user service

Create the environment file above, then run this command from the project directory:

```sh
./start-service.sh
```

The script installs the user service unit, sets the environment file permissions to `600`, enables the service at startup, and restarts it.

The service expects to find `claude`, `codex`, and `kiro-cli` in `/home/brunos/.local/bin` or `/usr/local/bin`. Adjust `PATH` in the service unit if your CLI binaries are elsewhere. Claude and Codex receive the home directory as an additional working directory; Kiro runs with the home directory as its workspace and has read and write tools enabled. This lets the agents work with files across your home directory while the service unit keeps the rest of the system protected from writes. On startup, the service also copies personal skills from `~/.codex/skills` and `~/.claude/skills` to `~/.kiro/skills`, preserving any skills already present in Kiro.

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
```

The folder check uses the session's working directory, so a shell command inside that folder can still reach outside it (for example `cd ..`). Use a dedicated folder.

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

## Security notes

- The service processes commands only from the configured Telegram chat ID.
- Its local endpoint listens on `127.0.0.1`; do not expose the port to the network.
- Keep the environment file private with mode `600`, and never commit your bot token.
