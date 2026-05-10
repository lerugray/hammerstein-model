// WargamePage — wargamer surface, API-driven against /api/wargame/*.
// Originally a port of the Claude Design prototype (which shipped with
// static fixtures); now wired live to hp_vision.py through the FastAPI
// backend in web/backend/wargame_api.py.

import { useCallback, useEffect, useMemo, useState } from "react";
import "./wargame.css";
import { Icon } from "./Icon";
import {
  CampaignPicker,
  ImageDropzone,
  IssueRow,
  SheetDropzone,
  SourcesPanel,
  StatusTextarea,
  TopBar,
  TurnCard,
  type ActiveTab,
  type Phase,
} from "./components";
import { NewCampaignModal, OrdersPanel, ShareModal } from "./OrdersPanel";
import {
  wargameApi,
  type Campaign,
  type CampaignDetail,
  type IssueResponse,
  type Source,
  type SourceKind,
} from "./api";

interface Props {
  activeTab: ActiveTab;
  onSwitchTab: (tab: ActiveTab) => void;
  dark: boolean;
  onToggleDark: () => void;
}

const STORAGE_ACTIVE_SLUG = "hp-web-wargame-active-slug";

export function WargamePage({ activeTab, onSwitchTab, dark, onToggleDark }: Props) {
  // Campaign discovery + selection
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [activeSlug, setActiveSlug] = useState<string | null>(() =>
    typeof window !== "undefined" ? localStorage.getItem(STORAGE_ACTIVE_SLUG) : null,
  );
  const [detail, setDetail] = useState<CampaignDetail | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Form inputs
  const [status, setStatus] = useState("");
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [xlsxFile, setXlsxFile] = useState<File | null>(null);

  // Issue state
  const [issuing, setIssuing] = useState(false);
  const [issueError, setIssueError] = useState<string | null>(null);
  const [lastIssue, setLastIssue] = useState<IssueResponse | null>(null);

  // Sources state (rulebooks + reference images, both kinds)
  const [sources, setSources] = useState<Source[]>([]);
  const [sourcesUploading, setSourcesUploading] = useState(false);
  const [sourcesError, setSourcesError] = useState<string | null>(null);

  // Dev / display
  const [devPhase, setDevPhase] = useState<Phase | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [modal, setModal] = useState<"share" | "new" | null>(null);
  const [serif, setSerif] = useState(false);

  // ── Load campaigns on mount ───────────────────────────────
  const reloadList = useCallback(async () => {
    try {
      const list = await wargameApi.list();
      setCampaigns(list);
      setListError(null);
      // Pick: stored slug if present in list, else first.
      if (list.length === 0) {
        setActiveSlug(null);
      } else if (!activeSlug || !list.find((c) => c.slug === activeSlug)) {
        setActiveSlug(list[0].slug);
      }
    } catch (e) {
      setListError(String(e));
    }
  }, [activeSlug]);

  useEffect(() => {
    reloadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Load detail + sources when activeSlug changes ────────
  useEffect(() => {
    if (!activeSlug) {
      setDetail(null);
      setSources([]);
      return;
    }
    localStorage.setItem(STORAGE_ACTIVE_SLUG, activeSlug);
    let cancelled = false;
    setDetailError(null);
    setSourcesError(null);
    Promise.all([wargameApi.get(activeSlug), wargameApi.listSources(activeSlug)])
      .then(([d, s]) => {
        if (cancelled) return;
        setDetail(d);
        setSources(s);
        setLastIssue(null);
        setIssueError(null);
        const top = d.turn_log[0];
        setExpanded(top ? top.turn : null);
      })
      .catch((e) => {
        if (!cancelled) setDetailError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [activeSlug]);

  // ── Sources upload + delete handlers ─────────────────────
  const handleSourcesUpload = useCallback(
    async (files: File[]) => {
      if (!activeSlug) return;
      setSourcesUploading(true);
      setSourcesError(null);
      try {
        const resp = await wargameApi.uploadSources(activeSlug, files);
        setSources(resp.sources);
        if (resp.errors.length > 0) {
          setSourcesError(
            resp.errors.map((e) => `${e.file}: ${e.error}`).join("; "),
          );
        }
      } catch (e) {
        setSourcesError(String(e));
      } finally {
        setSourcesUploading(false);
      }
    },
    [activeSlug],
  );

  const handleSourcesDelete = useCallback(
    async (kind: SourceKind, name: string) => {
      if (!activeSlug) return;
      try {
        const resp = await wargameApi.deleteSource(activeSlug, kind, name);
        setSources(resp.sources);
        setSourcesError(null);
      } catch (e) {
        setSourcesError(String(e));
      }
    },
    [activeSlug],
  );

  const handleRegenerateDigest = useCallback(
    async (name: string) => {
      if (!activeSlug) return;
      setSourcesError(null);
      try {
        const resp = await wargameApi.regenerateDigest(activeSlug, name);
        setSources(resp.sources);
      } catch (e) {
        setSourcesError(String(e));
      }
    },
    [activeSlug],
  );

  // ── Derived: active campaign + orders + turn-log ──────────
  const activeCampaign: Campaign | null =
    lastIssue?.campaign ?? detail?.campaign ?? null;
  const orders = lastIssue?.orders ?? detail?.last_orders ?? null;
  const turnLog = detail?.turn_log ?? [];

  // ── Phase derivation (auto unless dev override) ───────────
  const hasInputs = status.trim().length > 0 || imageFiles.length > 0 || xlsxFile !== null;
  const autoPhase: Phase = issuing
    ? "streaming"
    : orders
      ? "completed"
      : hasInputs
        ? "drafting"
        : "empty";
  const phase: Phase = devPhase ?? autoPhase;

  // ── Cost preview (rough) ──────────────────────────────────
  const tokens = useMemo(() => {
    // Match the heuristic the original prototype showed: ~4180 base
    // (system + state preamble) + status length / 4. Real numbers come
    // back from the API after issuing.
    return Math.round(4180 + status.length / 4);
  }, [status]);

  // ── Issue handler ─────────────────────────────────────────
  const handleIssue = useCallback(async () => {
    if (!activeSlug) return;
    setIssuing(true);
    setIssueError(null);
    setDevPhase(null);
    try {
      const resp = await wargameApi.issue(activeSlug, status, imageFiles, xlsxFile);
      setLastIssue(resp);
      setDetail((d) =>
        d
          ? {
              ...d,
              campaign: resp.campaign,
              turn_log: [
                resp.turn_log_entry,
                ...d.turn_log.map((e) => ({ ...e, current: false })),
              ],
              last_orders: resp.orders,
            }
          : d,
      );
      setCampaigns((cs) =>
        cs.map((c) => (c.slug === resp.campaign.slug ? resp.campaign : c)),
      );
      setStatus("");
      setImageFiles([]);
      setXlsxFile(null);
      setExpanded(resp.turn_log_entry.turn);
    } catch (e) {
      setIssueError(String(e));
    } finally {
      setIssuing(false);
    }
  }, [activeSlug, status, imageFiles, xlsxFile]);

  // ── New campaign ──────────────────────────────────────────
  const handleCreate = useCallback(
    async (body: { name: string; mission_md: string }) => {
      const resp = await wargameApi.create(body);
      setCampaigns((cs) => {
        if (cs.find((c) => c.slug === resp.campaign.slug)) return cs;
        return [...cs, resp.campaign];
      });
      setActiveSlug(resp.campaign.slug);
    },
    [],
  );

  // ── Render ────────────────────────────────────────────────
  return (
    <div className="wargame-page">
      <div className="wg-app">
        <TopBar
          dark={dark}
          onToggleDark={onToggleDark}
          spend={activeCampaign?.spend ?? 0}
          spendBudget={activeCampaign?.spend_budget ?? 1.2}
          activeTab={activeTab}
          onSwitchTab={onSwitchTab}
          onReload={() => activeSlug && wargameApi.get(activeSlug).then(setDetail).catch(() => {})}
        />

        <main className="wg-workspace">
          <div className="wg-campaign-bar">
            <CampaignPicker
              campaigns={campaigns}
              active={activeCampaign}
              onSelect={(slug) => setActiveSlug(slug)}
              onNew={() => setModal("new")}
            />
            {listError && (
              <span style={{ marginLeft: 12, color: "hsl(0 70% 45%)", fontSize: 12 }}>
                campaign list error: {listError}
              </span>
            )}
            {detailError && (
              <span style={{ marginLeft: 12, color: "hsl(0 70% 45%)", fontSize: 12 }}>
                detail error: {detailError}
              </span>
            )}
          </div>

          {activeSlug && (
            <SourcesPanel
              slug={activeSlug}
              sources={sources}
              uploading={sourcesUploading}
              error={sourcesError}
              onUpload={handleSourcesUpload}
              onDelete={handleSourcesDelete}
              onRegenerateDigest={handleRegenerateDigest}
            />
          )}

          <div className="wg-cols">
            {/* ── left column: turn input ─────────────────────── */}
            <div className="wg-card">
              <div className="wg-card-hd">
                <span>
                  Turn {(activeCampaign?.turn ?? 0) + 1} input
                </span>
                <span
                  className="hd-r"
                  style={{ color: "hsl(var(--muted-foreground))", fontSize: 11.5 }}
                >
                  <Icon name="history" className="wg-icon-sm" />
                  <span>
                    last issued{" "}
                    <b style={{ color: "hsl(var(--foreground))" }}>
                      {turnLog[0]?.time ?? "—"}
                    </b>
                    {turnLog[0] ? ` · turn ${turnLog[0].turn}` : ""}
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
                  <ImageDropzone
                    files={imageFiles}
                    onChange={setImageFiles}
                    active={phase === "drafting"}
                  />
                </div>
                <div>
                  <div className="wg-form-label">
                    <b>Order of battle</b>
                    <span>spreadsheet</span>
                  </div>
                  <SheetDropzone file={xlsxFile} onChange={setXlsxFile} />
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
                  enabled={!!activeSlug && hasInputs && !issuing}
                  state={phase}
                  tokens={tokens}
                  onIssue={handleIssue}
                  error={issueError}
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
                  {turnLog.length} turn{turnLog.length === 1 ? "" : "s"}
                </span>
              </div>
              <div className="wg-turnlog-bd">
                {turnLog.length === 0 ? (
                  <div
                    style={{
                      padding: 20,
                      textAlign: "center",
                      fontSize: 12,
                      color: "hsl(var(--muted-foreground))",
                    }}
                  >
                    No turns yet. Issue your first orders to seed the log.
                  </div>
                ) : (
                  turnLog.map((entry) => (
                    <TurnCard
                      key={entry.turn}
                      entry={entry}
                      expanded={expanded === entry.turn}
                      onToggle={() =>
                        setExpanded(expanded === entry.turn ? null : entry.turn)
                      }
                    />
                  ))
                )}
                {activeCampaign && (
                  <div
                    style={{
                      fontSize: 11,
                      color: "hsl(var(--muted-foreground))",
                      textAlign: "center",
                      padding: "6px 0 2px",
                    }}
                  >
                    campaign began{" "}
                    <b style={{ color: "hsl(var(--foreground))" }}>
                      {activeCampaign.started || "—"}
                    </b>
                  </div>
                )}
              </div>
            </aside>
          </div>

          {/* ── orders panel ───────────────────────────────────── */}
          <OrdersPanel
            data={orders}
            campaign={activeCampaign}
            serif={serif}
            state={phase}
            onShare={() => setModal("share")}
            meta={
              lastIssue
                ? {
                    issuedAt: lastIssue.turn_log_entry.time,
                    costUsd: lastIssue.cost_usd,
                    latencyMs: lastIssue.latency_ms,
                  }
                : undefined
            }
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
              phase override
              {(["empty", "drafting", "streaming", "completed"] as Phase[]).map((p) => (
                <button
                  key={p}
                  className="wg-btn wg-btn-sm"
                  style={{
                    background:
                      devPhase === p ? "hsl(var(--secondary))" : "hsl(var(--card))",
                    color:
                      devPhase === p
                        ? "hsl(var(--secondary-foreground))"
                        : "hsl(var(--muted-foreground))",
                    borderColor: devPhase === p ? "hsl(var(--secondary))" : undefined,
                  }}
                  onClick={() => setDevPhase(devPhase === p ? null : p)}
                >
                  {p}
                </button>
              ))}
              <button
                className="wg-btn wg-btn-sm"
                style={{ marginLeft: 4 }}
                onClick={() => setDevPhase(null)}
              >
                clear
              </button>
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
              backend: <code>hp_vision.py</code> · phase auto:{" "}
              <code>{autoPhase}</code>
              {devPhase ? ` · override → ${devPhase}` : ""}
            </span>
          </div>
        </main>
      </div>

      {modal === "share" && (
        <ShareModal
          onClose={() => setModal(null)}
          campaign={activeCampaign}
          data={orders}
        />
      )}
      {modal === "new" && (
        <NewCampaignModal
          onClose={() => setModal(null)}
          onCreate={handleCreate}
        />
      )}
    </div>
  );
}
