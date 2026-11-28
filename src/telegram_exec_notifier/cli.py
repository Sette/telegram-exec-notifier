"""Command line entry point for sending notifications."""

from __future__ import annotations

import argparse
import asyncio
import sys

from .notifier import TelegramNotifier


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a message to your Telegram chat")
    parser.add_argument("message", nargs="?", help="Message text; reads stdin if omitted")
    parser.add_argument("--tool", help="Label the message as an execution result")
    parser.add_argument("--failed", action="store_true", help="Mark execution as failed")
    args = parser.parse_args()
    message = args.message if args.message is not None else sys.stdin.read().strip()
    if not message:
        parser.error("provide a message or pipe text through stdin")

    notifier = TelegramNotifier()
    if args.tool:
        asyncio.run(
            notifier.execution_finished(args.tool, message, success=not args.failed)
        )
    else:
        asyncio.run(notifier.send(message))


if __name__ == "__main__":
    main()
