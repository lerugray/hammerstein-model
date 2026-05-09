import { useEffect, useState } from "react";
import { Moon, Sun, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  onRefresh: () => void;
  refreshing: boolean;
}

export function Header({ onRefresh, refreshing }: Props) {
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

  return (
    <header className="border-b bg-background/95 backdrop-blur sticky top-0 z-30">
      <div className="container mx-auto flex items-center justify-between gap-3 py-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="h-8 w-8 rounded-md bg-primary text-primary-foreground grid place-items-center font-bold font-mono">
            hp
          </div>
          <div className="min-w-0">
            <h1 className="text-base font-semibold leading-none">Hammerstein Persistent — dashboard</h1>
            <p className="text-xs text-muted-foreground mt-1">
              Local-only · reads <code className="font-mono">~/.hammerstein/logs</code>
            </p>
          </div>
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
            onClick={() => setDark((v) => !v)}
            aria-label="Toggle theme"
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </header>
  );
}
