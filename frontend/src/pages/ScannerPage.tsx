import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Radar, LineChart, TrendingUp, ArrowUpDown, Search, Filter, Star, ChevronDown, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";
import { useScanner } from "@/hooks/use-api";
import { useFavorites } from "@/hooks/use-portfolio";
import type { FII } from "@/services/api";

type SortKey = "score" | "ticker" | "dy" | "pvp" | "price" | "change";
type SortDir = "asc" | "desc";

const segments = ["Logística", "Shopping", "Lajes Corp.", "Papel (CRI)", "Híbrido", "Fundo de Fundos", "Agro", "Saúde"];

const ScannerPage = () => {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [selectedSegments, setSelectedSegments] = useState<string[]>([]);
  const [showFilters, setShowFilters] = useState(false);

  const { data, isLoading, error } = useScanner();
  const { toggleFavorite, isFavorite } = useFavorites();

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

  const fiis = data?.fiis ?? [];

  const filtered = fiis
    .filter((f) => {
      const matchSearch = f.ticker.toLowerCase().includes(search.toLowerCase()) || f.name.toLowerCase().includes(search.toLowerCase());
      const matchSegment = selectedSegments.length === 0 || selectedSegments.includes(f.segment);
      return matchSearch && matchSegment;
    })
    .sort((a, b) => {
      const mul = sortDir === "asc" ? 1 : -1;
      if (sortKey === "ticker") return mul * a.ticker.localeCompare(b.ticker);
      return mul * ((a[sortKey] as number) - (b[sortKey] as number));
    });

  const avgScore = Math.round(filtered.reduce((s, f) => s + f.score, 0) / (filtered.length || 1));
  const avgDY = (filtered.reduce((s, f) => s + f.dy, 0) / (filtered.length || 1)).toFixed(1);
  const avgPVP = (filtered.reduce((s, f) => s + f.pvp, 0) / (filtered.length || 1)).toFixed(2);

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
        <p className="text-xs text-muted-foreground mt-2">Verifique se a API está rodando: python -m uvicorn api.main:app --port 8000</p>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-3">
          <Radar className="w-6 h-6 text-primary" />
          Market Scanner
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Análise quantitativa de {data?.total ?? 0} FIIs — dados reais via yfinance + StatusInvest
        </p>
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

      {/* Search & Filters */}
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
          variant="outline"
          onClick={() => setShowFilters(!showFilters)}
          className="border-border/50 hover:bg-secondary"
        >
          <Filter className="w-4 h-4 mr-2" />
          Filtros
          <ChevronDown className={`w-4 h-4 ml-1 transition-transform ${showFilters ? "rotate-180" : ""}`} />
        </Button>
      </div>

      {showFilters && (
        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="flex flex-wrap gap-2">
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
          {selectedSegments.length > 0 && (
            <button
              onClick={() => setSelectedSegments([])}
              className="px-3 py-1.5 rounded-lg text-xs font-mono text-destructive border border-destructive/30 hover:bg-destructive/10 transition-colors"
            >
              Limpar
            </button>
          )}
        </motion.div>
      )}

      {/* Table */}
      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/30">
                <th className="px-4 py-3 text-left font-mono text-xs text-muted-foreground font-medium w-8"></th>
                <SortHeader label="TICKER" k="ticker" />
                <th className="px-4 py-3 text-left font-mono text-xs text-muted-foreground font-medium hidden lg:table-cell">SEGMENTO</th>
                <SortHeader label="PREÇO" k="price" />
                <SortHeader label="VAR" k="change" />
                <SortHeader label="DY" k="dy" />
                <SortHeader label="P/VP" k="pvp" />
                <SortHeader label="SCORE" k="score" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((fii) => (
                <tr key={fii.ticker} className="border-b border-border/10 hover:bg-secondary/30 transition-colors cursor-pointer" onClick={() => navigate(`/dashboard/fii/${fii.ticker}`)}>
                  <td className="px-4 py-3">
                    <Star
                      className={`w-3.5 h-3.5 cursor-pointer transition-colors ${isFavorite(fii.ticker) ? "text-accent fill-accent" : "text-muted-foreground/30 hover:text-accent/50"}`}
                      onClick={(e) => { e.stopPropagation(); toggleFavorite(fii.ticker); }}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-mono font-semibold">{fii.ticker}</div>
                    <div className="text-xs text-muted-foreground hidden sm:block">{fii.name}</div>
                  </td>
                  <td className="px-4 py-3 hidden lg:table-cell">
                    <span className="text-xs font-mono px-2 py-0.5 rounded bg-secondary text-muted-foreground">{fii.segment}</span>
                  </td>
                  <td className="px-4 py-3 text-center font-mono">R$ {fii.price.toFixed(2)}</td>
                  <td className={`px-4 py-3 text-center font-mono font-medium ${fii.change >= 0 ? "text-accent" : "text-destructive"}`}>
                    {fii.change >= 0 ? "+" : ""}{fii.change.toFixed(1)}%
                  </td>
                  <td className="px-4 py-3 text-center font-mono text-accent">{fii.dy.toFixed(1)}%</td>
                  <td className="px-4 py-3 text-center font-mono text-muted-foreground">{fii.pvp.toFixed(2)}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`inline-flex items-center justify-center w-10 h-6 rounded font-mono font-bold text-xs ${
                      fii.score >= 85 ? "bg-primary/15 text-primary" : fii.score >= 75 ? "bg-accent/15 text-accent" : "bg-muted text-muted-foreground"
                    }`}>
                      {fii.score}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default ScannerPage;
