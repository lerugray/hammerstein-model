// WargamePage — the wargamer surface, ported from the Claude Design
// prototype. Reuses the existing dashboard's dark/light theme by reading
// the same `dark` class on <html> that the dashboard's Header writes.

import { useEffect, useState } from "react";
import "./wargame.css";
import { Icon } from "./Icon";
import {
  CampaignPicker,
  ImageDropzone,
  IssueRow,
  SheetDropzone,
  StatusTextarea,
  TopBar,
  TurnCard,
  type ActiveTab,
  type Phase,
} from "./components";
import { NewCampaignModal, OrdersPanel, ShareModal } from "./OrdersPanel";
import {
  CAMPAIGN,
  ORDERS_T3,
  PHOTOS_DRAFT,
  SHEET_DRAFT,
  STATUS_DRAFT,
  TURN_LOG,
} from "./content";

interface Props {
  activeTab: ActiveTab;
  onSwitchTab: (tab: ActiveTab) => void;
  dark: boolean;
  onToggleDark: () => void;
}

export function WargamePage({ activeTab, onSwitchTab, dark, onToggleDark }: Props) {
  const [phase, setPhase] = useState<Phase>("completed");
  const [status, setStatus] = useState<string>(STATUS_DRAFT);
  const [expanded, setExpanded] = useState<number | null>(3);
  const [modal, setModal] = useState<"share" | "new" | null>(null);
  const [serif, setSerif] = useState(false);

  // Sync the textarea content with phase changes (so flipping to "empty"
  // clears it and back fills it back in)
  useEffect(() => {
    if (phase === "empty") setStatus("");
    else setStatus(STATUS_DRAFT);
  }, [phase]);

  const photos = phase === "empty" ? [] : PHOTOS_DRAFT;
  const sheet = phase === "empty" ? null : SHEET_DRAFT;
  const tokens =
    (phase === "empty" || phase === "drafting") && (status || photos.length)
      ? Math.round(4180 + status.length / 4)
      : 4792;

  const dropzoneActive = phase === "drafting";

  return (
    <div className="wargame-page">
      <div className="wg-app">
        <TopBar
          dark={dark}
          onToggleDark={onToggleDark}
          spend={CAMPAIGN.spend}
          spendBudget={CAMPAIGN.spendBudget}
          activeTab={activeTab}
          onSwitchTab={onSwitchTab}
        />

        <main className="wg-workspace">
          <div className="wg-campaign-bar">
            <CampaignPicker campaign={CAMPAIGN} onNew={() => setModal("new")} />
          </div>

          <div className="wg-cols">
            {/* ── left column: turn input ─────────────────────── */}
            <div className="wg-card">
              <div className="wg-card-hd">
                <span>Turn {CAMPAIGN.turn} input</span>
                <span
                  className="hd-r"
                  style={{ color: "hsl(var(--muted-foreground))", fontSize: 11.5 }}
                >
                  <Icon name="history" className="wg-icon-sm" />
                  <span>
                    last issued <b style={{ color: "hsl(var(--foreground))" }}>1 day ago</b> · turn 2
                  </span>
                </span>
              </div>
              <div
                className="wg-card-bd"
                style={{ display: "flex", flexDirection: "column", gap: "var(--dens-gap)" }}
              >
                <div>
                  <div className="wg-form-label">
                    <b>Board photos</b>
                    <span>required if no spreadsheet</span>
                  </div>
                  <ImageDropzone photos={photos} active={dropzoneActive} />
                </div>
                <div>
                  <div className="wg-form-label">
                    <b>Order of battle</b>
                    <span>spreadsheet</span>
                  </div>
                  <SheetDropzone sheet={sheet} />
                </div>
                <div>
                  <div className="wg-form-label">
                    <b>Status report</b>
                    <span>verbal — what just happened, what you're thinking</span>
                  </div>
                  <StatusTextarea
                    value={status}
                    onChange={setStatus}
                    placeholder={`e.g. "Just played turn 3. Russians took the bridge but lost a regiment to my artillery. Thinking of withdrawing my left flank to consolidate."`}
                  />
                </div>
                <IssueRow
                  enabled={!!status || photos.length > 0 || !!sheet}
                  state={phase}
                  tokens={tokens}
                  onIssue={() => setPhase("streaming")}
                />
              </div>
            </div>

            {/* ── right column: turn-log ──────────────────────── */}
            <aside className="wg-card wg-turnlog">
              <div className="wg-card-hd">
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <Icon name="history" className="wg-icon-sm" /> Turn log
                </span>
                <span
                  className="hd-r"
                  style={{ color: "hsl(var(--muted-foreground))", fontSize: 11.5 }}
                >
                  {TURN_LOG.length} turn{TURN_LOG.length === 1 ? "" : "s"}
                </span>
              </div>
              <div className="wg-turnlog-bd">
                {TURN_LOG.map((entry) => (
                  <TurnCard
                    key={entry.turn}
                    entry={entry}
                    expanded={expanded === entry.turn}
                    onToggle={() =>
                      setExpanded(expanded === entry.turn ? null : entry.turn)
                    }
                  />
                ))}
                <div
                  style={{
                    fontSize: 11,
                    color: "hsl(var(--muted-foreground))",
                    textAlign: "center",
                    padding: "6px 0 2px",
                  }}
                >
                  campaign began{" "}
                  <b style={{ color: "hsl(var(--foreground))" }}>{CAMPAIGN.started}</b> · 6 days
                </div>
              </div>
            </aside>
          </div>

          {/* ── orders panel ───────────────────────────────────── */}
          <OrdersPanel
            data={ORDERS_T3}
            serif={serif}
            state={phase}
            onShare={() => setModal("share")}
          />

          {/* ── dev controls (state switcher + serif toggle) ───── */}
          <div
            className="wg-card"
            style={{
              padding: "10px 14px",
              display: "flex",
              alignItems: "center",
              gap: 14,
              flexWrap: "wrap",
              fontSize: 11.5,
              color: "hsl(var(--muted-foreground))",
            }}
          >
            <span style={{ fontWeight: 600, letterSpacing: ".04em", textTransform: "uppercase" }}>
              dev preview
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              phase
              {(["empty", "drafting", "streaming", "completed"] as Phase[]).map((p) => (
                <button
                  key={p}
                  className="wg-btn wg-btn-sm"
                  style={{
                    background:
                      phase === p ? "hsl(var(--secondary))" : "hsl(var(--card))",
                    color:
                      phase === p
                        ? "hsl(var(--secondary-foreground))"
                        : "hsl(var(--muted-foreground))",
                    borderColor: phase === p ? "hsl(var(--secondary))" : undefined,
                  }}
                  onClick={() => setPhase(p)}
                >
                  {p}
                </button>
              ))}
            </span>
            <label
              style={{ display: "inline-flex", alignItems: "center", gap: 5, cursor: "pointer" }}
            >
              <input
                type="checkbox"
                checked={serif}
                onChange={(e) => setSerif(e.target.checked)}
              />
              serif orders panel
            </label>
            <span style={{ marginLeft: "auto", opacity: 0.7 }}>
              backend: <code>hp_vision.py</code> (not wired yet · static fixture)
            </span>
          </div>
        </main>
      </div>

      {modal === "share" && <ShareModal onClose={() => setModal(null)} />}
      {modal === "new" && <NewCampaignModal onClose={() => setModal(null)} />}
    </div>
  );
}
