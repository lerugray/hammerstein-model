// Orders panel + share/new-campaign modals.
// Originally a TS port of the Claude Design source bundle; now
// data-driven via props from WargamePage.tsx.

import { useState } from "react";
import { Icon } from "./Icon";
import type { OrdersData } from "./content";
import type { Campaign } from "./api";
import type { Phase } from "./components";

interface OrdersMeta {
  issuedAt?: string;
  tokensIn?: number;
  tokensOut?: number;
  costUsd?: number | null;
  latencyMs?: number | null;
}

interface OrdersPanelProps {
  data: OrdersData | null;
  campaign: Campaign | null;
  serif: boolean;
  state: Phase;
  onShare: () => void;
  meta?: OrdersMeta;
}

export function OrdersPanel({ data, campaign, serif, state, onShare, meta }: OrdersPanelProps) {
  if (state === "empty" || !data) {
    return (
      <div className="wg-card">
        <div className="wg-empty">
          <span className="e-icon">
            <Icon name="swords" />
          </span>
          <div className="e-title">No orders for this campaign yet</div>
          <div>
            Drop a board photo or write a status report and click <b>Issue orders</b>.
          </div>
        </div>
      </div>
    );
  }

  const isStreaming = state === "streaming";
  const turnLabel = campaign ? `T${(campaign.turn || 0) + (state === "completed" ? 0 : 1)}` : "T—";
  const campaignName = campaign?.name ?? "Wargame";
  const stateDirLabel =
    campaign?.slug === "wargame-example"
      ? "wargame-example/turn-log.md"
      : `wargames/${campaign?.slug ?? "<campaign>"}/turn-log.md`;

  const tokensIn = meta?.tokensIn;
  const tokensOut = meta?.tokensOut;
  const costUsd = meta?.costUsd;
  const issuedAt = meta?.issuedAt;

  // Streaming preview: show only the first paragraph of the first
  // section, with a caret. Falls through to full render once state flips.
  const partialBody = data.sections[0]?.body?.[0] ? [data.sections[0].body[0]] : [];

  return (
    <div className={`wg-orders ${serif ? "serif" : ""}`}>
      <div className="wg-orders-hd">
        <div className="wg-orders-hd-l">
          <span className="stamp">Op order · {turnLabel}</span>
          <div>
            <div className="ohd-title">Latest orders — {campaignName}</div>
            <div className="ohd-sub">
              {issuedAt
                ? `Issued ${issuedAt}`
                : isStreaming
                ? "Issuing now…"
                : "Latest issued"}
              {campaign ? ` · model ${campaign.model.split("/").slice(-1)}` : ""}
            </div>
          </div>
        </div>
        <div className="wg-orders-hd-r">
          {isStreaming ? (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                fontFamily: "ui-monospace, Menlo, monospace",
                fontSize: 11.5,
              }}
            >
              <span className="wg-spinner" /> waiting on hp_vision.py
            </span>
          ) : (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              <Icon name="info" className="wg-icon-sm" />{" "}
              {tokensIn ? `${tokensIn.toLocaleString()} tok in` : "—"}
              {tokensOut ? ` · ${tokensOut} out` : ""}
              {typeof costUsd === "number" ? ` · $${costUsd.toFixed(4)}` : ""}
            </span>
          )}
        </div>
      </div>

      {/* What I see on the board — sanity-check belt */}
      <div className="wg-see-board">
        <div className="sb-label">
          <Icon name="eye" className="wg-icon-sm" /> What I see on the board
        </div>
        <div className="sb-body">
          {data.see_board.length > 0 ? (
            <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.55 }}>
              {data.see_board.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          ) : (
            <div style={{ color: "hsl(var(--muted-foreground))" }}>
              No board observations parsed.
            </div>
          )}
          <div className="sb-confirm">
            <span style={{ color: "hsl(var(--muted-foreground))" }}>
              <strong style={{ color: "hsl(38 90% 36%)" }}>Unread:</strong> {data.unread}
            </span>
            <span style={{ marginLeft: "auto", display: "inline-flex", gap: 6 }}>
              <button className="wg-btn wg-btn-sm">
                <Icon name="check" className="wg-icon-sm" /> Confirm
              </button>
              <button className="wg-btn wg-btn-sm">
                <Icon name="alert" className="wg-icon-sm" /> Flag misread
              </button>
            </span>
          </div>
        </div>
      </div>

      <div className="wg-orders-bd">
        {data.sections.map((s, i) => {
          const visibleBody =
            isStreaming && i > 0 ? null : isStreaming && i === 0 ? partialBody : s.body;
          if (!visibleBody) return null;
          return (
            <div key={s.n} className="wg-section">
              <div className="wg-section-hd">
                <span className="wg-section-num">§ {s.n}</span>
                <span className="wg-section-title">{s.title}</span>
              </div>
              <div className="wg-section-body">
                {visibleBody.map((p, j) => (
                  <p
                    key={j}
                    dangerouslySetInnerHTML={{
                      __html:
                        p +
                        (isStreaming && i === 0 && j === visibleBody.length - 1
                          ? '<span class="wg-caret"></span>'
                          : ""),
                    }}
                  />
                ))}
              </div>
            </div>
          );
        })}
        {!isStreaming && (
          <div
            style={{
              marginTop: 14,
              paddingTop: 12,
              borderTop: "1px solid hsl(var(--rule))",
              fontFamily: "ui-monospace, Menlo, monospace",
              fontSize: 12,
              color: "hsl(var(--muted-foreground))",
            }}
          >
            {data.ack}
          </div>
        )}
      </div>

      {!isStreaming && (
        <div className="wg-orders-actions">
          <button
            className="wg-btn"
            onClick={() => navigator.clipboard?.writeText(toMarkdown(data))}
          >
            <Icon name="copy" className="wg-icon-sm" /> Copy as markdown
          </button>
          <button className="wg-btn" onClick={onShare}>
            <Icon name="share" className="wg-icon-sm" /> Share turn
          </button>
          <span className="meta">
            <span>
              writes to{" "}
              <code style={{ fontFamily: "ui-monospace, Menlo, monospace", fontSize: 11 }}>
                {stateDirLabel}
              </code>
            </span>
          </span>
        </div>
      )}
    </div>
  );
}

function toMarkdown(d: OrdersData): string {
  const parts: string[] = [];
  if (d.see_board.length) {
    parts.push(
      "## What I see on the board\n\n" + d.see_board.map((l) => `- ${l}`).join("\n"),
    );
  }
  if (d.unread) parts.push("## Unread\n\n" + d.unread);
  for (const s of d.sections) {
    parts.push(`## ${s.title}\n\n` + s.body.join("\n\n"));
  }
  if (d.ack) parts.push("## Acknowledged\n\n" + d.ack);
  return parts.join("\n\n");
}

// ── Share modal ──────────────────────────────────────────
interface ShareModalProps {
  onClose: () => void;
  campaign: Campaign | null;
  data: OrdersData | null;
}

export function ShareModal({ onClose, campaign, data }: ShareModalProps) {
  const intent =
    data?.sections.find((s) => s.title === "Intent")?.body[0] ??
    "(no intent extracted)";
  const turn = campaign?.turn ?? "—";
  return (
    <div className="wg-modal-scrim" onClick={onClose}>
      <div className="wg-modal" onClick={(e) => e.stopPropagation()} style={{ width: 600 }}>
        <div className="wg-modal-hd">
          <div className="mh-title">Share turn {turn}</div>
          <button className="wg-icon-btn" onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>
        <div className="wg-modal-bd">
          <div style={{ fontSize: 12.5, color: "hsl(var(--muted-foreground))" }}>
            Pre-formatted social card with the turn's Intent line. Image rendering not yet wired.
          </div>
          <div className="wg-share-card">
            <div className="sc-watermark">T{turn}</div>
            <div className="sc-hd">
              <span>Hammerstein Persistent · Wargame</span>
              <span>{campaign?.name ?? "—"}</span>
            </div>
            <div className="sc-headline">
              {intent.replace(/<[^>]+>/g, "").slice(0, 140)}
            </div>
            <div className="sc-ft">
              <span>turn {turn} of campaign</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                <span
                  className="wg-badge b-mono"
                  style={{ borderColor: "hsl(var(--accent) / .4)", color: "hsl(var(--accent))" }}
                >
                  {campaign?.model.split("/").slice(-1) ?? "—"}
                </span>
              </span>
            </div>
          </div>
        </div>
        <div className="wg-modal-ft">
          <span style={{ marginRight: "auto", fontSize: 11.5, color: "hsl(var(--muted-foreground))" }}>
            <span className="wg-badge b-mono">just copy</span> bypasses the preview and copies markdown to clipboard.
          </span>
          <button
            className="wg-btn"
            onClick={() => {
              if (data) navigator.clipboard?.writeText(toMarkdown(data));
              onClose();
            }}
          >
            Just copy
          </button>
          <button className="wg-btn wg-btn-primary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ── New campaign modal ───────────────────────────────────
interface NewCampaignModalProps {
  onClose: () => void;
  onCreate: (body: { name: string; mission_md: string }) => Promise<void>;
}

const DEFAULT_MISSION_MD = `# Bridge Crossing — Steinbach

Operator plays the German defender (Blue) along the Steinbach river.
Blue holds the south bank with two understrength battalions and a battery.
Red (Russian) attacks across the bridge with two battalions and a mech regiment in reserve.

## Victory
- Blue wins if any Red unit south of the river is destroyed by turn 8.
- Red wins on a clean bridgehead (3+ hexes south of the river by turn 6).`;

export function NewCampaignModal({ onClose, onCreate }: NewCampaignModalProps) {
  const [name, setName] = useState("Bridge Crossing — Steinbach");
  const [mission, setMission] = useState(DEFAULT_MISSION_MD);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const slug = slugify(name);

  async function submit() {
    if (!name.trim() || !mission.trim()) {
      setErr("Both name and MISSION.md are required.");
      return;
    }
    setSubmitting(true);
    setErr(null);
    try {
      await onCreate({ name: name.trim(), mission_md: mission });
      onClose();
    } catch (e) {
      setErr(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="wg-modal-scrim" onClick={onClose}>
      <div className="wg-modal" onClick={(e) => e.stopPropagation()}>
        <div className="wg-modal-hd">
          <div className="mh-title">New campaign</div>
          <button className="wg-icon-btn" onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>
        <div className="wg-modal-bd">
          <div className="wg-field">
            <label className="wg-form-label">
              <b>Name</b>
              <span>used as state-dir folder</span>
            </label>
            <input
              className="wg-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <span className="wg-field-hint">
              →{" "}
              <code style={{ fontFamily: "ui-monospace, Menlo, monospace" }}>
                wargames/{slug || "<slug>"}/
              </code>
            </span>
          </div>
          <div className="wg-field">
            <label className="wg-form-label">
              <b>MISSION.md</b>
              <span>scenario brief, ROE, victory conditions</span>
            </label>
            <textarea
              className="wg-textarea"
              rows={8}
              value={mission}
              onChange={(e) => setMission(e.target.value)}
            />
          </div>
          {err && (
            <div style={{ color: "hsl(0 70% 45%)", fontSize: 12 }}>{err}</div>
          )}
        </div>
        <div className="wg-modal-ft">
          <button className="wg-btn" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button
            className="wg-btn wg-btn-primary"
            onClick={submit}
            disabled={submitting}
          >
            <Icon name="plus" className="wg-icon-sm" />{" "}
            {submitting ? "Creating…" : "Create campaign"}
          </button>
        </div>
      </div>
    </div>
  );
}

function slugify(s: string): string {
  return (
    s
      .toLowerCase()
      .replace(/[^\w\s-]/g, "")
      .replace(/[\s_-]+/g, "-")
      .replace(/^-+|-+$/g, "") || ""
  );
}
