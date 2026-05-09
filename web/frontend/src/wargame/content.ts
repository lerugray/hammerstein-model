// Bridge Crossing — Steinbach turn-3 placeholder content.
// Operator plays Blue (German). Red (Russian) just took the bridge in T2.
// Mirrors the Claude Design fixture so the implemented page reads like
// the prototype.

export interface Photo {
  label: string;
  kb: number;
}

export interface Sheet {
  name: string;
  sheetName: string;
  rows: number;
  cols: string[];
}

export interface CampaignInfo {
  name: string;
  turn: number;
  started: string;
  spend: number;
  spendBudget: number;
  cost_breakdown: { input_tokens: number; output_tokens: number; model: string };
}

export interface TurnLogEntry {
  turn: number;
  time: string;
  model: string;
  status: string;
  intent: string;
  current?: boolean;
}

export interface OrderSection {
  n: string;
  title: string;
  body: string[];
}

export interface OrdersData {
  see_board: string[];
  unread: string;
  sections: OrderSection[];
  ack: string;
}

export const PHOTOS_DRAFT: Photo[] = [
  { label: "turn3-board.jpg", kb: 2340 },
  { label: "oob-detail.jpg", kb: 1180 },
];

export const SHEET_DRAFT: Sheet = {
  name: "oob.xlsx",
  sheetName: "Steinbach OOB",
  rows: 28,
  cols: ["unit", "side", "hex", "strength", "fatigue"],
};

export const STATUS_DRAFT =
  "Just played turn 3. Russians took the bridge but lost a regiment to my artillery. I'm thinking of withdrawing my left flank to consolidate.";

export const CAMPAIGN: CampaignInfo = {
  name: "Bridge Crossing — Steinbach",
  turn: 3,
  started: "2026-04-22",
  spend: 0.18,
  spendBudget: 1.20,
  cost_breakdown: { input_tokens: 4180, output_tokens: 612, model: "anthropic/claude-sonnet-4.6" },
};

export const TURN_LOG: TurnLogEntry[] = [
  {
    turn: 3,
    time: "May 8 · 21:14",
    model: "claude-sonnet-4.6",
    status:
      "Just played turn 3. Russians took the bridge but lost a regiment to my artillery. I'm thinking of withdrawing my left flank to consolidate.",
    intent:
      "Bleed Red across the river while we shape the ground east of the bridge. Decision turn is 5.",
    current: true,
  },
  {
    turn: 2,
    time: "May 7 · 22:51",
    model: "claude-sonnet-4.6",
    status:
      "Engineers lost on the bridge. Red 1st Bn forced the crossing under smoke; I fell back to the cornfield line at 0509 with Bttry A registered.",
    intent:
      "Yield the bridgehead. Preserve combat power for a counter-attack on turn 4 or 5; do not feed reinforcements piecemeal.",
  },
  {
    turn: 1,
    time: "May 7 · 19:08",
    model: "claude-sonnet-4.6",
    status:
      "Engineers crossed the river under smoke and took the bridge intact at H+15. Red 1st Bn dug in north of the bridge in good order.",
    intent:
      "Seize the Steinbach bridge intact and hold the south bank for four turns until 3rd Co. closes from the ridge.",
  },
];

export const ORDERS_T3: OrdersData = {
  see_board: [
    "Two Red infantry stacks at the bridgehead — hex 0608 (strength 2, fatigued) and hex 0609 (strength 3).",
    "Red armor concentration forming at hex 0710; counter visible bears 71st Mech, full strength.",
    "Blue 2nd Bn in the cornfield at 0509, strength 2.",
    "3rd Co. on the ridge at 0410, strength 3, intact.",
    "Bttry A south of the wood line at 0309. Two ammo markers remaining.",
    "Bridge intact. River impassable except at the bridge.",
  ],
  unread:
    "I cannot read the smoke marker east of 0509 — confirm whether it is on 0608 or 0609 before committing fires.",
  sections: [
    {
      n: "01",
      title: "Situation",
      body: [
        "Red holds the bridge but paid for it. <strong>Red 1st Bn at <span class='hex'>0608</span></strong> is reduced to strength 2 — Bttry A counter-fire on the crossing cost them a step. <strong>Red 2nd Bn massing at <span class='hex'>0710</span></strong> is at full strength and will close the bridgehead by turn 5.",
        "Our line: 2nd Bn at <span class='hex'>0509</span>, strength 2. 3rd Co. (left flank) at <span class='hex'>0410</span>, strength 3, intact. Bttry A at <span class='hex'>0309</span>, ammunition 60%. Weather clear; the river is uncrossable except at the bridge.",
        "<em>We have lost the bridgehead. We have not lost the engagement.</em>",
      ],
    },
    {
      n: "02",
      title: "Intent",
      body: [
        "Bleed Red across the river while we shape the ground east of the bridge. We will not contest the bridge today — we will make Red pay for every hex of advance south.",
        "<strong>Decision turn is 5</strong>, when Red 2nd Bn arrives. Until then: preserve, register, observe.",
      ],
    },
    {
      n: "03",
      title: "Main Effort",
      body: [
        "<strong>2nd Bn at <span class='hex'>0509</span>.</strong> Hold the cornfield line. Engage Red 1st Bn if it advances south of <span class='hex'>0608</span>. No retreat without orders.",
        "Conserve fires for the second wave. Do not be drawn into a duel with the 1st Bn over a hex we already wrote off.",
      ],
    },
    {
      n: "04",
      title: "Supporting Effort",
      body: [
        "<strong>Bttry A.</strong> Two missions, in this order:",
        "<strong>Mission 1 (H to H+30).</strong> HE harassment on the bridge approach — hexes <span class='hex'>0608</span> and <span class='hex'>0708</span>. Worry the 1st Bn; do not expect to break it.",
        "<strong>Mission 2 (H+30 onward).</strong> Shift to the road junction at <span class='hex'>0710</span> the moment Red 2nd Bn deploys. That is the kill-box.",
        "<em>Withhold smoke. We want Red visible.</em>",
      ],
    },
    {
      n: "05",
      title: "Reserves & Fallback",
      body: [
        "<strong>3rd Co. (left flank): do NOT withdraw to consolidate.</strong> Hold the ridge at <span class='hex'>0410</span>.",
        "The ridge is the hinge of any counter-attack we mount on turn 5 or 6. Abandoning it cedes the wood line and uncovers Bttry A. We do not give up our hinge to tidy a line.",
        "If pressed, fall back one hex — to <span class='hex'>0411</span>, not further. If 3rd Co. takes a step loss, send word; we will reconsider on turn 4.",
      ],
    },
  ],
  ack: "— Acknowledged. Awaiting turn 4 board state.",
};
