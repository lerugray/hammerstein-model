"""Parse hp_vision.py kriegspiel orders (markdown) into the OrdersData
shape the React WargamePage expects.

Input shape (the 8-section markdown the WARGAME_ROLE_SUFFIX in
hp_vision.py enforces):

    ## What I see on the board
    - bullet 1
    - bullet 2

    ## Unread
    I cannot read X — confirm Y before doing Z.

    ## Situation
    ...

    ## Intent
    ...

    ## Main Effort
    ...

    ## Supporting Effort
    ...

    ## Reserves & Fallback
    ...

    ## Acknowledged
    — Acknowledged. Awaiting turn N+1 board state.

Output shape (matches OrdersData in web/frontend/src/wargame/content.ts):

    {
      "see_board": ["bullet 1", "bullet 2"],
      "unread": "I cannot read X — confirm Y before doing Z.",
      "sections": [
        {"n": "01", "title": "Situation", "body": ["..."]},
        ...
      ],
      "ack": "— Acknowledged. Awaiting turn N+1 board state."
    }

Tolerant of: missing sections (returns empty defaults), trailing
whitespace, mixed line endings, header capitalization differences.
Section bodies are split into paragraph strings (blank-line
separated).
"""

from __future__ import annotations

import re
from typing import Any

ORDER_SECTIONS: list[tuple[str, str]] = [
    ("situation", "Situation"),
    ("intent", "Intent"),
    ("main effort", "Main Effort"),
    ("supporting effort", "Supporting Effort"),
    ("reserves & fallback", "Reserves & Fallback"),
]

DEFAULT_UNREAD = "All clear — board fully readable."


def _split_sections(md: str) -> dict[str, str]:
    """Split markdown by `## ` headers. Returns {lowercased-header: body}."""
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []
    for raw in md.splitlines():
        line = raw.rstrip()
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = m.group(1).strip().lower()
            current_lines = []
        elif current_key is not None:
            current_lines.append(line)
    if current_key is not None:
        sections[current_key] = "\n".join(current_lines).strip()
    return sections


def _parse_bullets(body: str) -> list[str]:
    """Pull bullet items out of a markdown body. Tolerant: also accepts
    plain newline-separated lines if no bullets are present."""
    bullets: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^[-*+]\s+(.+)$", line)
        if m:
            bullets.append(m.group(1).strip())
        elif not bullets:
            bullets.append(line)
        else:
            bullets[-1] = bullets[-1] + " " + line
    return bullets


def _parse_paragraphs(body: str) -> list[str]:
    """Split a markdown body into paragraphs by blank lines.
    Single-paragraph bodies return [body]."""
    paragraphs = re.split(r"\n\s*\n", body.strip())
    return [p.strip().replace("\n", " ") for p in paragraphs if p.strip()]


def parse_orders(md: str) -> dict[str, Any]:
    """Parse a hp_vision.py kriegspiel orders response into OrdersData."""
    sections = _split_sections(md)

    see_board_body = sections.get("what i see on the board", "")
    see_board = _parse_bullets(see_board_body) if see_board_body else []

    unread = sections.get("unread", "").strip() or DEFAULT_UNREAD
    unread = re.sub(r"\s+", " ", unread)

    order_sections = []
    for i, (key, title) in enumerate(ORDER_SECTIONS, start=1):
        body = sections.get(key, "").strip()
        if not body:
            continue
        paragraphs = _parse_paragraphs(body)
        order_sections.append({
            "n": f"{i:02d}",
            "title": title,
            "body": paragraphs,
        })

    ack = sections.get("acknowledged", "").strip()
    if ack:
        ack = re.sub(r"\s+", " ", ack)
    else:
        # Tolerate the model omitting the `## Acknowledged` header but
        # still emitting the closing line as the final paragraph of the
        # last section. Pull it back out so the UI's ack slot renders.
        if order_sections:
            last_body = order_sections[-1]["body"]
            if last_body:
                tail = last_body[-1]
                m = re.search(
                    r"(?:^|\n|\s)(—\s*Acknowledged[^\n]*?)\s*$",
                    tail,
                )
                if m:
                    ack_line = m.group(1).strip()
                    remainder = tail[: m.start()].rstrip(" \n—")
                    if remainder:
                        last_body[-1] = remainder
                    else:
                        last_body.pop()
                    ack = ack_line
        if not ack:
            ack = "— Acknowledged."

    return {
        "see_board": see_board,
        "unread": unread,
        "sections": order_sections,
        "ack": ack,
    }
