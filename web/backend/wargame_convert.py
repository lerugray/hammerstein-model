"""PDF → markdown conversion for uploaded wargame rulebooks.

Used by the wargamer-mode "Sources" section: a wargamer drops a
rulebook PDF, the file is converted to a structured markdown the
multimodal model can consume, and the result is persisted under
`<state-dir>/rules/<basename>.md` so every subsequent issue call
includes the rules in the AI's preamble.

Pipeline:
  1. pymupdf4llm.to_markdown(path) — fast, text-layer extraction
  2. strip pandoc-style "==> picture [WxH] intentionally omitted <=="
     noise lines (artifact of how pymupdf renders image regions)
  3. promote "----- Start of picture text -----<br>SECTION TITLE
     <br>----- End of picture text -----" blocks to proper markdown
     headings (mapping X.0 → ##, X.Y → ###, X.Y.Z → ####)
  4. strip repeating page-header / page-footer junk (page numbers,
     publisher banner lines)

Cleanup rules ported from
[`conflict-simulations/manuals/build-docx.py`](https://github.com/lerugray/conflict-simulations/blob/main/manuals/build-docx.py),
which was Ray's hand-tuned pipeline for shipping CSL rulebooks
into translation-friendly DOCX. Same artifacts, same fixes.
"""

from __future__ import annotations

import re
from pathlib import Path

# pymupdf4llm is imported lazily inside `pdf_to_md` so the rest of
# the wargame API can import this module without paying the import
# cost at server startup (or failing if the package is missing in
# environments that don't need PDF support).

NOISE_LINE_RE = re.compile(r"^\*\*==> picture \[[^\]]+\] intentionally omitted <==\*\*\s*$")

PICTURE_BLOCK_RE = re.compile(
    r"\*\*----- Start of picture text -----\*\*<br>\s*\n"
    r"([^\n]+?)<br>\*\*----- End of picture text -----\*\*<br>\s*\n",
    re.MULTILINE,
)

SECTION_ID_RE = re.compile(r"^(\d+(?:\.\d+){0,3})\b")

# Page-furniture lines: "Page N", standalone bare numbers, repeating
# publisher / title banners. Stripped because they fragment the
# markdown structure without adding rules content.
PAGE_NUM_RE = re.compile(r"^Page \d+\s*$|^\d{1,3}\s*$")


def heading_level_for(section_id: str) -> int:
    """Map e.g. '1.0' -> 2, '6.1' -> 3, '6.1.2' -> 4."""
    parts = section_id.split(".")
    if len(parts) == 2 and parts[1] == "0":
        return 2
    if len(parts) == 2:
        return 3
    if len(parts) == 3:
        return 4
    return 3


def _promote_picture_text_block(match: re.Match[str]) -> str:
    inner = match.group(1).strip()
    sec = SECTION_ID_RE.match(inner)
    if sec:
        level = heading_level_for(sec.group(1))
        return "#" * level + " " + inner + "\n\n"
    return "**" + inner + "**\n\n"


def _detect_repeating_banners(md: str, min_repeats: int = 4) -> set[str]:
    """Find lines that appear repeatedly across pages — usually publisher
    name + game title + similar furniture. Anything appearing >=N times
    that's short enough to be a banner is stripped."""
    counts: dict[str, int] = {}
    for line in md.splitlines():
        s = line.strip()
        if not s or len(s) > 60:
            continue
        if s.startswith("#") or s.startswith("**==>") or s.startswith("- "):
            continue
        counts[s] = counts.get(s, 0) + 1
    return {s for s, n in counts.items() if n >= min_repeats}


def cleanup_md(md: str) -> str:
    """Apply the strip + promote pipeline to raw pymupdf4llm output."""
    # 1. Promote picture-text blocks to proper headings FIRST. The block
    #    boundary lines ("Start of picture text" etc.) are repeating
    #    banners; promoting first prevents the banner stripper below
    #    from eating them.
    md = PICTURE_BLOCK_RE.sub(_promote_picture_text_block, md)

    # 2. Line-level filter: drop noise + page numbers + repeating banners.
    banners = _detect_repeating_banners(md)
    out_lines: list[str] = []
    for line in md.splitlines():
        if NOISE_LINE_RE.match(line):
            continue
        if PAGE_NUM_RE.match(line.strip()):
            continue
        if line.strip() in banners:
            continue
        out_lines.append(line)
    cleaned = "\n".join(out_lines)
    # Collapse runs of >2 blank lines to exactly 2 (preserves paragraph
    # breaks while removing the gaps left by stripped lines).
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() + "\n"


def pdf_to_md(pdf_path: Path) -> str:
    """Convert a PDF to cleaned markdown. Raises on conversion failure."""
    import pymupdf4llm  # local import — see module docstring
    raw = pymupdf4llm.to_markdown(str(pdf_path), show_progress=False)
    return cleanup_md(raw)
