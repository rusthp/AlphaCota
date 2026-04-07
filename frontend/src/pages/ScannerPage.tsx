import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Radar, LineChart, TrendingUp, ArrowUpDown, Search, Filter, Star,
  ChevronDown, Loader2, CalendarClock, ShieldCheck, Shield, ShieldAlert,
  AlertTriangle, Droplets, Download, X,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";
import { useScanner } from "@/hooks/use-api";
import { useFavorites, usePortfolio } from "@/hooks/use-portfolio";
import { fetchUpcomingDividends, type UpcomingDividendEvent } from "@/services/api";
import type { FII } from "@/services/api";

type SortKey = "score" | "ticker" | "dy" | "pvp" | "price" | "change" | "confidence" | "liquidity";
type SortDir = "asc" | "desc";

const segments = ["Logística", "Shopping", "Lajes Corp.", "Papel (CRI)", "Híbrido", "Fundo de Fundos", "Agro", "Saúde"];

const ScannerPage = () => {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [selectedSegments, setSelectedSegments] = useState<string[]>([]);
  const [showFilters, setShowFilters] = useState(false);
  const [showOnlyFavs, setShowOnlyFavs] = useState(false);
  const [minScore, setMinScore] = useState<string>("");
  const [minDY, setMinDY] = useState<string>("");
  const [maxDY, setMaxDY] = useState<string>("");
  const [visibleCols, setVisibleCols] = useState({
    segmento: true,
    preco: true,
    var: true,
    dy: true,
    pvp: true,
    score: true,
    confianca: true,
    liquidez: false,
  });

  const { data, isLoading, error } = useScanner();
  const { toggleFavorite, isFavorite } = useFavorites();
  const { portfolio } = usePortfolio();
  const portfolioTickers = new Set(portfolio.assets.map((a) => a.ticker));
  const [upcomingMap, setUpcomingMap] = useState<Record<string, UpcomingDividendEvent>>({});

  useEffect(() => {
    fetchUpcomingDividends(30).then(({ events }) => {
      const map: Record<string, UpcomingDividendEvent> = {};
      for (const ev of events) {
        if (!map[ev.ticker] || ev.days_to_pay < map[ev.ticker].days_to_pay) {
          map[ev.ticker] = ev;
        }
      }
      setUpcomingMap(map);
    }).catch(() => {});
  }, []);

  const toggleSegment = (seg: string) => {
    setSelectedSegments((prev) =>
      prev.includes(seg) ? prev.filter((s) => s !== seg) : [...prev, seg]
    );
  };

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const hasActiveFilters = selectedSegments.length > 0 || minScore !== "" || minDY !== "" || maxDY !== "";

  const clearFilters = () => {
    setSelectedSegments([]);
    setMinScore("");
    setMinDY("");
    setMaxDY("");
  };

  const fiis = data?.fiis ?? [];

  const filtered = fiis
    .filter((f) => {
      const matchSearch =
        f.ticker.toLowerCase().includes(search.toLowerCase()) ||
        f.name.toLowerCase().includes(search.toLowerCase());
      const matchSegment = selectedSegments.length === 0 || selectedSegments.includes(f.segment);
      const matchFav = !showOnlyFavs || isFavorite(f.ticker);
      const matchScore = minScore === "" || f.score >= Number(minScore);
      const matchMinDY = minDY === "" || f.dy >= Number(minDY);
      const matchMaxDY = maxDY === "" || f.dy <= Number(maxDY);
      return matchSearch && matchSegment && matchFav && matchScore && matchMinDY && matchMaxDY;
    })
    .sort((a, b) => {
      const mul = sortDir === "asc" ? 1 : -1;
      if (sortKey === "ticker") return mul * a.ticker.localeCompare(b.ticker);
      if (sortKey === "confidence") return mul * ((a.data_confidence ?? 0) - (b.data_confidence ?? 0));
      if (sortKey === "pvp") {
        const av = a.pvp ?? -1;
        const bv = b.pvp ?? -1;
        return mul * (av - bv);
      }
      return mul * ((a[sortKey] as number) - (b[sortKey] as number));
    });

  const avgScore = Math.round(filtered.reduce((s, f) => s + f.score, 0) / (filtered.length || 1));
  const avgDY = (filtered.reduce((s, f) => s + f.dy, 0) / (filtered.length || 1)).toFixed(1);
  const pvpList = filtered.filter((f) => f.pvp !== null).map((f) => f.pvp as number);
  const avgPVP = pvpList.length
    ? (pvpList.reduce((s, v) => s + v, 0) / pvpList.length).toFixed(2)
    : "—";

  const exportCSV = useCallback(() => {
    const headers = ["Ticker", "Nome", "Segmento", "Preço", "Var%", "DY%", "P/VP", "Score", "Liquidez", "Confiança"];
    const rows = filtered.map((f) => [
      f.ticker,
      `"${f.name}"`,
      f.segment,
      f.price.toFixed(2),
      f.change.toFixed(2),
      f.dy.toFixed(2),
      f.pvp !== null ? f.pvp.toFixed(2) : "",
      f.score,
      f.liquidity,
      f.data_confidence ?? 0,
    ]);
    const csv = [headers.join(";"), ...rows.map((r) => r.join(";"))].join("\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `alphacota_scanner_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [filtered]);

  const SortHeader = ({ label, k }: { label: string; k: SortKey }) => (
    <th
      onClick={() => handleSort(k)}
      className="px-4 py-3 font-mono text-xs text-muted-foreground font-medium cursor-pointer hover:text-foreground transition-colors select-none"
    >
      <div className="flex items-center gap-1 justify-center">
        {label}
        <ArrowUpDown className={`w-3 h-3 ${sortKey === k ? "text-primary" : "opacity-30"}`} />
      </div>
    </th>
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96 gap-3 text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin" />
        Carregando dados reais dos FIIs...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-center text-destructive">
        <p className="text-lg font-semibold">Erro ao carregar scanner</p>
        <p className="text-sm text-muted-foreground mt-1">{(error as Error).message}</p>
        <p className="text-xs text-muted-foreground mt-2">
          Verifique se a API está rodando: python -m uvicorn api.main:app --port 8000
        </p>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-3">
            <Radar className="w-6 h-6 text-primary" />
            Market Scanner
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Análise quantitativa de {data?.total ?? 0} FIIs — dados reais via yfinance + StatusInvest
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={exportCSV}
          className="border-border/50 hover:bg-secondary gap-2"
          title="Exportar tabela atual como CSV"
        >
          <Download className="w-4 h-4" />
          CSV
        </Button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "FIIs Analisados", value: filtered.length, icon: Radar },
          { label: "Score Médio", value: avgScore, icon: Star },
          { label: "DY Médio", value: `${avgDY}%`, icon: TrendingUp },
          { label: "P/VP Médio", value: avgPVP, icon: LineChart },
        ].map((card) => (
          <div key={card.label} className="glass-card p-4">
            <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1">
              <card.icon className="w-3.5 h-3.5 text-primary" />
              {card.label}
            </div>
            <div className="text-xl font-bold font-mono">{card.value}</div>
          </div>
        ))}
      </div>

      {/* Search & Filters toolbar */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por ticker ou nome..."
            className="pl-10 bg-secondary border-border/50"
          />
        </div>
        <Button
          variant={showOnlyFavs ? "default" : "outline"}
          onClick={() => setShowOnlyFavs(!showOnlyFavs)}
          className={showOnlyFavs ? "" : "border-border/50 hover:bg-secondary"}
          title="Meus Favoritos"
        >
          <Star className={`w-4 h-4 mr-2 ${showOnlyFavs ? "fill-current" : ""}`} />
          Favoritos
        </Button>
        <Button
          variant={hasActiveFilters ? "default" : "outline"}
          onClick={() => setShowFilters(!showFilters)}
          className={hasActiveFilters ? "" : "border-border/50 hover:bg-secondary"}
        >
          <Filter className="w-4 h-4 mr-2" />
          Filtros
          {hasActiveFilters && (
            <span className="ml-1.5 bg-white/20 text-[10px] font-bold rounded px-1">
              {[selectedSegments.length > 0, minScore !== "", minDY !== "", maxDY !== ""].filter(Boolean).length}
            </span>
          )}
          <ChevronDown className={`w-4 h-4 ml-1 transition-transform ${showFilters ? "rotate-180" : ""}`} />
        </Button>
      </div>

      {showFilters && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="glass-card p-4 space-y-4"
        >
          {/* Score & DY sliders */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-mono text-muted-foreground">Score mínimo</label>
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  min={0} max={100}
                  value={minScore}
                  onChange={(e) => setMinScore(e.target.value)}
                  placeholder="ex: 70"
                  className="bg-secondary border-border/50 h-8 text-sm"
                />
                {minScore !== "" && (
                  <button onClick={() => setMinScore("")} className="text-muted-foreground hover:text-foreground">
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-mono text-muted-foreground">DY mínimo (%)</label>
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  min={0} max={100} step={0.5}
                  value={minDY}
                  onChange={(e) => setMinDY(e.target.value)}
                  placeholder="ex: 8"
                  className="bg-secondary border-border/50 h-8 text-sm"
                />
                {minDY !== "" && (
                  <button onClick={() => setMinDY("")} className="text-muted-foreground hover:text-foreground">
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-mono text-muted-foreground">DY máximo (%)</label>
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  min={0} max={100} step={0.5}
                  value={maxDY}
                  onChange={(e) => setMaxDY(e.target.value)}
                  placeholder="ex: 20"
                  className="bg-secondary border-border/50 h-8 text-sm"
                />
                {maxDY !== "" && (
                  <button onClick={() => setMaxDY("")} className="text-muted-foreground hover:text-foreground">
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Segment chips */}
          <div>
            <p className="text-xs font-mono text-muted-foreground mb-2">Segmento</p>
            <div className="flex flex-wrap gap-2">
              {segments.map((seg) => (
                <button
                  key={seg}
                  onClick={() => toggleSegment(seg)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-colors border ${
                    selectedSegments.includes(seg)
                      ? "bg-primary/20 border-primary/50 text-primary"
                      : "bg-secondary border-border/50 text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {seg}
                </button>
              ))}
            </div>
          </div>

          {/* Columns selection */}
          <div className="pt-2 border-t border-border/30">
            <p className="text-xs font-mono text-muted-foreground mb-2">Colunas Visíveis</p>
            <div className="flex flex-wrap gap-2">
              {Object.entries({
                segmento: "Segmento",
                preco: "Preço",
                var: "Variação %",
                dy: "DY",
                pvp: "P/VP",
                score: "Score",
                confianca: "Confiança",
                liquidez: "Liquidez",
              }).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setVisibleCols(prev => ({ ...prev, [key]: !prev[key as keyof typeof visibleCols] }))}
                  className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-colors border ${
                    visibleCols[key as keyof typeof visibleCols]
                      ? "bg-primary/20 border-primary/50 text-primary"
                      : "bg-secondary border-border/50 text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="text-xs font-mono text-destructive hover:underline"
            >
              Limpar todos os filtros
            </button>
          )}
        </motion.div>
      )}

      {/* Results count */}
      <div className="flex items-center justify-between text-xs text-muted-foreground font-mono">
        <span>{filtered.length} FIIs{filtered.length !== fiis.length ? ` de ${fiis.length}` : ""}</span>
        {hasActiveFilters && (
          <button onClick={clearFilters} className="flex items-center gap-1 hover:text-foreground">
            <X className="w-3 h-3" /> Limpar filtros
          </button>
        )}
      </div>

      {/* Table */}
      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/30">
                <th className="px-4 py-3 text-left font-mono text-xs text-muted-foreground font-medium w-8"></th>
                <SortHeader label="TICKER" k="ticker" />
                {visibleCols.segmento && (
                  <th className="px-4 py-3 text-left font-mono text-xs text-muted-foreground font-medium hidden lg:table-cell">
                    SEGMENTO
                  </th>
                )}
                {visibleCols.preco && <SortHeader label="PREÇO" k="price" />}
                {visibleCols.var && <SortHeader label="VAR" k="change" />}
                {visibleCols.dy && <SortHeader label="DY" k="dy" />}
                {visibleCols.pvp && (
                  <th
                    className="px-4 py-3 font-mono text-xs text-muted-foreground font-medium cursor-pointer hover:text-foreground transition-colors select-none hidden sm:table-cell"
                    onClick={() => handleSort("pvp")}
                  >
                    <div className="flex items-center gap-1 justify-center">
                      P/VP <ArrowUpDown className={`w-3 h-3 ${sortKey === "pvp" ? "text-primary" : "opacity-30"}`} />
                    </div>
                  </th>
                )}
                {visibleCols.score && <SortHeader label="SCORE" k="score" />}
                {visibleCols.liquidez && <SortHeader label="LIQUIDEZ" k="liquidity" />}
                {visibleCols.confianca && <SortHeader label="CONF" k="confidence" />}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-muted-foreground text-sm">
                    Nenhum FII encontrado com os filtros aplicados.
                  </td>
                </tr>
              ) : (
                filtered.map((fii) => (
                  <tr
                    key={fii.ticker}
                    className={`border-b border-border/10 hover:bg-secondary/30 transition-colors cursor-pointer ${portfolioTickers.has(fii.ticker) ? "bg-primary/5" : ""}`}
                    onClick={() => navigate(`/dashboard/fii/${fii.ticker}`)}
                  >
                    <td className="px-4 py-3">
                      <Star
                        className={`w-3.5 h-3.5 cursor-pointer transition-colors ${
                          isFavorite(fii.ticker)
                            ? "text-accent fill-accent"
                            : "text-muted-foreground/30 hover:text-accent/50"
                        }`}
                        onClick={(e) => { e.stopPropagation(); toggleFavorite(fii.ticker); }}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono font-semibold">{fii.ticker}</span>
                        {upcomingMap[fii.ticker] && (
                          <span
                            title={`Pagamento em ${upcomingMap[fii.ticker].days_to_pay}d — R$ ${upcomingMap[fii.ticker].valor_por_cota}`}
                            className={`inline-flex items-center gap-0.5 px-1 py-0.5 rounded text-[9px] font-medium leading-none ${
                              upcomingMap[fii.ticker].days_to_pay <= 7
                                ? "bg-primary/20 text-primary"
                                : upcomingMap[fii.ticker].days_to_pay <= 14
                                ? "bg-accent/20 text-accent"
                                : "bg-muted text-muted-foreground"
                            }`}
                          >
                            <CalendarClock className="w-2.5 h-2.5" />
                            {upcomingMap[fii.ticker].days_to_pay}d
                          </span>
                        )}
                        {portfolioTickers.has(fii.ticker) && (
                          <span className="px-1 py-0.5 rounded text-[9px] font-medium leading-none bg-primary/20 text-primary border border-primary/30">
                            carteira
                          </span>
                        )}
                        {fii.dividend_trap && (
                          <span title="DY > 20% — possível armadilha de dividendo">
                            <AlertTriangle className="w-3 h-3 text-yellow-500" />
                          </span>
                        )}
                        {fii.low_liquidity && (
                          <span title="Liquidez < R$ 500k/dia — baixa negociabilidade">
                            <Droplets className="w-3 h-3 text-destructive" />
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground hidden sm:block">{fii.name}</div>
                    </td>
                    {visibleCols.segmento && (
                      <td className="px-4 py-3 hidden lg:table-cell">
                        <span className="text-xs font-mono px-2 py-0.5 rounded bg-secondary text-muted-foreground">
                          {fii.segment}
                        </span>
                      </td>
                    )}
                    {visibleCols.preco && <td className="px-4 py-3 text-center font-mono">R$ {fii.price.toFixed(2)}</td>}
                    {visibleCols.var && (
                      <td className={`px-4 py-3 text-center font-mono font-medium ${fii.change >= 0 ? "text-accent" : "text-destructive"}`}>
                        {fii.change >= 0 ? "+" : ""}{fii.change.toFixed(1)}%
                      </td>
                    )}
                    {visibleCols.dy && <td className="px-4 py-3 text-center font-mono text-accent">{fii.dy.toFixed(1)}%</td>}
                    {visibleCols.pvp && (
                      <td className="px-4 py-3 text-center font-mono hidden sm:table-cell">
                        {fii.pvp !== null ? (
                          <span className={fii.pvp_outlier ? "text-yellow-500 font-semibold" : "text-muted-foreground"}>
                            {fii.pvp.toFixed(2)}
                            {fii.pvp_outlier && (
                              <span title="P/VP fora do normal (< 0,5 ou > 2,0)"> ⚠</span>
                            )}
                          </span>
                        ) : (
                          <span className="text-muted-foreground/40">—</span>
                        )}
                      </td>
                    )}
                    {visibleCols.score && (
                      <td className="px-4 py-3 text-center">
                        <span
                          className={`inline-flex items-center justify-center w-10 h-6 rounded font-mono font-bold text-xs ${
                            fii.score >= 85
                              ? "bg-primary/15 text-primary"
                              : fii.score >= 75
                              ? "bg-accent/15 text-accent"
                              : "bg-muted text-muted-foreground"
                          }`}
                        >
                          {fii.score}
                        </span>
                      </td>
                    )}
                    {visibleCols.liquidez && (
                      <td className="px-4 py-3 text-center font-mono text-xs">
                        {fii.liquidity >= 1_000_000 
                          ? `R$ ${(fii.liquidity / 1_000_000).toFixed(1)}M` 
                          : `R$ ${(fii.liquidity / 1_000).toFixed(0)}k`}
                      </td>
                    )}
                    {visibleCols.confianca && (
                      <td className="px-4 py-3 text-center hidden md:table-cell">
                        {(() => {
                          const conf = fii.data_confidence ?? 0;
                          if (conf >= 80)
                            return (
                              <span title={`Confiança nos dados: ${conf}%`} className="inline-flex items-center justify-center">
                                <ShieldCheck className="w-4 h-4 text-accent" />
                              </span>
                            );
                          if (conf >= 50)
                            return (
                              <span title={`Confiança nos dados: ${conf}%`} className="inline-flex items-center justify-center">
                                <Shield className="w-4 h-4 text-yellow-500" />
                              </span>
                            );
                          return (
                            <span title={`Confiança nos dados: ${conf}%`} className="inline-flex items-center justify-center">
                              <ShieldAlert className="w-4 h-4 text-destructive" />
                            </span>
                          );
                        })()}
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default ScannerPage;
