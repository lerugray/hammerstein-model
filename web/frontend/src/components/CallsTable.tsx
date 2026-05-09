import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, Image as ImageIcon, Search, Sheet, Swords } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { cn, formatCost, formatLatency, formatTimestamp, truncate } from "@/lib/utils";
import type { Call } from "@/types";

type SortKey = "timestamp" | "label" | "tokens" | "cost_usd" | "latency_ms";
type SortDir = "asc" | "desc";

interface Props {
  calls: Call[];
  onSelect: (call: Call) => void;
  onToggle: (call: Call, value: boolean) => Promise<void>;
  pendingTimestamp: string | null;
}

export function CallsTable({ calls, onSelect, onToggle, pendingTimestamp }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("timestamp");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [filter, setFilter] = useState("");

  const sorted = useMemo(() => {
    const filtered = filter.trim()
      ? calls.filter((c) => {
          const q = filter.toLowerCase();
          return (
            (c.query || "").toLowerCase().includes(q) ||
            (c.label || "").toLowerCase().includes(q) ||
            (c.response || "").toLowerCase().includes(q)
          );
        })
      : calls;

    const sign = sortDir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * sign;
      return String(av).localeCompare(String(bv)) * sign;
    });
  }, [calls, sortKey, sortDir, filter]);

  function toggleSort(k: SortKey) {
    if (k === sortKey) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else {
      setSortKey(k);
      setSortDir("desc");
    }
  }

  function HeaderCell({ k, label, className }: { k: SortKey; label: string; className?: string }) {
    const Icon = sortKey === k ? (sortDir === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
    return (
      <th
        scope="col"
        className={cn("text-left px-3 py-2 font-medium text-muted-foreground select-none", className)}
      >
        <button
          type="button"
          onClick={() => toggleSort(k)}
          className="inline-flex items-center gap-1 hover:text-foreground transition-colors"
        >
          {label}
          <Icon className="h-3 w-3" />
        </button>
      </th>
    );
  }

  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      <div className="flex items-center justify-between gap-3 p-3 border-b">
        <div className="relative w-72 max-w-full">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter by query / template / response…"
            className="w-full rounded-md border bg-background pl-8 pr-3 py-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </div>
        <div className="text-xs text-muted-foreground">
          {sorted.length} of {calls.length} calls
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-muted/40">
            <tr>
              <HeaderCell k="timestamp" label="When" className="whitespace-nowrap" />
              <HeaderCell k="label" label="Kind / Template" />
              <th scope="col" className="text-left px-3 py-2 font-medium text-muted-foreground">Query</th>
              <HeaderCell k="tokens" label="Tokens" className="text-right" />
              <HeaderCell k="cost_usd" label="Cost" className="text-right" />
              <HeaderCell k="latency_ms" label="Latency" className="text-right" />
              <th scope="col" className="text-center px-3 py-2 font-medium text-muted-foreground whitespace-nowrap">
                Changed conclusion?
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center py-12 text-muted-foreground">
                  {filter ? "No calls match the filter." : "No hp calls logged yet."}
                </td>
              </tr>
            ) : (
              sorted.map((c) => (
                <tr
                  key={c.timestamp}
                  className="border-t hover:bg-muted/30 cursor-pointer transition-colors"
                  onClick={() => onSelect(c)}
                >
                  <td className="px-3 py-2 whitespace-nowrap text-xs font-mono text-muted-foreground">
                    {formatTimestamp(c.timestamp)}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <div className="flex flex-col gap-1 items-start">
                      {c.kind === "vision" ? (
                        <Badge variant="default" className="text-[10px] gap-1">
                          <Swords className="h-3 w-3" />
                          wargame
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="text-[10px]">
                          audit
                        </Badge>
                      )}
                      <span className="text-[10px] font-mono text-muted-foreground max-w-[14rem] truncate">
                        {c.label || "—"}
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-2 max-w-xl">
                    <div className="text-foreground">{truncate(c.query, 110)}</div>
                    <CallSubline call={c} />
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {c.tokens}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {formatCost(c.cost_usd)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {formatLatency(c.latency_ms)}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <Switch
                      checked={c.conclusion_changed === true}
                      disabled={pendingTimestamp === c.timestamp}
                      onCheckedChange={(next) => onToggle(c, next)}
                      ariaLabel="Mark conclusion changed"
                    />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CallSubline({ call }: { call: Call }) {
  if (call.kind === "vision") {
    const imgs = call.image_count ?? call.images.length;
    const xls = call.xlsx_count ?? call.xlsx.length;
    if (imgs === 0 && xls === 0 && !call.state_dir) return null;
    return (
      <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2 flex-wrap">
        {imgs > 0 ? (
          <span className="inline-flex items-center gap-1">
            <ImageIcon className="h-3 w-3" />
            {imgs} image{imgs === 1 ? "" : "s"}
          </span>
        ) : null}
        {xls > 0 ? (
          <span className="inline-flex items-center gap-1">
            <Sheet className="h-3 w-3" />
            {xls} xlsx
          </span>
        ) : null}
        {call.state_dir ? <span className="font-mono">{call.state_dir}</span> : null}
      </div>
    );
  }
  const ids = call.matched_prior_corpus_ids;
  const n = call.injected_prior_count ?? 0;
  return (
    <div className="text-xs text-muted-foreground mt-0.5">
      {n} prior{n === 1 ? "" : "s"}
      {ids.length ? ` · corpus IDs ${ids.join(", ")}` : ""}
    </div>
  );
}
