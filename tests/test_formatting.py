"""Tests for the Markdown to Telegram HTML converter."""

from telegram_exec_notifier.formatting import markdown_to_telegram_html as convert


def test_inline_styles():
    assert convert("**bold** and *it* and `code`") == "<b>bold</b> and <i>it</i> and <code>code</code>"


def test_escapes_html_in_prose_and_code():
    assert convert("a < b & c") == "a &lt; b &amp; c"
    assert convert("```\nx = 1 < 2\n```") == "<pre>x = 1 &lt; 2</pre>"


def test_unclosed_fence_is_closed():
    assert convert("```bash\nls") == "<pre>ls</pre>"


def test_headers_bullets_rules_and_links():
    text = "## Title\n- item\n---\n[docs](https://x.io/a?b=1&c=2)"
    assert convert(text) == '<b>Title</b>\n• item\n<a href="https://x.io/a?b=1&amp;c=2">docs</a>'


def test_tables_become_preformatted_blocks():
    assert convert("| a | b |\n|---|---|\n| 1 | 2 |") == "<pre>| a | b |\n|---|---|\n| 1 | 2 |</pre>"


def test_identifiers_with_underscores_and_stars_are_untouched():
    assert convert("snake_case_name and 2*3*4") == "snake_case_name and 2*3*4"
