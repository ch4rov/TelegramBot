from __future__ import annotations

import html


def wrap_tail_in_blockquote(caption_html: str, min_tail_chars: int = 200) -> str:
    """Wrap everything after the first paragraph into an expandable blockquote.

    Keeps the first paragraph (usually title/link) clean, and hides long tails.
    If caption already contains a blockquote, it's returned unchanged.
    """
    if not caption_html:
        return caption_html

    s = str(caption_html)
    if "<blockquote" in s:
        return s

    # Split by double newline (paragraph boundary).
    parts = s.split("\n\n", 1)
    if len(parts) < 2:
        return s

    head, tail = parts[0].strip(), parts[1].strip()
    if len(tail) < int(min_tail_chars):
        return s

    # Best-effort: ensure tail is valid HTML fragment (don't escape links etc; assume caller already escapes).
    return f"{head}\n\n<blockquote expandable>{tail}</blockquote>"


def quote_text(text: str, max_chars: int = 1200) -> str:
    """Escape and wrap plain text in an expandable blockquote for Telegram HTML."""
    t = (text or "")
    if len(t) > max_chars:
        t = t[: max(0, max_chars - 1)] + "…"
    return f"<blockquote expandable>{html.escape(t)}</blockquote>"
