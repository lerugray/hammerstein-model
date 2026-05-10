// Wargame surface — top-level building blocks.
// Originally a faithful TypeScript port of the Claude Design source
// bundle; now wired to the live /api/wargame/* backend (see api.ts).

import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icon";
import type { TurnLogEntry } from "./content";
import type { Campaign } from "./api";

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
  onReload?: () => void;
}

export function TopBar({
  dark, onToggleDark, spend, spendBudget, activeTab, onSwitchTab, onReload,
}: TopBarProps) {
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
        <button className="wg-icon-btn" title="Reload" onClick={onReload}>
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
  campaigns: Campaign[];
  active: Campaign | null;
  onSelect: (slug: string) => void;
  onNew: () => void;
}

function relTime(startedISO: string): string {
  if (!startedISO) return "";
  const d = new Date(startedISO);
  if (isNaN(d.getTime())) return startedISO;
  const days = Math.floor((Date.now() - d.getTime()) / 86400_000);
  if (days <= 0) return "today";
  if (days === 1) return "1 day";
  if (days < 30) return `${days} days`;
  const months = Math.floor(days / 30);
  return months === 1 ? "1 mo" : `${months} mo`;
}

export function CampaignPicker({ campaigns, active, onSelect, onNew }: CampaignPickerProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const display = active ?? campaigns[0] ?? null;

  return (
    <div ref={ref} className="wg-campaign-picker">
      <span className="cp-label">Campaign</span>
      <span className="cp-name">{display ? display.name : "no campaigns"}</span>
      {display && <span className="wg-badge b-primary">turn {display.turn || "—"}</span>}
      {display && (
        <span className="cp-meta">
          <span>
            state-dir{" "}
            <code style={{ fontFamily: "ui-monospace, Menlo, monospace", fontSize: 11 }}>
              {display.slug === "wargame-example"
                ? "wargame-example/"
                : `wargames/${display.slug}/`}
            </code>
          </span>
          <span>·</span>
          <span>
            <b>{display.model}</b>
          </span>
        </span>
      )}
      <button className="cp-chev" onClick={() => setOpen((o) => !o)} aria-label="Switch campaign">
        <Icon name="chev-down" />
      </button>
      {open && (
        <div className="wg-dropdown">
          {campaigns.map((c) => (
            <div
              key={c.slug}
              className="wg-dd-item"
              onClick={() => {
                setOpen(false);
                onSelect(c.slug);
              }}
            >
              {display && c.slug === display.slug ? (
                <Icon name="check" className="wg-icon-sm" />
              ) : (
                <span style={{ width: 14 }} />
              )}
              <span className="dd-name">{c.name}</span>
              <span className="dd-meta">
                turn {c.turn || "—"} · {relTime(c.started)}
              </span>
            </div>
          ))}
          {campaigns.length > 0 && <div className="wg-dd-sep" />}
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
  files: File[];
  onChange: (files: File[]) => void;
  active: boolean;
}

export function ImageDropzone({ files, onChange, active }: ImageDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [previewUrls, setPreviewUrls] = useState<string[]>([]);

  useEffect(() => {
    const urls = files.map((f) => URL.createObjectURL(f));
    setPreviewUrls(urls);
    return () => urls.forEach((u) => URL.revokeObjectURL(u));
  }, [files]);

  function addFiles(list: FileList | null) {
    if (!list || !list.length) return;
    const next = [...files];
    for (const f of Array.from(list)) {
      if (f.type.startsWith("image/")) next.push(f);
    }
    onChange(next);
  }

  function remove(idx: number) {
    const next = files.slice();
    next.splice(idx, 1);
    onChange(next);
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    addFiles(e.dataTransfer.files);
  }

  const showPhotos = files.length > 0;
  const totalKb = files.reduce((a, f) => a + Math.round(f.size / 1024), 0);
  const oversized = files.some((f) => f.size > 2 * 1024 * 1024);

  return (
    <div
      className={`wg-dropzone ${active ? "active" : ""}`}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDrop}
      style={{ cursor: "pointer" }}
    >
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif"
        multiple
        style={{ display: "none" }}
        onChange={(e) => {
          addFiles(e.target.files);
          e.target.value = "";
        }}
      />
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
            <span>{files.length} image{files.length === 1 ? "" : "s"}</span>
            <span>·</span>
            <span>{totalKb.toLocaleString()} KB</span>
            {oversized && (
              <span className="wg-dz-warn">
                <Icon name="alert" className="wg-icon-sm" /> server-side downscale
              </span>
            )}
          </div>
        )}
      </div>
      {showPhotos && (
        <div className="wg-dz-thumbs">
          {files.map((f, i) => (
            <div key={i} className="wg-thumb" onClick={(e) => e.stopPropagation()}>
              <div
                className="wg-thumb-art"
                style={{
                  backgroundImage: previewUrls[i] ? `url(${previewUrls[i]})` : undefined,
                  backgroundSize: "cover",
                  backgroundPosition: "center",
                }}
              />
              <button
                className="wg-thumb-x"
                aria-label="Remove"
                onClick={(e) => {
                  e.stopPropagation();
                  remove(i);
                }}
              >
                <Icon name="x" className="wg-icon-sm" />
              </button>
              <div className="wg-thumb-meta">
                <span title={f.name}>
                  {f.name.length > 16 ? f.name.slice(0, 14) + "…" : f.name}
                </span>
                <span>
                  {f.size > 1024 * 1024
                    ? `${(f.size / 1024 / 1024).toFixed(1)}MB`
                    : `${Math.round(f.size / 1024)}KB`}
                </span>
              </div>
            </div>
          ))}
          <button
            className="wg-thumb-add"
            onClick={(e) => {
              e.stopPropagation();
              inputRef.current?.click();
            }}
          >
            <Icon name="plus" />
            <span>add another</span>
          </button>
        </div>
      )}
    </div>
  );
}

// ── Sources panel (NotebookLM-style: rules + reference images) ──
interface SourcesPanelProps {
  slug: string | null;
  sources: import("./api").Source[];
  uploading: boolean;
  error: string | null;
  onUpload: (files: File[]) => void;
  onDelete: (kind: import("./api").SourceKind, name: string) => void;
  onRegenerateDigest?: (name: string) => Promise<void>;
}

// Token-budget warning threshold. Sonnet 4.6 has a 200k context but
// turn-by-turn play accumulates: digest + state + status + photos.
// Warn at 30k preamble tokens — well below the limit but a sign that
// the campaign has accumulated a lot of context the operator may want
// to prune.
const TOKEN_WARN_THRESHOLD = 30_000;

const ACCEPTED_EXT_SET = new Set([
  ".pdf", ".md", ".markdown", ".txt",
  ".jpg", ".jpeg", ".png", ".webp", ".gif",
]);

export function SourcesPanel({
  slug, sources, uploading, error, onUpload, onDelete, onRegenerateDigest,
}: SourcesPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [regeneratingName, setRegeneratingName] = useState<string | null>(null);

  async function handleRegenerate(name: string) {
    if (!onRegenerateDigest) return;
    setRegeneratingName(name);
    try {
      await onRegenerateDigest(name);
    } finally {
      setRegeneratingName(null);
    }
  }
  // Reference image previews are not currently fetched client-side
  // (server doesn't expose a static route for <state-dir>/reference/
  // yet); the row shows a placeholder image icon. If we want real
  // thumbnails later, add a /api/wargame/campaigns/{slug}/reference/{name}
  // endpoint and `URL.createObjectURL` the response Blob.

  function pick(list: FileList | null) {
    if (!list || !list.length) return;
    const accepted: File[] = [];
    for (const f of Array.from(list)) {
      const lower = f.name.toLowerCase();
      const dot = lower.lastIndexOf(".");
      const ext = dot >= 0 ? lower.slice(dot) : "";
      if (ACCEPTED_EXT_SET.has(ext)) accepted.push(f);
    }
    if (accepted.length) onUpload(accepted);
  }

  const rules = sources.filter((s) => s.kind === "rules");
  const refs = sources.filter((s) => s.kind === "reference");
  const totalTokens = rules.reduce((a, s) => a + s.tokens_est, 0);
  const overBudget = totalTokens > TOKEN_WARN_THRESHOLD;

  return (
    <div className="wg-card" style={{ marginBottom: "var(--dens-gap)" }}>
      <div className="wg-card-hd">
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Icon name="sheet" className="wg-icon-sm" /> Sources
          <span
            style={{
              color: "hsl(var(--muted-foreground))",
              fontWeight: 400,
              fontSize: 11.5,
            }}
          >
            — rulebooks + reference images, persisted in every turn's context
          </span>
        </span>
        <span
          className="hd-r"
          style={{ color: "hsl(var(--muted-foreground))", fontSize: 11.5 }}
        >
          {sources.length === 0 ? (
            "no sources mounted"
          ) : (
            <>
              <b style={{ color: "hsl(var(--foreground))" }}>{rules.length}</b>{" "}
              rule{rules.length === 1 ? "" : "s"} ·{" "}
              <b style={{ color: "hsl(var(--foreground))" }}>{refs.length}</b>{" "}
              ref image{refs.length === 1 ? "" : "s"}
              {totalTokens > 0 && (
                <>
                  {" · "}
                  <b style={{ color: overBudget ? "hsl(38 90% 36%)" : "hsl(var(--foreground))" }}>
                    ~{totalTokens.toLocaleString()}
                  </b>{" "}
                  tok in preamble
                  {overBudget && (
                    <span
                      style={{ color: "hsl(38 90% 36%)", marginLeft: 6 }}
                      title="Per-turn cost is climbing. Consider pruning sources or trimming digests."
                    >
                      <Icon name="alert" className="wg-icon-sm" /> high
                    </span>
                  )}
                </>
              )}
            </>
          )}
        </span>
      </div>
      <div className="wg-card-bd" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {sources.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {sources.map((s) => {
              const isImage = s.kind === "reference";
              const hasDigest = !!s.has_digest;
              const digestTok = s.digest_tokens_est ?? 0;
              const thumbUrl =
                isImage && slug
                  ? `/api/wargame/campaigns/${encodeURIComponent(slug)}/reference/${encodeURIComponent(s.name)}`
                  : null;
              const regenerating = regeneratingName === s.name;
              return (
                <div
                  key={`${s.kind}-${s.name}`}
                  className="wg-sheet-preview"
                  style={{ padding: "6px 10px" }}
                >
                  <span className="sp-icon" style={{ overflow: "hidden" }}>
                    {thumbUrl ? (
                      <img
                        src={thumbUrl}
                        alt=""
                        style={{
                          width: "100%",
                          height: "100%",
                          objectFit: "cover",
                          borderRadius: 3,
                        }}
                      />
                    ) : (
                      <Icon name={isImage ? "image" : "sheet"} className="wg-icon-sm" />
                    )}
                  </span>
                  <div style={{ flex: 1 }}>
                    <div className="sp-name">{s.name}</div>
                    <div className="sp-cols">
                      {(s.size_bytes / 1024).toFixed(1)} KB
                      {hasDigest ? (
                        <>
                          {" · digest "}~{digestTok.toLocaleString()} tok in preamble (full
                          rulebook on disk for citation)
                        </>
                      ) : s.tokens_est > 0 ? (
                        ` · ~${s.tokens_est.toLocaleString()} tok in preamble`
                      ) : (
                        ""
                      )}
                      {" · "}
                      {s.source}
                    </div>
                  </div>
                  {hasDigest && (
                    <span
                      className="wg-badge b-accent"
                      style={{ marginRight: 4 }}
                      title="LLM-curated AI Commander Reference generated at upload"
                    >
                      digest
                    </span>
                  )}
                  <span
                    className={`wg-badge ${isImage ? "b-accent" : "b-mono"}`}
                    style={{ marginRight: 4 }}
                  >
                    {isImage ? "ref image" : "rules"}
                  </span>
                  {!isImage && onRegenerateDigest && (
                    <button
                      className="wg-btn wg-btn-ghost wg-btn-sm"
                      onClick={() => handleRegenerate(s.name)}
                      disabled={regenerating || uploading}
                      title="Regenerate the LLM digest from the full rulebook (~$0.05, ~90s)"
                      style={{ marginRight: 2 }}
                    >
                      {regenerating ? "…" : (
                        <Icon name="refresh" className="wg-icon-sm" />
                      )}
                    </button>
                  )}
                  <button
                    className="wg-btn wg-btn-ghost wg-btn-sm"
                    onClick={() => onDelete(s.kind, s.name)}
                    title="Remove from sources"
                  >
                    <Icon name="x" className="wg-icon-sm" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
        <div
          className="wg-dropzone compact"
          onClick={() => !uploading && inputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            if (!uploading) pick(e.dataTransfer.files);
          }}
          style={{ cursor: uploading ? "wait" : "pointer", opacity: uploading ? 0.6 : 1 }}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.md,.markdown,.txt,.jpg,.jpeg,.png,.webp,.gif"
            multiple
            style={{ display: "none" }}
            onChange={(e) => {
              pick(e.target.files);
              e.target.value = "";
            }}
          />
          <span className="wg-dz-icon" style={{ width: 28, height: 28 }}>
            <Icon name="sheet" className="wg-icon-sm" />
          </span>
          <div className="wg-dz-prompt" style={{ alignItems: "baseline" }}>
            <div>
              <div>
                <b>{uploading ? "Converting…" : "Drop a source"}</b>{" "}
                <span
                  style={{ color: "hsl(var(--muted-foreground))", fontWeight: 400 }}
                >
                  · PDF rulebook (auto-converted) · .md / .txt · or reference image (.jpg / .png)
                </span>
              </div>
              <div style={{ fontSize: 11.5, color: "hsl(var(--muted-foreground))" }}>
                Persists with the campaign — every turn's orders ground in
                these sources. Reference images (map, counter sheet, TEC) get
                attached to every API call.
              </div>
            </div>
          </div>
          <span className="wg-badge b-mono" style={{ marginLeft: "auto" }}>
            .pdf / .md / .img
          </span>
        </div>
        {error && (
          <div style={{ color: "hsl(0 70% 45%)", fontSize: 12 }}>{error}</div>
        )}
      </div>
    </div>
  );
}

// ── OOB sheet dropzone ───────────────────────────────────
interface SheetDropzoneProps {
  file: File | null;
  onChange: (file: File | null) => void;
}

export function SheetDropzone({ file, onChange }: SheetDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  function pick(list: FileList | null) {
    if (!list || !list.length) return;
    const f = list[0];
    if (
      f.name.toLowerCase().endsWith(".xlsx") ||
      f.name.toLowerCase().endsWith(".xlsm")
    ) {
      onChange(f);
    }
  }

  if (file) {
    return (
      <div className="wg-sheet-preview">
        <span className="sp-icon">
          <Icon name="sheet" className="wg-icon-sm" />
        </span>
        <div style={{ flex: 1 }}>
          <div className="sp-name">{file.name}</div>
          <div className="sp-cols">
            uploaded ·{" "}
            <b style={{ color: "hsl(var(--foreground))" }}>
              {(file.size / 1024).toFixed(1)} KB
            </b>{" "}
            · parsed server-side per turn
          </div>
        </div>
        <span className="wg-badge b-accent">.xlsx</span>
        <button
          className="wg-btn wg-btn-ghost wg-btn-sm"
          onClick={() => onChange(null)}
        >
          <Icon name="x" className="wg-icon-sm" />
        </button>
      </div>
    );
  }
  return (
    <div
      className="wg-dropzone compact"
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        pick(e.dataTransfer.files);
      }}
      style={{ cursor: "pointer" }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx,.xlsm"
        style={{ display: "none" }}
        onChange={(e) => {
          pick(e.target.files);
          e.target.value = "";
        }}
      />
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
  error?: string | null;
}

export function IssueRow({ enabled, state, onIssue, tokens, error }: IssueRowProps) {
  // Sonnet 4.6 OpenRouter pricing: ~$6.50/M input, ~$22.50/M output
  const cost = (tokens / 1000) * 6.5e-3 + (612 / 1000) * 22.5e-3;
  if (state === "streaming") {
    return (
      <div className="wg-issue-row">
        <div className="wg-issue-cost">
          <span>issuing orders</span>
          <span className="wg-streaming-meta">
            <span className="wg-spinner" /> waiting on hp_vision.py
          </span>
        </div>
        <button className="wg-btn wg-issue-btn" disabled style={{ marginLeft: "auto" }}>
          <Icon name="swords" /> Awaiting orders…
        </button>
      </div>
    );
  }
  return (
    <div className="wg-issue-row" style={{ flexWrap: "wrap" }}>
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
      {error && (
        <div
          style={{
            flexBasis: "100%",
            color: "hsl(0 70% 45%)",
            fontSize: 11.5,
            marginTop: 4,
          }}
        >
          {error}
        </div>
      )}
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
        <div className="wg-tc-model">
          <Icon name="info" className="wg-icon-sm" /> {entry.model}
        </div>
      </div>
    </div>
  );
}
