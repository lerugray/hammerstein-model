"""Round-trip tests for wargame_parse.parse_orders.

These don't hit the API — they verify the markdown→OrdersData mapping
against a representative sample.
"""

from web.backend.wargame_parse import parse_orders, DEFAULT_UNREAD


SAMPLE_FULL = """
## What I see on the board

- Two Red infantry stacks at the bridgehead — hex 0608 (strength 2, fatigued) and 0609 (strength 3).
- Red armor concentration forming at hex 0710; counter visible bears 71st Mech, full strength.
- Blue 2nd Bn in the cornfield at 0509, strength 2.
- 3rd Co. on the ridge at 0410, strength 3, intact.

## Unread

I cannot read the smoke marker east of 0509 — confirm whether it is on 0608 or 0609 before committing fires.

## Situation

Red holds the bridge but paid for it. Red 1st Bn at 0608 is reduced to strength 2.

## Intent

Bleed Red across the river while we shape the ground east of the bridge.

Decision turn is 5.

## Main Effort

2nd Bn at 0509. Hold the cornfield line.

## Supporting Effort

Bttry A. HE harassment on the bridge approach.

## Reserves & Fallback

3rd Co. holds the ridge. Do not withdraw.

## Acknowledged

— Acknowledged. Awaiting turn 4 board state.
""".strip()


def test_parse_full_response():
    out = parse_orders(SAMPLE_FULL)
    assert len(out["see_board"]) == 4
    assert "0608" in out["see_board"][0]
    assert "smoke marker" in out["unread"]
    assert len(out["sections"]) == 5
    assert [s["title"] for s in out["sections"]] == [
        "Situation", "Intent", "Main Effort", "Supporting Effort", "Reserves & Fallback"
    ]
    assert [s["n"] for s in out["sections"]] == ["01", "02", "03", "04", "05"]
    assert len(out["sections"][1]["body"]) == 2  # Intent has two paragraphs
    assert "turn 4" in out["ack"]


def test_parse_missing_sections_uses_defaults():
    minimal = "## Situation\nRed advances.\n\n## Intent\nHold."
    out = parse_orders(minimal)
    assert out["see_board"] == []
    assert out["unread"] == DEFAULT_UNREAD
    assert len(out["sections"]) == 2
    assert out["ack"] == "— Acknowledged."


def test_parse_handles_lower_case_headers():
    md = "## what i see on the board\n- one\n- two\n\n## unread\nfoo"
    out = parse_orders(md)
    assert out["see_board"] == ["one", "two"]
    assert out["unread"] == "foo"


def test_parse_preserves_inline_markup():
    md = "## Main Effort\n2nd Bn at <span class='hex'>0509</span>. Hold."
    out = parse_orders(md)
    body = out["sections"][0]["body"][0]
    assert "<span class='hex'>0509</span>" in body


def test_parse_recovers_ack_when_header_missing():
    """The model often emits the closing — Acknowledged line without
    a `## Acknowledged` header. Parser should pull it back out of the
    last section's body."""
    md = (
        "## Reserves & Fallback\n\n"
        "No reserves. Commit everything.\n\n"
        "— Acknowledged. Awaiting Turn 5 board state."
    )
    out = parse_orders(md)
    assert "Awaiting Turn 5" in out["ack"]
    last_body = out["sections"][-1]["body"]
    assert all("Acknowledged" not in p for p in last_body), \
        f"ack line still in last section body: {last_body}"


if __name__ == "__main__":
    test_parse_full_response()
    test_parse_missing_sections_uses_defaults()
    test_parse_handles_lower_case_headers()
    test_parse_preserves_inline_markup()
    test_parse_recovers_ack_when_header_missing()
    print("all parser tests pass")
