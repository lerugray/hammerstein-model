# Turn log — Bridge Crossing

Append-only per-turn snapshots. Newest turn at the top so the
wrapper's recency-decay surfaces it first.

---

## Turn 3 — 2026-05-08 dogfood run

**Red orders (from AI):** 2nd Bn D5→D4 to fix D2/C3; 3rd Bn F4→E4
through forest, swing E3 to assault E2; no reserves; fallback to
D4/E4 if push fails.

**Player adjudication:** 2nd Bn ends at D4 (movement only, no
attack — one action per unit). 3rd Bn ends at E4 (E3 is river,
can't enter). Blue Recon Co + Bty A take ranged shots, each
scoring 1 hit (rolls of 6 and 5 respectively).

**End Turn 3:** 2nd Bn at D4 str 2, 3rd Bn at E4 str 2, no
engineer. Red infantry weakening. Two turns left. Bridge crossing
attempt incoming.

**Format compliance:** Clean. 5 sections, no preamble/suffix,
imperative voice, used our hex grid. Working query pattern
(see MISSION.md "Calling the wrapper") held.

---

## Turn 2 — 2026-05-08 dogfood run

**Red orders (from AI):**
- Eng Co: D4 → D3 (bridge). Secure, clear obstacles.
- 3rd Bn: E4 → E3 (suppressive fire on E2 / D2; screen east).
- 2nd Bn: Hold D5; shift direct fire to C3 and D2; overwatch for Eng Co.

**Player adjudication:**
- Eng Co D4 → D3 (bridge): ✓ valid. Triggers Blue Recon Co overwatch fire.
- 3rd Bn E4 → E3: invalid (E3 is river). Rules-shimmed: 3rd Bn moves E4 → F4 (forest, +1 def) for flanking position. Now at F4.
- 2nd Bn at D5 holds: ✓. Note that "hold + direct fire" exceeds one-action-per-turn; player interprets as Hold only (no shooting).

**Blue orders (player):**
- 1st Bn: Hold at D2 (+1 def).
- Recon Co: Overwatch fire at Eng Co crossing D3.
- Bty A: Ranged fire at 3rd Bn (now at F4 forest).

**Combat:**
- Recon Co (str 2) overwatch fire on Eng Co at D3: 2 dice, hits 5-6, no terrain mod (Eng on open bridge). Rolls 5, 2 → 1 hit. Eng Co str 1 → 0. **Eng Co ELIMINATED.**
- Bty A (str 2) fire on 3rd Bn at F4 (forest). Defender in forest hits on 4-6 in melee but ranged: simplify to standard 5-6. 2 dice. Rolls 3, 5 → 1 hit. 3rd Bn str 4 → 3.

**End of Turn 2 state:**

| Side | Unit     | Strength | Hex | Notes |
|------|----------|---------:|-----|-------|
| Red  | 2nd Bn   | 3        | D5  | Held in place |
| Red  | 3rd Bn   | 3 (-1)   | F4  | In forest (+1 def). Took 1 art hit |
| Red  | Eng Co   | 0        | —   | **ELIMINATED on bridge** |
| Blue | 1st Bn   | 4        | D2  | In village (+1 def) |
| Blue | Recon Co | 2        | C3  | Overwatch held |
| Blue | Bty A    | 2        | E2  | Range 3 |

**Significant change:** Red has lost the only Engineer unit. **No
pontoon option remains.** Red must force the bridge with infantry
only (taking village/forest defender penalties), retreat, or
accept defeat by Turn 5. This is the kind of decision point that
distinguishes AI command quality.

---

## Turn 1 — 2026-05-08 dogfood run

**Red orders (from AI):**
- Eng Co: Advance D5 to D4. Breach river obstacle at D3. Clear bridge approaches.
- 2nd Bn: Advance C5 to D5. Cross D3 immediately following Eng Co.
- 3rd Bn: Advance E5 to E4. Push to E3. Suppress E2 artillery. Fix C3 Recon with direct fire.

**Player adjudication:**
- Eng Co moves D5 → D4 (✓ valid, 1 hex move, no contact). Now at D4.
- 2nd Bn ordered C5 → D5 → "cross D3" but D3 is bridge and Eng Co is at D4 (not bridge), and you can't cross in one turn while breaching. Rules-shimmed: 2nd Bn moves C5 → D5 (1 hex; respects stacking since Eng Co left D5). Now at D5.
- 3rd Bn ordered E5 → E4 → E3 → fire on E2/C3. E3 is river (impassable for infantry). Rules-shimmed: 3rd Bn moves E5 → E4. Now at E4. No fire (out of range / across river without bridge).

**Blue orders (player):**
- 1st Bn: Hold at D2 (defensive prep, +1 def).
- Recon Co: Hold at C3 (overwatch, +1 def).
- Bty A: Ranged fire at 2nd Bn at D5 (distance 3, in range).

**Combat:**
- Bty A fire at 2nd Bn (D5): 2 dice, hits on 5-6, no terrain mod (open ground). Rolls: 4, 6. One hit. 2nd Bn loses 1 strength.

**End of Turn 1 state:**

| Side | Unit     | Strength | Hex | Notes |
|------|----------|---------:|-----|-------|
| Red  | 2nd Bn   | 3 (-1)   | D5  | Bracketed by Bty A; in open ground |
| Red  | 3rd Bn   | 4        | E4  | Adjacent to F4 forest (could move there for cover) |
| Red  | Eng Co   | 1        | D4  | At bridge approach; can begin pontoon Turn 2 |
| Blue | 1st Bn   | 4        | D2  | In village (+1 def) |
| Blue | Recon Co | 2        | C3  | River hex, overwatching D3 |
| Blue | Bty A    | 2        | E2  | Range 3 |

Bridge D3 still uncontested but in artillery range.

---

## Setup (pre-Turn 1)

Initial deployment per `tasks.json`. Red on row 5, Blue holding the
village + bridge area. Weather: clear. Time: 0600 local. River is
fordable only via the bridge at D3.
