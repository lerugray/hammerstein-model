// Orders panel + share/new-campaign modals.
// TS port of the Claude Design source bundle.

import { Icon } from "./Icon";
import type { OrdersData } from "./content";
import type { Phase } from "./components";

interface OrdersPanelProps {
  data: OrdersData;
  serif: boolean;
  state: Phase;
  onShare: () => void;
}

export function OrdersPanel({ data, serif, state, onShare }: OrdersPanelProps) {
  if (state === "empty") {
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
  const partialBody = [data.sections[0].body[0]];

  return (
    <div className={`wg-orders ${serif ? "serif" : ""}`}>
      <div className="wg-orders-hd">
        <div className="wg-orders-hd-l">
          <span className="stamp">Op order · T3</span>
          <div>
            <div className="ohd-title">Latest orders — Bridge Crossing, Steinbach</div>
            <div className="ohd-sub">
              Issued 21:14 · 8 May 2026 · operator playing Blue (German)
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
              <span className="wg-spinner" /> streaming · 318 / ~612 tok · 4.2s
            </span>
          ) : (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              <Icon name="info" className="wg-icon-sm" /> 4,792 tok in · 612 out · $0.034
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
          <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.55 }}>
            {data.see_board.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
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
          if (!visibleBody && !(isStreaming && i === 1)) return null;
          return (
            <div key={s.n} className="wg-section">
              <div className="wg-section-hd">
                <span className="wg-section-num">§ {s.n}</span>
                <span className="wg-section-title">{s.title}</span>
                {!isStreaming && i === 0 && (
                  <span className="wg-section-tag">red 2 · blue 2 · 60% ammo</span>
                )}
              </div>
              <div className="wg-section-body">
                {visibleBody &&
                  visibleBody.map((p, j) => (
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
                {isStreaming && i === 1 && (
                  <p style={{ color: "hsl(var(--muted-foreground))" }}>
                    <em>
                      Bleed Red across the river<span className="wg-caret" />
                    </em>
                  </p>
                )}
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
          <button className="wg-btn">
            <Icon name="copy" className="wg-icon-sm" /> Copy as markdown
          </button>
          <button className="wg-btn" onClick={onShare}>
            <Icon name="share" className="wg-icon-sm" /> Share turn
          </button>
          <button className="wg-btn wg-btn-primary">
            <Icon name="save" className="wg-icon-sm" /> Append to turn-log.md
          </button>
          <span className="meta">
            <span>
              writes to{" "}
              <code style={{ fontFamily: "ui-monospace, Menlo, monospace", fontSize: 11 }}>
                ~/.hammerstein/wargames/steinbach/turn-log.md
              </code>
            </span>
          </span>
        </div>
      )}
    </div>
  );
}

// ── Share modal ──────────────────────────────────────────
interface ModalProps {
  onClose: () => void;
}

export function ShareModal({ onClose }: ModalProps) {
  return (
    <div className="wg-modal-scrim" onClick={onClose}>
      <div className="wg-modal" onClick={(e) => e.stopPropagation()} style={{ width: 600 }}>
        <div className="wg-modal-hd">
          <div className="mh-title">Share turn 3</div>
          <button className="wg-icon-btn" onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>
        <div className="wg-modal-bd">
          <div style={{ fontSize: 12.5, color: "hsl(var(--muted-foreground))" }}>
            Pre-formatted social card with the turn's Intent line. Image is rendered server-side at
            1200×675.
          </div>
          <div className="wg-share-card">
            <div className="sc-watermark">T3</div>
            <div className="sc-hd">
              <span>Hammerstein Persistent · Wargame</span>
              <span>Bridge Crossing — Steinbach</span>
            </div>
            <div className="sc-headline">Decision turn is 5. Until then: preserve, register, observe.</div>
            <div className="sc-quote">
              "We have lost the bridgehead. We have not lost the engagement."
            </div>
            <div className="sc-ft">
              <span>turn 3 of campaign · operator: Blue</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                <span
                  className="wg-badge b-mono"
                  style={{ borderColor: "hsl(var(--accent) / .4)", color: "hsl(var(--accent))" }}
                >
                  claude-sonnet-4.6
                </span>
              </span>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
            <input
              className="wg-input"
              readOnly
              value="https://hammerstein.local/share/steinbach-t3.png"
              style={{ flex: 1 }}
            />
            <button className="wg-btn">
              <Icon name="copy" className="wg-icon-sm" /> Copy URL
            </button>
          </div>
        </div>
        <div className="wg-modal-ft">
          <span style={{ marginRight: "auto", fontSize: 11.5, color: "hsl(var(--muted-foreground))" }}>
            <span className="wg-badge b-mono">just copy</span> bypasses the preview and copies markdown
            to clipboard.
          </span>
          <button className="wg-btn" onClick={onClose}>
            Just copy
          </button>
          <button className="wg-btn">
            <Icon name="image" className="wg-icon-sm" /> Download PNG
          </button>
          <button className="wg-btn wg-btn-primary">
            <Icon name="share" className="wg-icon-sm" /> Open share sheet
          </button>
        </div>
      </div>
    </div>
  );
}

// ── New campaign modal ───────────────────────────────────
export function NewCampaignModal({ onClose }: ModalProps) {
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
            <input className="wg-input" defaultValue="Bridge Crossing — Steinbach" />
            <span className="wg-field-hint">
              →{" "}
              <code style={{ fontFamily: "ui-monospace, Menlo, monospace" }}>
                ~/.hammerstein/wargames/bridge-crossing-steinbach/
              </code>
            </span>
          </div>
          <div className="wg-field">
            <label className="wg-form-label">
              <b>MISSION.md</b>
              <span>paste the mission, opfor, victory conditions</span>
            </label>
            <textarea
              className="wg-textarea"
              rows={6}
              defaultValue={`# Bridge Crossing — Steinbach\n\nOperator plays the German defender (Blue) along the Steinbach river.\nBlue holds the south bank with two understrength battalions and a battery.\nRed (Russian) attacks across the bridge with two battalions and a mech regiment in reserve.\n\n## Victory\n- Blue wins if any Red unit south of the river is destroyed by turn 8.\n- Red wins on a clean bridgehead (3+ hexes south of the river by turn 6).`}
            />
          </div>
          <div className="wg-field-row">
            <div className="wg-field" style={{ flex: 2 }}>
              <label className="wg-form-label">
                <b>tasks.json</b>
                <span>optional</span>
              </label>
              <div className="wg-dropzone compact" style={{ padding: "8px 11px" }}>
                <span className="wg-dz-icon" style={{ width: 24, height: 24 }}>
                  <Icon name="sheet" className="wg-icon-sm" />
                </span>
                <span style={{ color: "hsl(var(--muted-foreground))", fontSize: 12 }}>
                  Drop tasks.json or browse…
                </span>
              </div>
            </div>
            <div className="wg-field" style={{ flex: 1 }}>
              <label className="wg-form-label">
                <b>Voice</b>
                <span>orders register</span>
              </label>
              <select className="wg-select" defaultValue="auftragstaktik">
                <option value="auftragstaktik">Auftragstaktik (default)</option>
                <option value="britsh-staff">British staff officer</option>
                <option value="plain">Plain operational</option>
              </select>
            </div>
          </div>
        </div>
        <div className="wg-modal-ft">
          <button className="wg-btn" onClick={onClose}>
            Cancel
          </button>
          <button className="wg-btn wg-btn-primary">
            <Icon name="plus" className="wg-icon-sm" /> Create campaign
          </button>
        </div>
      </div>
    </div>
  );
}
