import type { ReactNode } from "react";
import { CheckCircle2, AlertTriangle, XOctagon, HelpCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { GateStatus, Status, Verdict } from "@/types";

const VERDICT_STYLES: Record<Verdict, { ring: string; pill: string; icon: ReactNode; blurb: string }> = {
  CONTINUE: {
    ring: "ring-success/40 bg-success/5",
    pill: "bg-success text-success-foreground",
    icon: <CheckCircle2 className="h-6 w-6" />,
    blurb: "All Phase-3 gates pass. The wrapper is earning its weight.",
  },
  EXTEND: {
    ring: "ring-warning/40 bg-warning/5",
    pill: "bg-warning text-warning-foreground",
    icon: <AlertTriangle className="h-6 w-6" />,
    blurb: "Within 10% of a threshold. Watch closely; one more drift and it abort-gates.",
  },
  ABORT: {
    ring: "ring-destructive/40 bg-destructive/5",
    pill: "bg-destructive text-destructive-foreground",
    icon: <XOctagon className="h-6 w-6" />,
    blurb: "A gate is breached. The wrapper is not earning its weight on this dimension.",
  },
};

const GATE_LABELS: Record<string, string> = {
  cost_ratio: "Cost ratio",
  conclusion_changed: "conclusion_changed in last 5",
  maintenance_hours: "Maintenance hours (7d)",
};

const GATE_BADGE: Record<GateStatus, { variant: "success" | "warning" | "destructive" | "secondary"; label: string }> = {
  ok: { variant: "success", label: "OK" },
  warn: { variant: "warning", label: "WARN" },
  abort: { variant: "destructive", label: "ABORT" },
  unknown: { variant: "secondary", label: "INSUFFICIENT DATA" },
};

interface Props {
  status: Status;
}

export function VerdictCard({ status }: Props) {
  const style = VERDICT_STYLES[status.verdict];

  return (
    <Card className={cn("ring-2 transition-shadow", style.ring)}>
      <CardContent className="p-6">
        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div className="flex items-center gap-4 min-w-0">
            <div className={cn("flex items-center gap-2 rounded-full px-4 py-2 font-bold tracking-wide", style.pill)}>
              {style.icon}
              <span className="text-lg">{status.verdict}</span>
            </div>
            <div className="min-w-0">
              <p className="text-sm text-muted-foreground">{style.blurb}</p>
              <p className="text-xs text-muted-foreground mt-1">
                Window: last {status.window_days} days · {status.hp_calls_in_window} hp calls ·{" "}
                {status.baseline_calls_in_window} baseline calls
              </p>
            </div>
          </div>
        </div>

        <div className="mt-6 grid gap-3 grid-cols-1 md:grid-cols-3">
          {status.gates.map((g) => {
            const badge = GATE_BADGE[g.status];
            return (
              <div
                key={g.name}
                className="rounded-md border p-3 bg-card flex flex-col gap-1"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    {GATE_LABELS[g.name] ?? g.name}
                  </div>
                  <Badge variant={badge.variant} className="text-[10px]">
                    {g.status === "unknown" ? <HelpCircle className="mr-1 h-3 w-3" /> : null}
                    {badge.label}
                  </Badge>
                </div>
                <div className="text-2xl font-mono">
                  {g.value == null ? "—" : g.value}
                  <span className="text-sm text-muted-foreground ml-1">
                    / {g.threshold}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground">{g.detail}</div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
