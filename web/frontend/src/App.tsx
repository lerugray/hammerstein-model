import { useCallback, useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Header } from "@/components/Header";
import { VerdictCard } from "@/components/VerdictCard";
import { CallsTable } from "@/components/CallsTable";
import { CallDetailDrawer } from "@/components/CallDetailDrawer";
import { WargamePage } from "@/wargame/WargamePage";
import { api } from "@/api";
import type { Call, Status } from "@/types";

type Tab = "dashboard" | "wargame";

function App() {
  const [tab, setTab] = useState<Tab>(() => {
    if (typeof window === "undefined") return "dashboard";
    const stored = localStorage.getItem("hp-web-tab");
    return stored === "wargame" ? "wargame" : "dashboard";
  });
  const [dark, setDark] = useState(() => {
    if (typeof window === "undefined") return false;
    const saved = localStorage.getItem("hp-web-theme");
    if (saved) return saved === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("hp-web-theme", dark ? "dark" : "light");
  }, [dark]);

  useEffect(() => {
    localStorage.setItem("hp-web-tab", tab);
  }, [tab]);

  if (tab === "wargame") {
    return (
      <WargamePage
        activeTab={tab}
        onSwitchTab={setTab}
        dark={dark}
        onToggleDark={() => setDark((v) => !v)}
      />
    );
  }

  return (
    <DashboardPage
      activeTab={tab}
      onSwitchTab={setTab}
      dark={dark}
      onToggleDark={() => setDark((v) => !v)}
    />
  );
}

interface PageProps {
  activeTab: Tab;
  onSwitchTab: (tab: Tab) => void;
  dark: boolean;
  onToggleDark: () => void;
}

function DashboardPage({ activeTab, onSwitchTab, dark, onToggleDark }: PageProps) {
  const [status, setStatus] = useState<Status | null>(null);
  const [calls, setCalls] = useState<Call[]>([]);
  const [selected, setSelected] = useState<Call | null>(null);
  const [pendingTimestamp, setPendingTimestamp] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, c] = await Promise.all([api.status(), api.calls(200, 0)]);
      setStatus(s);
      setCalls(c.rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const onToggle = useCallback(
    async (call: Call, value: boolean) => {
      setPendingTimestamp(call.timestamp);
      const previous = call.conclusion_changed;
      setCalls((prev) =>
        prev.map((c) =>
          c.timestamp === call.timestamp ? { ...c, conclusion_changed: value } : c,
        ),
      );
      try {
        await api.setConclusionChanged(call.timestamp, value);
        const s = await api.status();
        setStatus(s);
      } catch (e) {
        setCalls((prev) =>
          prev.map((c) =>
            c.timestamp === call.timestamp ? { ...c, conclusion_changed: previous } : c,
          ),
        );
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setPendingTimestamp(null);
      }
    },
    [],
  );

  return (
    <div className="min-h-screen flex flex-col">
      <Header
        onRefresh={refresh}
        refreshing={loading}
        dark={dark}
        onToggleDark={onToggleDark}
        activeTab={activeTab}
        onSwitchTab={onSwitchTab}
      />
      <main className="container mx-auto py-6 space-y-6 flex-1">
        {error ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <div>
              <div className="font-semibold">Couldn't load data</div>
              <div className="font-mono text-xs mt-1">{error}</div>
            </div>
          </div>
        ) : null}

        {status ? <VerdictCard status={status} /> : <SkeletonCard />}

        <section>
          <div className="flex items-baseline justify-between mb-3 px-1">
            <h2 className="text-base font-semibold">Recent hp calls</h2>
            <p className="text-xs text-muted-foreground">
              Click a row for the full query / response. Toggle the switch when an audit
              actually changed your conclusion.
            </p>
          </div>
          <CallsTable
            calls={calls}
            onSelect={setSelected}
            onToggle={onToggle}
            pendingTimestamp={pendingTimestamp}
          />
        </section>
      </main>

      <footer className="border-t py-4 text-center text-xs text-muted-foreground">
        hp-web · binds to 127.0.0.1 only · CLI remains source of truth
      </footer>

      <CallDetailDrawer call={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function SkeletonCard() {
  return <div className="rounded-lg border bg-card h-48 animate-pulse" />;
}

export default App;
