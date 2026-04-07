import { useEffect, useState, useCallback } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { DashboardSidebar } from "@/components/DashboardSidebar";
import { Button } from "@/components/ui/button";
import { Sun, Moon, Keyboard, X, Type } from "lucide-react";

const SHORTCUTS = [
  { key: "S", description: "Ir para Scanner" },
  { key: "C", description: "Ir para Carteira" },
  { key: "M", description: "Ir para Macro" },
  { key: "?", description: "Abrir/fechar atalhos" },
  { key: "Esc", description: "Fechar modal" },
];

const DashboardLayout = () => {
  const navigate = useNavigate();
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    return (localStorage.getItem("alphacota-theme") as "dark" | "light") ?? "dark";
  });
  const [showHelp, setShowHelp] = useState(false);

  useEffect(() => {
    const html = document.documentElement;
    if (theme === "light") {
      html.classList.add("light");
    } else {
      html.classList.remove("light");
    }
    localStorage.setItem("alphacota-theme", theme);
  }, [theme]);

  const [density, setDensity] = useState<"compact" | "normal" | "large">(() => {
    return (localStorage.getItem("alphacota-density") as "compact" | "normal" | "large") ?? "normal";
  });

  useEffect(() => {
    const html = document.documentElement;
    if (density === "compact") html.style.fontSize = "14px";
    else if (density === "large") html.style.fontSize = "18px";
    else html.style.fontSize = "16px";
    localStorage.setItem("alphacota-density", density);
  }, [density]);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    // Ignore when typing in inputs/textareas/selects
    const tag = (e.target as HTMLElement).tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if ((e.target as HTMLElement).isContentEditable) return;

    switch (e.key) {
      case "s":
      case "S":
        navigate("/dashboard/scanner");
        break;
      case "c":
      case "C":
        navigate("/dashboard/portfolio");
        break;
      case "m":
      case "M":
        navigate("/dashboard/macro");
        break;
      case "?":
        setShowHelp(h => !h);
        break;
      case "Escape":
        setShowHelp(false);
        break;
    }
  }, [navigate]);

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full bg-gradient-dark">
        <DashboardSidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <header className="h-12 flex items-center border-b border-border/30 bg-background/50 backdrop-blur-xl px-4 sticky top-0 z-30">
            <SidebarTrigger className="mr-4" />
            <span className="font-mono text-xs text-muted-foreground">alphacota / dashboard</span>
            <div className="ml-auto flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => setShowHelp(h => !h)}
                title="Atalhos de teclado (?)"
              >
                <Keyboard className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => setDensity(d => d === "compact" ? "normal" : d === "normal" ? "large" : "compact")}
                title={`Densidade da Fonte (${density})`}
              >
                <Type className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => setTheme(t => t === "dark" ? "light" : "dark")}
                title={theme === "dark" ? "Modo claro" : "Modo escuro"}
              >
                {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </Button>
            </div>
          </header>
          <main className="flex-1 overflow-auto">
            <Outlet />
          </main>
        </div>

        {/* Keyboard shortcuts modal */}
        {showHelp && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={() => setShowHelp(false)}
          >
            <div
              className="bg-card border border-border rounded-xl p-6 w-80 shadow-2xl"
              onClick={e => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-semibold text-foreground flex items-center gap-2">
                  <Keyboard className="h-4 w-4 text-primary" />
                  Atalhos de teclado
                </h2>
                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setShowHelp(false)}>
                  <X className="h-3 w-3" />
                </Button>
              </div>
              <div className="space-y-2">
                {SHORTCUTS.map(s => (
                  <div key={s.key} className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">{s.description}</span>
                    <kbd className="px-2 py-0.5 rounded border border-border bg-muted font-mono text-xs text-foreground">
                      {s.key}
                    </kbd>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </SidebarProvider>
  );
};

export default DashboardLayout;
