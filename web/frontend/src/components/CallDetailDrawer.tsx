import { useEffect } from "react";
import { Image as ImageIcon, Sheet, Swords, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { formatCost, formatLatency, formatTimestamp } from "@/lib/utils";
import type { Call } from "@/types";

interface Props {
  call: Call | null;
  onClose: () => void;
}

export function CallDetailDrawer({ call, onClose }: Props) {
  useEffect(() => {
    if (!call) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [call, onClose]);

  if (!call) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      <div
        className="flex-1 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside className="w-full max-w-2xl bg-background shadow-2xl border-l flex flex-col">
        <header className="flex items-center justify-between gap-3 p-4 border-b shrink-0">
          <div className="min-w-0">
            <div className="text-xs font-mono text-muted-foreground">
              {formatTimestamp(call.timestamp)}
            </div>
            <h2 className="text-base font-semibold truncate flex items-center gap-2">
              {call.kind === "vision" ? (
                <Badge variant="default" className="gap-1">
                  <Swords className="h-3 w-3" />
                  wargame
                </Badge>
              ) : (
                <Badge variant="secondary">audit</Badge>
              )}
              <span className="font-mono text-xs text-muted-foreground truncate">
                {call.label || "—"}
              </span>
            </h2>
          </div>
          <Button size="icon" variant="ghost" onClick={onClose} aria-label="Close">
            <X className="h-5 w-5" />
          </Button>
        </header>

        <div className="overflow-y-auto p-4 space-y-5">
          <Section title={call.kind === "vision" ? "Status report" : "Query"}>
            <pre className="whitespace-pre-wrap text-sm font-sans">{call.query}</pre>
          </Section>

          <div className="grid grid-cols-3 gap-3">
            <Stat label="Cost" value={formatCost(call.cost_usd)} />
            <Stat label="Latency (model)" value={formatLatency(call.latency_ms)} />
            <Stat
              label={call.kind === "vision" ? "Wall clock" : "Wrapper"}
              value={formatLatency(call.wrapper_elapsed_ms ?? call.latency_ms)}
            />
            <Stat label="Preamble tokens" value={String(call.tokens)} />
            {call.kind === "audit" ? (
              <Stat label="Priors injected" value={String(call.injected_prior_count ?? 0)} />
            ) : (
              <Stat
                label="Attachments"
                value={`${call.image_count ?? call.images.length} img · ${call.xlsx_count ?? call.xlsx.length} xlsx`}
              />
            )}
            <Stat
              label="Conclusion changed"
              value={
                call.conclusion_changed === true
                  ? "yes"
                  : call.conclusion_changed === false
                    ? "no"
                    : "—"
              }
            />
          </div>

          {call.kind === "audit" ? (
            <Section title="Corpus IDs">
              <div className="flex flex-wrap gap-4 text-xs">
                <Block label="New query" ids={call.new_query_corpus_ids} />
                <Block label="Matched prior" ids={call.matched_prior_corpus_ids} />
              </div>
            </Section>
          ) : (
            <Section title="Inputs">
              <div className="space-y-2 text-xs">
                {call.state_dir ? (
                  <div>
                    <span className="text-muted-foreground">state-dir:</span>{" "}
                    <code className="font-mono">{call.state_dir}</code>
                  </div>
                ) : null}
                {call.images.length ? (
                  <div>
                    <div className="flex items-center gap-1 text-muted-foreground mb-1">
                      <ImageIcon className="h-3 w-3" />
                      images
                    </div>
                    <ul className="font-mono text-[11px] space-y-0.5">
                      {call.images.map((p) => (
                        <li key={p} className="break-all">{p}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {call.xlsx.length ? (
                  <div>
                    <div className="flex items-center gap-1 text-muted-foreground mb-1">
                      <Sheet className="h-3 w-3" />
                      xlsx
                    </div>
                    <ul className="font-mono text-[11px] space-y-0.5">
                      {call.xlsx.map((p) => (
                        <li key={p} className="break-all">{p}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {!call.state_dir && !call.images.length && !call.xlsx.length ? (
                  <span className="text-muted-foreground">No attachments.</span>
                ) : null}
              </div>
            </Section>
          )}

          <Section title={call.kind === "vision" ? "Orders" : "Response"}>
            <pre className="whitespace-pre-wrap text-sm font-sans leading-relaxed">
              {call.response}
            </pre>
          </Section>
        </div>
      </aside>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-2">
        {title}
      </h3>
      <div className="rounded-md border bg-muted/30 p-3">{children}</div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-card p-3">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-base font-mono mt-0.5">{value}</div>
    </div>
  );
}

function Block({ label, ids }: { label: string; ids: number[] }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">{label}</div>
      <div className="flex flex-wrap gap-1">
        {ids.length === 0 ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          ids.map((id) => (
            <Badge key={id} variant="secondary" className="font-mono">
              #{id}
            </Badge>
          ))
        )}
      </div>
    </div>
  );
}
