// Wargame surface — top-level building blocks.
// Faithful TypeScript port of the Claude Design source bundle.

import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icon";
import type { CampaignInfo, Photo, Sheet, TurnLogEntry } from "./content";

export type Phase = "empty" | "drafting" | "streaming" | "completed";
export type ActiveTab = "dashboard" | "wargame";

// ── Top bar ──────────────────────────────────────────────
interface TopBarProps {
  dark: boolean;
  onToggleDark: () => void;
  spend: number;
  spendBudget: number;
  activeTab: ActiveTab;
  onSwitchTab: (tab: ActiveTab) => void;
}

export function TopBar({ dark, onToggleDark, spend, spendBudget, activeTab, onSwitchTab }: TopBarProps) {
  return (
    <header className="wg-topbar">
      <div className="wg-topbar-l">
        <span className="wg-brand">
          <span className="wg-brand-mark">hp</span>
          <span className="wg-brand-name">Hammerstein Persistent</span>
          <span className="wg-brand-sub">/ wargame</span>
        </span>
        <nav className="wg-nav-tabs">
          <button
            className={`wg-nav-tab ${activeTab === "dashboard" ? "active" : ""}`}
            onClick={() => onSwitchTab("dashboard")}
          >
            Dashboard
          </button>
          <button
            className={`wg-nav-tab ${activeTab === "wargame" ? "active" : ""}`}
            onClick={() => onSwitchTab("wargame")}
          >
            Wargame
          </button>
        </nav>
      </div>
      <div className="wg-topbar-r">
        <span className="wg-cost-pill" title="Running campaign spend">
          <span>spend</span>
          <span className="cp-amt">${spend.toFixed(2)}</span>
          <span style={{ color: "hsl(var(--muted-foreground))" }}>/ ${spendBudget.toFixed(2)}</span>
          <span className="cp-spark">
            {[3, 5, 4, 7, 6, 9].map((h, i) => (
              <i key={i} style={{ height: `${h * 1.2}px` }} />
            ))}
          </span>
        </span>
        <button className="wg-icon-btn" title="Theme" onClick={onToggleDark}>
          <Icon name={dark ? "sun" : "moon"} />
        </button>
        <button className="wg-icon-btn" title="Reload">
          <Icon name="refresh" />
        </button>
        <button className="wg-icon-btn" title="Settings">
          <Icon name="settings" />
        </button>
      </div>
    </header>
  );
}

// ── Campaign picker ──────────────────────────────────────
interface CampaignPickerProps {
  campaign: CampaignInfo;
  onNew: () => void;
}

export function CampaignPicker({ campaign, onNew }: CampaignPickerProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  return (
    <div ref={ref} className="wg-campaign-picker">
      <span className="cp-label">Campaign</span>
      <span className="cp-name">{campaign.name}</span>
      <span className="wg-badge b-primary">turn {campaign.turn}</span>
      <span className="cp-meta">
        <span>
          state-dir{" "}
          <code style={{ fontFamily: "ui-monospace, Menlo, monospace", fontSize: 11 }}>
            ~/.hammerstein/wargames/steinbach/
          </code>
        </span>
        <span>·</span>
        <span>
          <b>{campaign.cost_breakdown.model}</b>
        </span>
      </span>
      <button className="cp-chev" onClick={() => setOpen((o) => !o)} aria-label="Switch campaign">
        <Icon name="chev-down" />
      </button>
      {open && (
        <div className="wg-dropdown">
          <div className="wg-dd-item" onClick={() => setOpen(false)}>
            <Icon name="check" className="wg-icon-sm" />
            <span className="dd-name">Bridge Crossing — Steinbach</span>
            <span className="dd-meta">turn 3 · 6 days</span>
          </div>
          <div className="wg-dd-item" onClick={() => setOpen(false)}>
            <span style={{ width: 14 }} />
            <span className="dd-name">Operation Saturn — Voronezh</span>
            <span className="dd-meta">turn 11 · 23 days</span>
          </div>
          <div className="wg-dd-item" onClick={() => setOpen(false)}>
            <span style={{ width: 14 }} />
            <span className="dd-name">Tannenberg '14 — sandbox</span>
            <span className="dd-meta">turn 1 · today</span>
          </div>
          <div className="wg-dd-sep" />
          <div
            className="wg-dd-item wg-dd-new"
            onClick={() => {
              setOpen(false);
              onNew();
            }}
          >
            <Icon name="plus" className="wg-icon-sm" />
            <span className="dd-name">New campaign…</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Image dropzone ───────────────────────────────────────
interface ImageDropzoneProps {
  photos: Photo[];
  active: boolean;
}

export function ImageDropzone({ photos, active }: ImageDropzoneProps) {
  const showPhotos = photos.length > 0;
  return (
    <div className={`wg-dropzone ${active ? "active" : ""}`}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div className="wg-dz-prompt">
          <span className="wg-dz-icon">
            <Icon name="image" />
          </span>
          <div>
            <div>
              <b>Drop board photos</b> here, or click to browse
            </div>
            <div style={{ fontSize: 11.5, color: "hsl(var(--muted-foreground))" }}>
              Multi-file.{" "}
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                <Icon name="camera" className="wg-icon-sm" /> tap to use camera on mobile
              </span>
            </div>
          </div>
        </div>
        {showPhotos && (
          <div className="wg-dz-meta">
            <span>{photos.length} image{photos.length === 1 ? "" : "s"}</span>
            <span>·</span>
            <span>{photos.reduce((a, p) => a + p.kb, 0).toLocaleString()} KB</span>
            {photos.some((p) => p.kb > 2048) && (
              <span className="wg-dz-warn">
                <Icon name="alert" className="wg-icon-sm" /> server-side downscale
              </span>
            )}
          </div>
        )}
      </div>
      {showPhotos && (
        <div className="wg-dz-thumbs">
          {photos.map((p, i) => (
            <div key={i} className="wg-thumb">
              <div className={`wg-thumb-art ${i === 1 ? "t2" : ""}`} />
              <button className="wg-thumb-x" aria-label="Remove">
                <Icon name="x" className="wg-icon-sm" />
              </button>
              <div className="wg-thumb-meta">
                <span>{p.label}</span>
                <span>{p.kb > 1024 ? `${(p.kb / 1024).toFixed(1)}MB` : `${p.kb}KB`}</span>
              </div>
            </div>
          ))}
          <button className="wg-thumb-add">
            <Icon name="plus" />
            <span>add another</span>
          </button>
        </div>
      )}
    </div>
  );
}

// ── OOB sheet dropzone ───────────────────────────────────
interface SheetDropzoneProps {
  sheet: Sheet | null;
}

export function SheetDropzone({ sheet }: SheetDropzoneProps) {
  if (sheet) {
    return (
      <div className="wg-sheet-preview">
        <span className="sp-icon">
          <Icon name="sheet" className="wg-icon-sm" />
        </span>
        <div style={{ flex: 1 }}>
          <div className="sp-name">{sheet.name}</div>
          <div className="sp-cols">
            sheet: <b style={{ color: "hsl(var(--foreground))" }}>{sheet.sheetName}</b> · cols:{" "}
            {sheet.cols.join(", ")}
          </div>
        </div>
        <span className="wg-badge b-accent">parsed · {sheet.rows} rows</span>
        <button className="wg-btn wg-btn-ghost wg-btn-sm">
          <Icon name="x" className="wg-icon-sm" />
        </button>
      </div>
    );
  }
  return (
    <div className="wg-dropzone compact">
      <span className="wg-dz-icon" style={{ width: 28, height: 28 }}>
        <Icon name="sheet" className="wg-icon-sm" />
      </span>
      <div className="wg-dz-prompt" style={{ alignItems: "baseline" }}>
        <div>
          <div>
            <b>OOB spreadsheet</b>{" "}
            <span style={{ color: "hsl(var(--muted-foreground))", fontWeight: 400 }}>· optional</span>
          </div>
          <div style={{ fontSize: 11.5, color: "hsl(var(--muted-foreground))" }}>
            Single .xlsx — confirms unit positions & strengths
          </div>
        </div>
      </div>
      <span className="wg-badge b-mono" style={{ marginLeft: "auto" }}>
        .xlsx
      </span>
    </div>
  );
}

// ── Status textarea ──────────────────────────────────────
interface StatusTextareaProps {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}

export function StatusTextarea({ value, onChange, placeholder }: StatusTextareaProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    ref.current.style.height = "auto";
    ref.current.style.height = ref.current.scrollHeight + "px";
  }, [value]);
  const words = (value || "").trim().split(/\s+/).filter(Boolean).length;
  const target = words >= 50 && words <= 300;
  return (
    <div className="wg-status-wrap">
      <textarea
        ref={ref}
        className="wg-textarea"
        rows={4}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{ minHeight: 120, fontSize: 13, lineHeight: 1.55 }}
      />
      <div className="wg-status-meta">
        <span className="voice-hint">
          <Icon name="info" className="wg-icon-sm" />
          Plain operational language. Hex labels welcome.
        </span>
        <span style={{ color: target ? "hsl(var(--muted-foreground))" : "hsl(38 90% 36%)" }}>
          {words} words <span style={{ opacity: 0.55 }}>· target 50–300</span>
        </span>
      </div>
    </div>
  );
}

// ── Issue button row ─────────────────────────────────────
interface IssueRowProps {
  enabled: boolean;
  state: Phase;
  onIssue: () => void;
  tokens: number;
}

export function IssueRow({ enabled, state, onIssue, tokens }: IssueRowProps) {
  // Sonnet 4.6 OpenRouter pricing: ~$6.50/M input, ~$22.50/M output
  const cost = (tokens / 1000) * 6.5e-3 + (612 / 1000) * 22.5e-3;
  if (state === "streaming") {
    return (
      <div className="wg-issue-row">
        <div className="wg-issue-cost">
          <span>streaming response</span>
          <span className="wg-streaming-meta">
            <span className="wg-spinner" /> 318 tok · 4.2s elapsed
          </span>
        </div>
        <button className="wg-btn wg-issue-btn" disabled style={{ marginLeft: "auto" }}>
          <Icon name="swords" /> Awaiting orders…
        </button>
      </div>
    );
  }
  return (
    <div className="wg-issue-row">
      <div className="wg-issue-cost">
        <span>cost preview</span>
        <span className="ic-bd">
          <span className="ic-amt">${cost.toFixed(3)}</span>
          <code>~{tokens.toLocaleString()} in · ~612 out</code>
        </span>
      </div>
      <button
        className="wg-btn wg-btn-primary wg-issue-btn"
        disabled={!enabled}
        onClick={onIssue}
        style={{ marginLeft: "auto" }}
      >
        <Icon name="send" /> Issue orders
      </button>
    </div>
  );
}

// ── Turn-log card ────────────────────────────────────────
interface TurnCardProps {
  entry: TurnLogEntry;
  expanded: boolean;
  onToggle: () => void;
}

export function TurnCard({ entry, expanded, onToggle }: TurnCardProps) {
  const isCurrent = entry.current;
  return (
    <div className={`wg-turncard ${isCurrent ? "current" : ""}`}>
      <div className="wg-tc-hd" onClick={onToggle}>
        <div className="wg-tc-hd-l">
          <span className={`wg-tc-num ${isCurrent ? "current-num" : ""}`}>T{entry.turn}</span>
          <span className="wg-tc-time">{entry.time}</span>
        </div>
        <Icon name={expanded ? "chev-up" : "chev-down"} className="wg-icon-sm" />
      </div>
      <div className="wg-tc-bd">
        <div className="wg-tc-status">{entry.status}</div>
        <div className="wg-tc-intent">
          <span className="tag">INTENT</span>
          <span>{entry.intent}</span>
        </div>
        {expanded && entry.turn === 3 && (
          <>
            <hr className="wg-rule" style={{ margin: "10px 0" }} />
            <div style={{ fontSize: 12, lineHeight: 1.55 }}>
              <strong>Main effort:</strong> 2nd Bn at <code className="hex">0509</code> — hold the
              cornfield line. <br />
              <strong>Supporting:</strong> Bttry A — HE on bridge approach, then shift fire to{" "}
              <code className="hex">0710</code>. <br />
              <strong>Reserves:</strong> 3rd Co. <em>holds</em> the ridge. Do not withdraw.
            </div>
          </>
        )}
        <div className="wg-tc-model">
          <Icon name="info" className="wg-icon-sm" /> {entry.model} · 4,792 tok · $0.03
        </div>
      </div>
    </div>
  );
}
