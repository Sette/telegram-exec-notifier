"""Convert the Markdown emitted by agent CLIs into Telegram-safe HTML."""

from __future__ import annotations

import html
import re

_FENCE = re.compile(r"^```[^\n]*\n(.*?)(?:^```[ \t]*$|\Z)", re.S | re.M)
_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*|__(?=\S)(.+?)(?<=\S)__")
_ITALIC = re.compile(r"(?<![\w*])\*(?=[^\s*])([^*\n]+?)(?<=[^\s*])\*(?![\w*])")
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
_HEADER = re.compile(r"^#{1,6}\s+(.*)$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+")
_RULE = re.compile(r"^\s*([-*_])\1{2,}\s*$")


def _inline(text: str) -> str:
    """Format one already-escaped line of Markdown."""
    spans: list[str] = []

    def stash(match: re.Match) -> str:
        spans.append(f"<code>{match.group(1)}</code>")
        return f"\0{len(spans) - 1}\0"

    text = _CODE.sub(stash, text)
    text = _LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    text = _BOLD.sub(lambda m: f"<b>{m.group(1) or m.group(2)}</b>", text)
    text = _ITALIC.sub(r"<i>\1</i>", text)
    return re.sub(r"\0(\d+)\0", lambda m: spans[int(m.group(1))], text)


def _prose(text: str) -> str:
    lines = html.escape(text, quote=False).split("\n")
    out: list[str] = []
    table: list[str] = []

    def flush_table() -> None:
        if table:
            out.append("<pre>" + "\n".join(table) + "</pre>")
            table.clear()

    for line in lines:
        if line.lstrip().startswith("|"):
            table.append(line)
            continue
        flush_table()
        if _RULE.match(line):
            continue
        header = _HEADER.match(line)
        if header:
            out.append(f"<b>{_inline(header.group(1))}</b>")
            continue
        out.append(_inline(_BULLET.sub(lambda m: f"{m.group(1)}• ", line)))
    flush_table()
    return "\n".join(out)


def markdown_to_telegram_html(text: str) -> str:
    """Return Telegram HTML for Markdown text; unclosed code fences are closed."""
    parts: list[str] = []
    position = 0
    for match in _FENCE.finditer(text):
        parts.append(_prose(text[position : match.start()]))
        code = html.escape(match.group(1).rstrip("\n"), quote=False)
        parts.append(f"<pre>{code}</pre>")
        position = match.end()
    parts.append(_prose(text[position:]))
    return "".join(parts)
