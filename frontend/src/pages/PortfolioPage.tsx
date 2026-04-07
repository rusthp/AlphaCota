import { useState, useMemo, useRef, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  TrendingUp, TrendingDown, Wallet, DollarSign,
  PieChart as PieIcon, Plus, Trash2, User, Loader2, Shield, CalendarClock,
  Sliders, AlertTriangle, ChevronDown, ChevronUp, Download, FileBarChart, Receipt
} from "lucide-react";
import { fetchUpcomingDividends, type UpcomingDividendEvent, type RebalanceSuggestion } from "@/services/api";
import { Progress } from "@/components/ui/progress";
import { usePortfolio, calculateInvestorProfile } from "@/hooks/use-portfolio";
import { useScanner, useScoreAlerts } from "@/hooks/use-api";
import { motion, AnimatePresence } from "framer-motion";

const SEGMENT_COLORS: Record<string, string> = {
  "Logística": "hsl(173, 80%, 50%)",
  "Shopping": "hsl(145, 70%, 50%)",
  "Híbrido": "hsl(210, 70%, 55%)",
  "Lajes Corp.": "hsl(280, 60%, 55%)",
  "Papel (CRI)": "hsl(45, 80%, 55%)",
  "Fundo de Fundos": "hsl(30, 70%, 55%)",
  "Agro": "hsl(90, 60%, 50%)",
  "Saúde": "hsl(0, 60%, 55%)",
  "Residencial": "hsl(320, 50%, 55%)",
};

// ─── TickerCombobox ───────────────────────────────────────────────────────────

interface FIIOption { ticker: string; name: string; segment: string; }

function TickerCombobox({
  options,
  value,
  onChange,
  placeholder = "Ticker (ex: HGLG11)",
}: {
  options: FIIOption[];
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(value);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Sync external value → local query when cleared externally
  useEffect(() => {
    if (value === "") setQuery("");
  }, [value]);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options.slice(0, 20); // show top 20 when empty
    return options
      .filter((o) => o.ticker.toLowerCase().includes(q) || o.name.toLowerCase().includes(q))
      .slice(0, 20);
  }, [options, query]);

  const select = useCallback((ticker: string) => {
    setQuery(ticker);
    onChange(ticker);
    setOpen(false);
  }, [onChange]);

  const handleKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") { setOpen(false); inputRef.current?.blur(); }
    if (e.key === "Enter" && filtered.length === 1) select(filtered[0].ticker);
  };

  return (
    <div ref={containerRef} className="relative flex-1">
      <input
        ref={inputRef}
        value={query}
        onChange={(e) => { setQuery(e.target.value.toUpperCase()); onChange(e.target.value.toUpperCase()); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKey}
        placeholder={placeholder}
        className="flex h-10 w-full rounded-md border border-border/50 bg-secondary px-3 py-2 text-sm font-mono ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
        autoComplete="off"
        spellCheck={false}
      />
      {open && filtered.length > 0 && (
        <div className="absolute z-50 mt-1 w-full max-h-64 overflow-auto rounded-md border border-border bg-popover shadow-lg">
          {filtered.map((o) => (
            <button
              key={o.ticker}
              type="button"
              onMouseDown={(e) => { e.preventDefault(); select(o.ticker); }}
              className="flex w-full items-center gap-3 px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground text-left"
            >
              <span className="font-mono font-semibold w-20 shrink-0">{o.ticker}</span>
              <span className="text-muted-foreground truncate flex-1">{o.name}</span>
              <span className="text-xs text-muted-foreground/70 shrink-0">{o.segment}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

export default function PortfolioPage() {
  const { portfolio, addAsset, removeAsset, updateAsset, isEmpty } = usePortfolio();
  const portfolioTickers = useMemo(() => portfolio.assets.map(a => a.ticker), [portfolio.assets]);
  
  const { data: scannerData, isLoading: scannerLoading } = useScanner();
  const { data: scoreAlerts } = useScoreAlerts(portfolioTickers);
  const [newTicker, setNewTicker] = useState("");
  const [newQty, setNewQty] = useState("");
  const [newPrice, setNewPrice] = useState("");
  const [editingTicker, setEditingTicker] = useState<string | null>(null);
  const [editQty, setEditQty] = useState("");
  const [editPrice, setEditPrice] = useState("");

  // Rebalance panel state
  const [showRebalance, setShowRebalance] = useState(false);
  const [targetAlloc, setTargetAlloc] = useState<Record<string, number>>({});
  const [aporteValue, setAporteValue] = useState("");
  const [suggestions, setSuggestions] = useState<RebalanceSuggestion[]>([]);
  
  // IRPF Modal State
  const [showIRPFModal, setShowIRPFModal] = useState(false);

  // Build sector map and price map from scanner data
  const sectorMap = useMemo(() => {
    const map: Record<string, string> = {};
    scannerData?.fiis?.forEach((f) => { map[f.ticker] = f.segment; });
    return map;
  }, [scannerData]);

  const priceMap = useMemo(() => {
    const map: Record<string, number> = {};
    scannerData?.fiis?.forEach((f) => { map[f.ticker] = f.price; });
    return map;
  }, [scannerData]);

  const dyMap = useMemo(() => {
    const map: Record<string, number> = {};
    scannerData?.fiis?.forEach((f) => { map[f.ticker] = f.dy; });
    return map;
  }, [scannerData]);

  // Enrich portfolio with live data
  const enrichedAssets = useMemo(() => {
    return portfolio.assets.map((a) => {
      const currentPrice = priceMap[a.ticker] || a.avgPrice;
      const dy = dyMap[a.ticker] || 0;
      const segment = sectorMap[a.ticker] || "Outros";
      const totalCost = a.quantity * a.avgPrice;
      const totalValue = a.quantity * currentPrice;
      const ret = a.avgPrice > 0 ? ((currentPrice - a.avgPrice) / a.avgPrice) * 100 : 0;
      const dividendMonthly = (totalValue * (dy / 100)) / 12;
      return {
        ...a,
        currentPrice,
        dy,
        segment,
        totalCost,
        totalValue,
        returnPct: ret,
        dividendMonthly,
      };
    });
  }, [portfolio.assets, priceMap, dyMap, sectorMap]);

  const totalEquity = enrichedAssets.reduce((s, a) => s + a.totalValue, 0);
  const totalCost = enrichedAssets.reduce((s, a) => s + a.totalCost, 0);
  const totalDividends = enrichedAssets.reduce((s, a) => s + a.dividendMonthly, 0);
  const totalReturn = totalCost > 0 ? ((totalEquity - totalCost) / totalCost) * 100 : 0;

  // Investor profile
  const profile = calculateInvestorProfile(portfolio.assets, sectorMap);

  // Sector allocation
  const segmentData = useMemo(() => {
    const map: Record<string, number> = {};
    enrichedAssets.forEach((a) => {
      const pct = totalEquity > 0 ? (a.totalValue / totalEquity) * 100 : 0;
      map[a.segment] = (map[a.segment] || 0) + pct;
    });
    return Object.entries(map).map(([name, value]) => ({ name, value: Math.round(value) }));
  }, [enrichedAssets, totalEquity]);

  // Initialize targetAlloc when rebalance panel opens
  const handleToggleRebalance = useCallback(() => {
    setShowRebalance((prev) => {
      if (!prev) {
        // Initialize with current rounded allocation
        const init: Record<string, number> = {};
        segmentData.forEach((s) => { init[s.name] = s.value; });
        setTargetAlloc(init);
        setSuggestions([]);
      }
      return !prev;
    });
  }, [segmentData]);

  const targetAllocTotal = Object.values(targetAlloc).reduce((s, v) => s + v, 0);

  const calculateSuggestions = useCallback(() => {
    const aporte = parseFloat(aporteValue) || 0;
    const result: RebalanceSuggestion[] = [];

    // Map segment → current pct
    const currentMap: Record<string, number> = {};
    segmentData.forEach((s) => { currentMap[s.name] = s.value; });

    // All segments present in targetAlloc union currentMap
    const allSegments = Array.from(new Set([
      ...Object.keys(targetAlloc),
      ...Object.keys(currentMap),
    ]));

    // Calculate total deficit weight to distribute aporte proportionally
    const deficits: Array<{ segment: string; deficit: number }> = [];
    allSegments.forEach((seg) => {
      const target = targetAlloc[seg] ?? 0;
      const current = currentMap[seg] ?? 0;
      if (target > current) {
        deficits.push({ segment: seg, deficit: target - current });
      }
    });
    const totalDeficit = deficits.reduce((s, d) => s + d.deficit, 0);

    allSegments.forEach((seg) => {
      const target = targetAlloc[seg] ?? 0;
      const current = currentMap[seg] ?? 0;
      const diff = target - current;

      if (diff < 0) {
        // Overweight — just warn, no purchase
        result.push({
          ticker: "",
          segment: seg,
          action: "overweight",
          quantity: 0,
          value: 0,
          currentPct: current,
          targetPct: target,
          score: 0,
        });
        return;
      }

      if (diff === 0) return;

      // Find best candidate FII in this segment from scanner
      const candidates = (scannerData?.fiis ?? [])
        .filter((f) => f.segment === seg && f.price > 0)
        .sort((a, b) => b.score - a.score);

      if (candidates.length === 0) return;

      // Prefer FIIs already in portfolio, then the highest-score available
      const portfolioTickers = new Set(portfolio.assets.map((a) => a.ticker));
      const best =
        candidates.find((f) => portfolioTickers.has(f.ticker)) ?? candidates[0];

      // Capital to allocate: from aporte (proportional to deficit) + gap vs equity
      let capital = 0;
      if (aporte > 0 && totalDeficit > 0) {
        capital = (deficits.find((d) => d.segment === seg)?.deficit ?? 0) / totalDeficit * aporte;
      } else {
        // Without aporte, show what would be needed to reach target from current equity
        capital = (diff / 100) * totalEquity;
      }

      const qty = Math.floor(capital / best.price);
      if (qty <= 0) return;

      result.push({
        ticker: best.ticker,
        segment: seg,
        action: "buy",
        quantity: qty,
        value: qty * best.price,
        currentPct: current,
        targetPct: target,
        score: best.score,
      });
    });

    // Sort: buy first, then overweight warnings
    result.sort((a, b) => {
      if (a.action === b.action) return b.targetPct - a.targetPct;
      return a.action === "buy" ? -1 : 1;
    });

    setSuggestions(result);
  }, [segmentData, targetAlloc, aporteValue, scannerData, portfolio.assets, totalEquity]);

  // Available tickers for autocomplete (includes name + segment for display)
  const availableTickers = useMemo<FIIOption[]>(() => {
    if (!scannerData) return [];
    const existing = new Set(portfolio.assets.map((a) => a.ticker));
    return scannerData.fiis
      .filter((f) => !existing.has(f.ticker))
      .map((f) => ({ ticker: f.ticker, name: f.name || f.ticker, segment: f.segment || "" }));
  }, [scannerData, portfolio.assets]);

  const handleAdd = () => {
    const ticker = newTicker.toUpperCase().trim();
    const qty = parseInt(newQty);
    const price = parseFloat(newPrice) || priceMap[ticker] || 0;
    if (!ticker || !qty || qty <= 0) return;
    addAsset(ticker, qty, price);
    setNewTicker("");
    setNewQty("");
    setNewPrice("");
  };

  const handleStartEdit = (a: typeof enrichedAssets[0]) => {
    setEditingTicker(a.ticker);
    setEditQty(String(a.quantity));
    setEditPrice(String(a.avgPrice.toFixed(2)));
  };

  const handleSaveEdit = () => {
    if (!editingTicker) return;
    const qty = parseInt(editQty);
    const price = parseFloat(editPrice);
    if (qty > 0 && price > 0) {
      updateAsset(editingTicker, qty, price);
    }
    setEditingTicker(null);
  };

  // Upcoming dividends for portfolio tickers
  const [upcomingEvents, setUpcomingEvents] = useState<UpcomingDividendEvent[]>([]);
  useEffect(() => {
    if (portfolio.assets.length === 0) return;
    const tickers = portfolio.assets.map((a) => a.ticker).join(",");
    fetchUpcomingDividends(30, tickers)
      .then(({ events }) => setUpcomingEvents(events))
      .catch(() => {});
  }, [portfolio.assets]);

  if (scannerLoading) {
    return (
      <div className="flex items-center justify-center h-96 gap-3 text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin" />
        Carregando dados do mercado...
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-[family-name:var(--font-display)]">Minha Carteira</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {isEmpty ? "Adicione seus FIIs para começar a análise" : `${portfolio.assets.length} ativos — preços atualizados em tempo real`}
          </p>
        </div>
        {!isEmpty && (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowIRPFModal(true)}
              className="border-primary/50 text-primary hover:bg-primary/10 gap-2"
            >
              <Receipt className="w-4 h-4" /> Informe IRPF
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={() => {
                if (enrichedAssets.length === 0 || totalEquity === 0) return;
                const t = enrichedAssets.map(a => a.ticker).join(",");
                const w = enrichedAssets.map(a => (a.totalValue / totalEquity).toFixed(4)).join(",");
                window.open(`http://localhost:8000/api/portfolio/tearsheet?tickers=${t}&weights=${w}`, '_blank');
              }}
              className="gap-2"
            >
              <FileBarChart className="w-4 h-4" /> Gerar Tearsheet
            </Button>
          </div>
        )}
      </div>

      {/* Score Alerts banner */}
      {scoreAlerts?.alerts && scoreAlerts.alerts.length > 0 && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3">
          <div className="flex items-center gap-2 mb-2 text-destructive">
            <AlertTriangle className="w-4 h-4" />
            <span className="text-sm font-medium">Alerta de Risco: Queda brusca no AlphaScore</span>
          </div>
          <div className="flex flex-col gap-2">
            {scoreAlerts.alerts.map((alert, i) => (
              <div key={i} className="flex items-center gap-2 px-3 py-2 rounded-md text-xs border border-destructive/20 bg-background/50 text-foreground">
                <span className="font-mono font-bold px-2 py-0.5 rounded bg-muted/50">{alert.ticker}</span>
                <span className="text-muted-foreground ml-1">
                  Caiu de <span className="text-foreground">{alert.previous_score.toFixed(1)}</span> para <span className="text-destructive font-bold">{alert.latest_score.toFixed(1)}</span>
                </span>
                <span className="font-bold text-destructive inline-flex items-center ml-auto bg-destructive/10 px-2 py-0.5 rounded">
                  <TrendingDown className="w-3 h-3 mr-1" />
                  -{alert.drop.toFixed(1)} pts
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Upcoming dividends banner */}
      {upcomingEvents.length > 0 && (
        <div className="rounded-lg border border-primary/30 bg-primary/5 p-3">
          <div className="flex items-center gap-2 mb-2">
            <CalendarClock className="w-4 h-4 text-primary" />
            <span className="text-sm font-medium">Próximos pagamentos (30 dias)</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {upcomingEvents.map((ev, i) => (
              <div key={i} className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-xs border ${
                ev.days_to_pay <= 7
                  ? "border-primary/50 bg-primary/10 text-primary"
                  : "border-border/50 bg-secondary text-foreground"
              }`}>
                <span className="font-mono font-bold">{ev.ticker.replace(/\.SA$/, "")}</span>
                <span className="text-muted-foreground">R$ {ev.valor_por_cota.toFixed(2)}/cota</span>
                <span className={`font-medium ${ev.days_to_pay <= 7 ? "text-primary" : "text-muted-foreground"}`}>
                  em {ev.days_to_pay}d
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Add asset form */}
      <Card className="bg-card border-border/30">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-[family-name:var(--font-display)] flex items-center gap-2">
            <Plus className="w-4 h-4 text-primary" /> Adicionar FII
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row gap-3">
            <TickerCombobox
              options={availableTickers}
              value={newTicker}
              onChange={setNewTicker}
            />
            <Input
              type="number"
              value={newQty}
              onChange={(e) => setNewQty(e.target.value)}
              placeholder="Quantidade"
              className="bg-secondary border-border/50 font-mono w-32"
              min="1"
            />
            <Input
              type="number"
              value={newPrice}
              onChange={(e) => setNewPrice(e.target.value)}
              placeholder={newTicker && priceMap[newTicker.toUpperCase()] ? `R$ ${priceMap[newTicker.toUpperCase()]?.toFixed(2)} (atual)` : "Preço médio"}
              className="bg-secondary border-border/50 font-mono w-40"
              step="0.01"
            />
            <Button onClick={handleAdd} disabled={!newTicker.trim() || !newQty}>
              <Plus className="w-4 h-4 mr-1" /> Adicionar
            </Button>
          </div>
        </CardContent>
      </Card>

      {isEmpty ? (
        <Card className="bg-card border-border/30">
          <CardContent className="p-12 text-center">
            <Wallet className="w-12 h-12 text-muted-foreground/30 mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">Carteira vazia</h3>
            <p className="text-sm text-muted-foreground max-w-md mx-auto">
              Adicione seus FIIs acima para ver alocação por segmento, rentabilidade, dividendos estimados e perfil de investidor.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card className="bg-card border-border/30">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1">
                  <Wallet className="w-3.5 h-3.5" /> Patrimônio
                </div>
                <p className="text-xl font-bold font-[family-name:var(--font-mono)]">
                  R$ {totalEquity.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                </p>
              </CardContent>
            </Card>
            <Card className="bg-card border-border/30">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1">
                  <DollarSign className="w-3.5 h-3.5" /> Dividendos/mês (est.)
                </div>
                <p className="text-xl font-bold font-[family-name:var(--font-mono)] text-primary">
                  R$ {totalDividends.toFixed(2)}
                </p>
              </CardContent>
            </Card>
            <Card className="bg-card border-border/30">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1">
                  <PieIcon className="w-3.5 h-3.5" /> Ativos
                </div>
                <p className="text-xl font-bold font-[family-name:var(--font-mono)]">{portfolio.assets.length}</p>
              </CardContent>
            </Card>
            <Card className="bg-card border-border/30">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1">
                  {totalReturn >= 0 ? <TrendingUp className="w-3.5 h-3.5 text-accent" /> : <TrendingDown className="w-3.5 h-3.5 text-destructive" />}
                  Rentabilidade
                </div>
                <p className={`text-xl font-bold font-[family-name:var(--font-mono)] ${totalReturn >= 0 ? "text-accent" : "text-destructive"}`}>
                  {totalReturn >= 0 ? "+" : ""}{totalReturn.toFixed(2)}%
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Investor Profile + Allocation Chart */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Investor Profile */}
            <Card className="bg-card border-border/30">
              <CardHeader className="pb-2">
                <CardTitle className="text-base font-[family-name:var(--font-display)] flex items-center gap-2">
                  <User className="w-4 h-4 text-primary" /> Perfil do Investidor
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-center mb-4">
                  <div className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-primary/10 border border-primary/20">
                    <Shield className="w-5 h-5 text-primary" />
                    <span className="text-lg font-bold text-primary">{profile.profile}</span>
                  </div>
                </div>
                <p className="text-sm text-muted-foreground text-center mb-4">{profile.description}</p>
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-muted-foreground">Conservador</span>
                    <span className="font-mono">{profile.riskLevel}/100</span>
                    <span className="text-muted-foreground">Agressivo</span>
                  </div>
                  <Progress value={profile.riskLevel} className="h-2" />
                </div>
              </CardContent>
            </Card>

            {/* Pie Chart */}
            <Card className="bg-card border-border/30">
              <CardHeader className="pb-2">
                <CardTitle className="text-base font-[family-name:var(--font-display)]">Alocação por Segmento</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col sm:flex-row items-center gap-4">
                  <div className="w-48 h-48">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={segmentData}
                          cx="50%"
                          cy="50%"
                          innerRadius={45}
                          outerRadius={80}
                          paddingAngle={3}
                          dataKey="value"
                          stroke="none"
                        >
                          {segmentData.map((entry) => (
                            <Cell key={entry.name} fill={SEGMENT_COLORS[entry.name] || "hsl(var(--muted))"} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "hsl(222, 44%, 9%)",
                            border: "1px solid hsl(222, 30%, 16%)",
                            borderRadius: "8px",
                            fontSize: "12px",
                          }}
                          formatter={(value: number) => [`${value}%`, "Peso"]}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="flex flex-col gap-2 text-sm">
                    {segmentData.map((s) => (
                      <div key={s.name} className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: SEGMENT_COLORS[s.name] || "#888" }} />
                        <span className="text-muted-foreground">{s.name}</span>
                        <span className="font-[family-name:var(--font-mono)] font-medium ml-auto">{s.value}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Rebalance Panel */}
          <Card className="bg-card border-border/30">
            <CardHeader
              className="pb-2 cursor-pointer select-none"
              onClick={handleToggleRebalance}
            >
              <CardTitle className="text-base font-[family-name:var(--font-display)] flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <Sliders className="w-4 h-4 text-primary" />
                  Sugerir Rebalanceamento
                </span>
                {showRebalance
                  ? <ChevronUp className="w-4 h-4 text-muted-foreground" />
                  : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
              </CardTitle>
            </CardHeader>

            <AnimatePresence initial={false}>
              {showRebalance && (
                <motion.div
                  key="rebalance-body"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.25, ease: "easeInOut" }}
                  style={{ overflow: "hidden" }}
                >
                  <CardContent className="pt-0 space-y-5">
                    {/* Target allocation inputs */}
                    <div>
                      <p className="text-xs text-muted-foreground mb-3">
                        Defina a alocação-alvo por segmento. A soma deve ser 100%.
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {segmentData.map((s) => (
                          <div key={s.name} className="flex items-center gap-3">
                            <div
                              className="w-2.5 h-2.5 rounded-sm shrink-0"
                              style={{ backgroundColor: SEGMENT_COLORS[s.name] || "#888" }}
                            />
                            <span className="text-sm text-muted-foreground w-28 shrink-0 truncate">{s.name}</span>
                            <Input
                              type="number"
                              min={0}
                              max={100}
                              value={targetAlloc[s.name] ?? s.value}
                              onChange={(e) =>
                                setTargetAlloc((prev) => ({
                                  ...prev,
                                  [s.name]: Number(e.target.value),
                                }))
                              }
                              className="bg-secondary border-border/50 font-mono w-20 h-8 text-sm"
                            />
                            <span className="text-xs text-muted-foreground">%</span>
                            <span className="text-xs text-muted-foreground ml-auto shrink-0">
                              atual: {s.value}%
                            </span>
                          </div>
                        ))}
                      </div>

                      {/* Total validation */}
                      <div className={`mt-3 text-xs font-mono flex items-center gap-1.5 ${
                        targetAllocTotal === 100
                          ? "text-accent"
                          : "text-yellow-500"
                      }`}>
                        {targetAllocTotal !== 100 && (
                          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                        )}
                        Total alvo: {targetAllocTotal}%
                        {targetAllocTotal !== 100 && " — ajuste para somar 100%"}
                      </div>
                    </div>

                    {/* Aporte field + calculate button */}
                    <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-muted-foreground whitespace-nowrap">Aporte disponível:</span>
                        <Input
                          type="number"
                          min={0}
                          step={100}
                          value={aporteValue}
                          onChange={(e) => setAporteValue(e.target.value)}
                          placeholder="R$ 0,00"
                          className="bg-secondary border-border/50 font-mono w-36 h-8 text-sm"
                        />
                      </div>
                      <Button
                        size="sm"
                        onClick={calculateSuggestions}
                        disabled={targetAllocTotal !== 100}
                        className="shrink-0"
                      >
                        <Sliders className="w-3.5 h-3.5 mr-1.5" />
                        Calcular Sugestões
                      </Button>
                    </div>

                    {/* Suggestions */}
                    {suggestions.length > 0 && (
                      <div className="space-y-3 pt-2 border-t border-border/30">
                        <p className="text-sm font-medium">Sugestões de Rebalanceamento</p>
                        {suggestions.map((s, i) => (
                          <div
                            key={i}
                            className={`rounded-lg border p-3 text-sm space-y-1 ${
                              s.action === "buy"
                                ? "border-accent/30 bg-accent/5"
                                : "border-yellow-500/30 bg-yellow-500/5"
                            }`}
                          >
                            {s.action === "buy" ? (
                              <>
                                <div className="flex items-center gap-2 font-medium text-accent">
                                  <TrendingUp className="w-4 h-4 shrink-0" />
                                  <span>
                                    COMPRAR {s.quantity} {s.quantity === 1 ? "cota" : "cotas"} de{" "}
                                    <span className="font-mono">{s.ticker}</span>{" "}
                                    (R$ {s.value.toLocaleString("pt-BR", { minimumFractionDigits: 2 })})
                                  </span>
                                </div>
                                <p className="text-xs text-muted-foreground pl-6">
                                  {s.segment}: {s.currentPct}% → meta {s.targetPct}%
                                  {s.score > 0 && (
                                    <span className="ml-2 text-primary">score {s.score}</span>
                                  )}
                                </p>
                                <div className="pl-6 pt-1">
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    className="h-7 text-xs border-accent/40 text-accent hover:bg-accent/10"
                                    onClick={() => {
                                      setNewTicker(s.ticker);
                                      setNewQty(String(s.quantity));
                                      const price = scannerData?.fiis?.find((f) => f.ticker === s.ticker)?.price;
                                      if (price) setNewPrice(price.toFixed(2));
                                      // Scroll to top of page where add form is
                                      window.scrollTo({ top: 0, behavior: "smooth" });
                                    }}
                                  >
                                    + Adicionar {s.ticker} à carteira
                                  </Button>
                                </div>
                              </>
                            ) : (
                              <>
                                <div className="flex items-center gap-2 font-medium text-yellow-500">
                                  <AlertTriangle className="w-4 h-4 shrink-0" />
                                  <span>
                                    {s.segment} está {(s.currentPct - s.targetPct).toFixed(0)}% acima da meta
                                  </span>
                                </div>
                                <p className="text-xs text-muted-foreground pl-6">
                                  Atual: {s.currentPct}% — Meta: {s.targetPct}% — Considere não aportar aqui
                                </p>
                              </>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </motion.div>
              )}
            </AnimatePresence>
          </Card>

          {/* Assets Table */}
          <Card className="bg-card border-border/30">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base font-[family-name:var(--font-display)]">Ativos na Carteira</CardTitle>
                  <CardDescription>Clique em um ativo para editar. Preços atuais do mercado.</CardDescription>
                </div>
                {enrichedAssets.length > 0 && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-border/50 hover:bg-secondary gap-1.5"
                    title="Exportar carteira como CSV"
                    onClick={() => {
                      const headers = ["Ticker", "Segmento", "Quantidade", "Preço Médio", "Preço Atual", "Custo Total", "Valor Atual", "Retorno %", "DY %", "Div/mês"];
                      const rows = enrichedAssets.map((a) => [
                        a.ticker,
                        a.segment,
                        a.quantity,
                        a.avgPrice.toFixed(2),
                        a.currentPrice.toFixed(2),
                        a.totalCost.toFixed(2),
                        a.totalValue.toFixed(2),
                        a.returnPct.toFixed(2),
                        a.dy.toFixed(2),
                        a.dividendMonthly.toFixed(2),
                      ]);
                      const csv = [headers.join(";"), ...rows.map((r) => r.join(";"))].join("\n");
                      const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = `carteira_alphacota_${new Date().toISOString().slice(0, 10)}.csv`;
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                  >
                    <Download className="w-3.5 h-3.5" />
                    CSV
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <Table className="min-w-[600px]">
                <TableHeader>
                  <TableRow className="border-border/30 hover:bg-transparent">
                    <TableHead className="text-xs">Ticker</TableHead>
                    <TableHead className="text-xs hidden sm:table-cell">Segmento</TableHead>
                    <TableHead className="text-xs text-right">Qtd</TableHead>
                    <TableHead className="text-xs text-right hidden md:table-cell">PM</TableHead>
                    <TableHead className="text-xs text-right">Atual</TableHead>
                    <TableHead className="text-xs text-right">Retorno</TableHead>
                    <TableHead className="text-xs text-right hidden sm:table-cell">DY</TableHead>
                    <TableHead className="text-xs text-right">Div/mês</TableHead>
                    <TableHead className="text-xs text-center w-16"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {enrichedAssets.map((a) => (
                    <TableRow key={a.ticker} className="border-border/30">
                      {editingTicker === a.ticker ? (
                        <>
                          <TableCell className="font-[family-name:var(--font-mono)] font-medium text-sm">{a.ticker}</TableCell>
                          <TableCell className="hidden sm:table-cell">
                            <Badge variant="outline" className="text-xs border-border/50">{a.segment}</Badge>
                          </TableCell>
                          <TableCell className="text-right">
                            <Input
                              type="number"
                              value={editQty}
                              onChange={(e) => setEditQty(e.target.value)}
                              className="w-20 h-7 text-xs font-mono bg-secondary"
                              min="1"
                            />
                          </TableCell>
                          <TableCell className="text-right hidden md:table-cell">
                            <Input
                              type="number"
                              value={editPrice}
                              onChange={(e) => setEditPrice(e.target.value)}
                              className="w-24 h-7 text-xs font-mono bg-secondary"
                              step="0.01"
                            />
                          </TableCell>
                          <TableCell colSpan={3}></TableCell>
                          <TableCell className="text-center">
                            <Button size="sm" variant="ghost" className="h-7 text-xs text-primary" onClick={handleSaveEdit}>
                              Salvar
                            </Button>
                          </TableCell>
                        </>
                      ) : (
                        <>
                          <TableCell
                            className="font-[family-name:var(--font-mono)] font-medium text-sm cursor-pointer hover:text-primary"
                            onClick={() => handleStartEdit(a)}
                          >
                            {a.ticker}
                          </TableCell>
                          <TableCell className="hidden sm:table-cell">
                            <Badge variant="outline" className="text-xs border-border/50">{a.segment}</Badge>
                          </TableCell>
                          <TableCell className="text-right font-[family-name:var(--font-mono)] text-sm">{a.quantity}</TableCell>
                          <TableCell className="text-right font-[family-name:var(--font-mono)] text-sm hidden md:table-cell">
                            R$ {a.avgPrice.toFixed(2)}
                          </TableCell>
                          <TableCell className="text-right font-[family-name:var(--font-mono)] text-sm">
                            R$ {a.currentPrice.toFixed(2)}
                          </TableCell>
                          <TableCell className={`text-right font-[family-name:var(--font-mono)] text-sm font-medium ${a.returnPct >= 0 ? "text-accent" : "text-destructive"}`}>
                            {a.returnPct >= 0 ? "+" : ""}{a.returnPct.toFixed(1)}%
                          </TableCell>
                          <TableCell className="text-right font-[family-name:var(--font-mono)] text-sm text-primary hidden sm:table-cell">
                            {a.dy.toFixed(1)}%
                          </TableCell>
                          <TableCell className="text-right font-[family-name:var(--font-mono)] text-sm">
                            R$ {a.dividendMonthly.toFixed(2)}
                          </TableCell>
                          <TableCell className="text-center">
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                              onClick={() => removeAsset(a.ticker)}
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </Button>
                          </TableCell>
                        </>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}

      {/* IRPF Modal */}
      <AnimatePresence>
        {showIRPFModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-card border border-border/50 shadow-xl rounded-xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden relative"
            >
              <div className="p-6 border-b border-border/50 flex items-center justify-between shrink-0">
                <div>
                  <h3 className="text-xl font-bold font-[family-name:var(--font-display)] flex items-center gap-2">
                    <Receipt className="w-5 h-5 text-primary" /> Informe Anual (IRPF)
                  </h3>
                  <p className="text-sm text-muted-foreground mt-1">
                    Posição em bens e direitos (cotas) e rendimentos isentos (dividendos) projetados.
                  </p>
                </div>
                <Button variant="ghost" size="icon" onClick={() => setShowIRPFModal(false)}>
                  <Trash2 className="w-4 h-4" /> {/* Fallback icon for close, typically X */}
                </Button>
              </div>
              <div className="p-6 overflow-y-auto space-y-6 flex-1">
                
                <div className="rounded-lg bg-accent/10 border border-accent/20 p-4">
                  <h4 className="font-semibold text-accent mb-2">Bens e Direitos (Grupo 07 - Código 03)</h4>
                  <p className="text-sm text-muted-foreground mb-4">
                    Declare o saldo exato do custo de aquisição da sua carteira. Os dados abaixo são de caráter projetivo e educativo.
                  </p>
                  <div className="space-y-3">
                    {enrichedAssets.map((a) => (
                      <div key={a.ticker} className="flex flex-col sm:flex-row justify-between p-3 border border-border/50 rounded bg-background/50 text-sm">
                        <div className="mb-2 sm:mb-0">
                          <span className="font-bold text-primary font-mono">{a.ticker}</span>
                          <span className="text-xs text-muted-foreground ml-2">({a.segment})</span>
                          <div className="text-xs text-muted-foreground mt-1">CNPJ não encontrado na base. Consulte o StatusInvest.</div>
                        </div>
                        <div className="text-left sm:text-right">
                          <div className="font-medium">{a.quantity} cotas</div>
                          <div className="text-xs text-muted-foreground">Custo total: R$ {a.totalCost.toFixed(2)}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-lg bg-primary/10 border border-primary/20 p-4">
                  <h4 className="font-semibold text-primary mb-2">Rendimentos Isentos e Nâo Tributáveis (Tipo 26)</h4>
                  <p className="text-sm text-muted-foreground mb-4">
                    Projeção anual de dividendos. Total em 12 meses: <strong className="text-foreground">R$ {(totalDividends * 12).toFixed(2)}</strong>
                  </p>
                  <div className="space-y-3">
                    {enrichedAssets.map((a) => (
                      <div key={a.ticker} className="flex justify-between items-center p-3 border border-border/50 rounded bg-background/50 text-sm">
                        <span className="font-bold font-mono">{a.ticker}</span>
                        <span className="font-medium text-primary">R$ {(a.dividendMonthly * 12).toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              
              <div className="p-4 border-t border-border/50 shrink-0 flex justify-end gap-3 bg-secondary/20">
                <Button variant="outline" onClick={() => setShowIRPFModal(false)}>
                  Fechar
                </Button>
                <Button onClick={() => window.print()} className="gap-2">
                  <Download className="w-4 h-4" /> Salvar em PDF
                </Button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
