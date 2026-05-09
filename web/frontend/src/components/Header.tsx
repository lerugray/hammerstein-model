import { Moon, Sun, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Tab = "dashboard" | "wargame";

interface Props {
  onRefresh: () => void;
  refreshing: boolean;
  dark: boolean;
  onToggleDark: () => void;
  activeTab: Tab;
  onSwitchTab: (tab: Tab) => void;
}

export function Header({ onRefresh, refreshing, dark, onToggleDark, activeTab, onSwitchTab }: Props) {
  return (
    <header className="border-b bg-background/95 backdrop-blur sticky top-0 z-30">
      <div className="container mx-auto flex items-center justify-between gap-3 py-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="h-8 w-8 rounded-md bg-primary text-primary-foreground grid place-items-center font-bold font-mono">
            hp
          </div>
          <div className="min-w-0">
            <h1 className="text-base font-semibold leading-none">Hammerstein Persistent</h1>
            <p className="text-xs text-muted-foreground mt-1">
              Local-only · reads <code className="font-mono">~/.hammerstein/logs</code>
            </p>
          </div>
          <nav className="ml-3 flex items-center gap-1">
            <TabButton active={activeTab === "dashboard"} onClick={() => onSwitchTab("dashboard")}>
              Dashboard
            </TabButton>
            <TabButton active={activeTab === "wargame"} onClick={() => onSwitchTab("wargame")}>
              Wargame
            </TabButton>
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onRefresh}
            disabled={refreshing}
            aria-label="Refresh"
          >
            <RefreshCw className={refreshing ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleDark}
            aria-label="Toggle theme"
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </header>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "px-2.5 py-1.5 text-xs font-medium rounded-md transition-colors",
        active
          ? "bg-secondary text-secondary-foreground"
          : "text-muted-foreground hover:text-foreground hover:bg-muted/50",
      )}
    >
      {children}
    </button>
  );
}
