import { useState, useEffect, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  BarChart3,
  X,
  Plus,
  Loader2,
  Search,
  ChevronDown,
  Briefcase,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { motion, AnimatePresence } from "framer-motion";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
} from "recharts";
import { useScanner } from "@/hooks/use-api";
import { fetchCompare, type CompareableFII } from "@/services/api";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const FII_COLORS = [
  "#6366f1", // indigo
  "#f59e0b", // amber
  "#10b981", // emerald
  "#ef4444", // red
  "#8b5cf6", // violet
];

interface MetricRow {
  label: string;
  key: keyof CompareableFII | string;
  format: (v: number | null | undefined) => string;
  higherIsBetter: boolean;
  extract: (fii: CompareableFII) => number | null | undefined;
}

const METRIC_ROWS: MetricRow[] = [
  {
    label: "Score",
    key: "score",
    format: (v) => (v != null ? String(Math.round(v)) : "—"),
    higherIsBetter: true,
    extract: (f) => f.score,
  },
  {
    label: "DY (%)",
    key: "dy",
    format: (v) => (v != null ? `${v.toFixed(2)}%` : "—"),
    higherIsBetter: true,
    extract: (f) => f.dy,
  },
  {
    label: "P/VP",
    key: "pvp",
    format: (v) => (v != null ? v.toFixed(2) : "—"),
    higherIsBetter: false,
    extract: (f) => f.pvp,
  },
  {
    label: "Preço (R$)",
    key: "price",
    format: (v) => (v != null ? `R$ ${v.toFixed(2)}` : "—"),
    higherIsBetter: false,
    extract: (f) => f.price,
  },
  {
    label: "Liquidez",
    key: "liquidez",
    format: (v) => {
      if (v == null) return "—";
      if (v >= 1_000_000) return `R$ ${(v / 1_000_000).toFixed(1)}M`;
      if (v >= 1_000) return `R$ ${(v / 1_000).toFixed(0)}K`;
      return `R$ ${v.toFixed(0)}`;
    },
    higherIsBetter: true,
    extract: (f) => f.liquidez,
  },
  {
    label: "Patrimônio Líq.",
    key: "fund_info.patrimonio_liquido",
    format: (v) => {
      if (v == null) return "—";
      if (v >= 1_000_000_000) return `R$ ${(v / 1_000_000_000).toFixed(1)}B`;
      if (v >= 1_000_000) return `R$ ${(v / 1_000_000).toFixed(0)}M`;
      return `R$ ${v.toFixed(0)}`;
    },
    higherIsBetter: true,
    extract: (f) => (f.fund_info?.patrimonio_liquido ?? null),
  },
  {
    label: "Vacância (%)",
    key: "vacancia",
    format: (v) => (v != null ? `${v.toFixed(1)}%` : "—"),
    higherIsBetter: false,
    extract: (f) => f.vacancia,
  },
  {
    label: "Nº Imóveis",
    key: "num_imoveis",
    format: (v) => (v != null ? String(v) : "—"),
    higherIsBetter: true,
    extract: (f) => f.num_imoveis ?? null,
  },
  {
    label: "Cap Rate (%)",
    key: "cap_rate",
    format: (v) => (v != null ? `${(v as number).toFixed(2)}%` : "—"),
    higherIsBetter: true,
    extract: (f) => (f.cap_rate != null ? Number(f.cap_rate) : null),
  },
  {
    label: "Volatilidade 30d",
    key: "volatilidade_30d",
    format: (v) => (v != null ? `${(v as number).toFixed(2)}%` : "—"),
    higherIsBetter: false,
    extract: (f) => (f.volatilidade_30d != null ? Number(f.volatilidade_30d) : null),
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function normalize(value: number | null | undefined, min: number, max: number): number {
  if (value == null || max === min) return 50;
  return Math.round(((value - min) / (max - min)) * 100);
}

function buildRadarData(fiis: CompareableFII[]): Array<Record<string, number | string>> {
  const dimensions = [
    { label: "Score", extract: (f: CompareableFII) => f.score ?? 0, higherIsBetter: true },
    { label: "DY", extract: (f: CompareableFII) => f.dy ?? 0, higherIsBetter: true },
    { label: "P/VP inv.", extract: (f: CompareableFII) => f.pvp ?? 0, higherIsBetter: false },
    {
      label: "Liquidez",
      extract: (f: CompareableFII) => Math.log10(Math.max(f.liquidez ?? 1, 1)),
      higherIsBetter: true,
    },
    {
      label: "Fundamentos",
      extract: (f: CompareableFII) => f.score_breakdown?.fundamentos ?? 0,
      higherIsBetter: true,
    },
    {
      label: "Rendimento",
      extract: (f: CompareableFII) => f.score_breakdown?.rendimento ?? 0,
      higherIsBetter: true,
    },
  ];

  return dimensions.map(({ label, extract, higherIsBetter }) => {
    const values = fiis.map(extract);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const row: Record<string, number | string> = { dimension: label };
    fiis.forEach((fii, idx) => {
      const norm = normalize(extract(fii), min, max);
      row[fii.ticker] = higherIsBetter ? norm : 100 - norm;
    });
    return row;
  });
}

function buildPriceChartData(fiis: CompareableFII[]): Array<Record<string, number | string>> {
  // Collect all months across all FIIs
  const allMonths = new Set<string>();
  fiis.forEach((fii) => {
    (fii.price_history ?? []).forEach((pt) => allMonths.add(pt.month));
  });

  const sortedMonths = Array.from(allMonths).sort();
  // Only last 12 months
  const last12 = sortedMonths.slice(-12);

  return last12.map((month) => {
    const row: Record<string, number | string> = { month };
    fiis.forEach((fii) => {
      const pt = (fii.price_history ?? []).find((p) => p.month === month);
      if (pt) row[fii.ticker] = pt.price;
    });
    return row;
  });
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ComparePage() {
  const { data: scannerData } = useScanner();
  const allFIIs = scannerData?.fiis ?? [];
  const [searchParams] = useSearchParams();

  const [selected, setSelected] = useState<string[]>(() => {
    const param = searchParams.get("tickers");
    return param ? param.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean) : [];
  });
  const [compareData, setCompareData] = useState<CompareableFII[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [dropdownOpen, setDropdownOpen] = useState(false);

  // Filter suggestions — not already selected, match search
  const suggestions = useMemo(() => {
    const q = search.toLowerCase();
    return allFIIs
      .filter((f) => !selected.includes(f.ticker))
      .filter((f) => f.ticker.toLowerCase().includes(q) || f.name.toLowerCase().includes(q))
      .slice(0, 10);
  }, [allFIIs, selected, search]);

  function addTicker(ticker: string) {
    if (selected.length >= 5) return;
    setSelected((prev) => [...prev, ticker]);
    setSearch("");
    setDropdownOpen(false);
  }

  function removeTicker(ticker: string) {
    setSelected((prev) => prev.filter((t) => t !== ticker));
  }

  // Fetch compare data when selected changes (2+ FIIs)
  useEffect(() => {
    if (selected.length < 2) {
      setCompareData(null);
      setLoadError(null);
      return;
    }
    setLoading(true);
    setLoadError(null);
    fetchCompare(selected)
      .then((res) => setCompareData(res.fiis))
      .catch((err) => setLoadError((err as Error).message))
      .finally(() => setLoading(false));
  }, [selected.join(",")]);

  // Best-value highlight per metric row
  function getBestIdx(row: MetricRow, fiis: CompareableFII[]): number {
    const values = fiis.map((f) => row.extract(f));
    const defined = values.filter((v) => v != null) as number[];
    if (defined.length === 0) return -1;
    const best = row.higherIsBetter ? Math.max(...defined) : Math.min(...defined);
    return values.findIndex((v) => v === best);
  }

  const radarData = useMemo(
    () => (compareData && compareData.length >= 2 ? buildRadarData(compareData) : []),
    [compareData],
  );

  const priceChartData = useMemo(
    () => (compareData && compareData.length >= 2 ? buildPriceChartData(compareData) : []),
    [compareData],
  );

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-3">
          <BarChart3 className="w-6 h-6 text-primary" />
          Comparador de FIIs
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Selecione 2 a 5 FIIs para comparar métricas, radar e histórico de preços
        </p>
      </div>

      {/* FII Selector */}
      <div className="glass-card p-4 space-y-3 relative z-20">
        <div className="flex flex-wrap gap-2">
          {selected.map((ticker, idx) => (
            <motion.span
              key={ticker}
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-mono font-semibold border"
              style={{
                color: FII_COLORS[idx % FII_COLORS.length],
                borderColor: FII_COLORS[idx % FII_COLORS.length] + "55",
                backgroundColor: FII_COLORS[idx % FII_COLORS.length] + "15",
              }}
            >
              {ticker}
              <button
                onClick={() => removeTicker(ticker)}
                className="hover:opacity-70 transition-opacity"
                aria-label={`Remover ${ticker}`}
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </motion.span>
          ))}

          {selected.length < 5 && (
            <div className="relative">
              <div className="flex items-center gap-1 border border-border/50 rounded-full px-3 py-1.5 bg-secondary/50 min-w-[180px]">
                <Search className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
                <Input
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    setDropdownOpen(true);
                  }}
                  onFocus={() => setDropdownOpen(true)}
                  onBlur={() => setTimeout(() => setDropdownOpen(false), 150)}
                  placeholder="Adicionar FII..."
                  className="border-0 bg-transparent p-0 h-auto text-sm focus-visible:ring-0 focus-visible:ring-offset-0"
                />
                <Plus className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
              </div>

              <AnimatePresence>
                {dropdownOpen && suggestions.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    className="absolute top-full mt-1 left-0 z-50 w-64 rounded-lg border border-border/50 bg-background/95 backdrop-blur shadow-xl overflow-hidden"
                  >
                    {suggestions.map((fii) => (
                      <button
                        key={fii.ticker}
                        onMouseDown={() => addTicker(fii.ticker)}
                        className="w-full flex items-center justify-between px-3 py-2 text-sm hover:bg-secondary/50 transition-colors"
                      >
                        <div className="text-left">
                          <span className="font-mono font-semibold">{fii.ticker}</span>
                          <span className="text-xs text-muted-foreground ml-2 truncate">{fii.name}</span>
                        </div>
                        <Badge variant="outline" className="text-[10px] font-mono ml-2 flex-shrink-0">
                          {fii.score}
                        </Badge>
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}
        </div>

        {selected.length < 2 && (
          <p className="text-xs text-muted-foreground">
            Selecione 2 ou mais FIIs para comparar
          </p>
        )}
        {selected.length >= 5 && (
          <p className="text-xs text-muted-foreground">
            Máximo de 5 FIIs atingido
          </p>
        )}
      </div>

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center h-48 gap-3 text-muted-foreground">
          <Loader2 className="w-5 h-5 animate-spin" />
          Carregando dados para comparação...
        </div>
      )}

      {/* Error state */}
      {loadError && !loading && (
        <div className="glass-card p-6 text-center text-destructive">
          <p className="font-semibold">Erro ao carregar dados</p>
          <p className="text-sm text-muted-foreground mt-1">{loadError}</p>
        </div>
      )}

      {/* Empty state */}
      {!loading && !loadError && selected.length < 2 && (
        <div className="glass-card p-12 text-center text-muted-foreground">
          <BarChart3 className="w-12 h-12 mx-auto mb-4 opacity-20" />
          <p className="text-lg font-medium">Selecione 2 ou mais FIIs para comparar</p>
          <p className="text-sm mt-1">Use o campo acima para buscar e adicionar FIIs</p>
        </div>
      )}

      {/* Content — shown when data loaded and 2+ FIIs */}
      {!loading && !loadError && compareData && compareData.length >= 2 && (
        <>
          {/* Metrics comparison table */}
          <div className="glass-card overflow-hidden">
            <div className="px-6 py-4 border-b border-border/30">
              <h2 className="font-semibold text-sm">Tabela Comparativa</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border/20">
                    <th className="px-4 py-3 text-left font-mono text-xs text-muted-foreground font-medium">
                      MÉTRICA
                    </th>
                    {compareData.map((fii, idx) => (
                      <th
                        key={fii.ticker}
                        className="px-4 py-3 text-center font-mono text-xs font-semibold"
                        style={{ color: FII_COLORS[idx % FII_COLORS.length] }}
                      >
                        <div className="flex flex-col items-center gap-1.5">
                          <span>{fii.ticker}</span>
                          <Link to={`/dashboard/portfolio`}>
                            <Button
                              variant="outline"
                              size="sm"
                              className="h-6 px-2 text-[10px] border-border/40 hover:bg-secondary"
                            >
                              <Briefcase className="w-2.5 h-2.5 mr-1" />
                              Carteira
                            </Button>
                          </Link>
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {METRIC_ROWS.map((row) => {
                    const bestIdx = getBestIdx(row, compareData);
                    return (
                      <tr
                        key={row.label}
                        className="border-b border-border/10 hover:bg-secondary/20 transition-colors"
                      >
                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                          {row.label}
                        </td>
                        {compareData.map((fii, idx) => {
                          const val = row.extract(fii);
                          const isBest = idx === bestIdx && val != null;
                          return (
                            <td
                              key={fii.ticker}
                              className={`px-4 py-3 text-center font-mono text-sm ${
                                isBest
                                  ? "text-accent font-bold"
                                  : "text-foreground"
                              }`}
                            >
                              {row.format(val as number | null | undefined)}
                              {isBest && (
                                <span className="ml-1 text-[10px] text-accent/70">best</span>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Charts grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Radar chart */}
            <div className="glass-card p-6">
              <h2 className="font-semibold text-sm mb-4">Radar de Perfil</h2>
              <ResponsiveContainer width="100%" height={300}>
                <RadarChart data={radarData} outerRadius={100}>
                  <PolarGrid stroke="rgba(255,255,255,0.1)" />
                  <PolarAngleAxis
                    dataKey="dimension"
                    tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                  />
                  <PolarRadiusAxis
                    angle={90}
                    domain={[0, 100]}
                    tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 9 }}
                    tickCount={3}
                  />
                  {compareData.map((fii, idx) => (
                    <Radar
                      key={fii.ticker}
                      name={fii.ticker}
                      dataKey={fii.ticker}
                      stroke={FII_COLORS[idx % FII_COLORS.length]}
                      fill={FII_COLORS[idx % FII_COLORS.length]}
                      fillOpacity={0.12}
                      strokeWidth={2}
                    />
                  ))}
                  <Legend
                    wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "hsl(var(--background))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                      fontSize: "11px",
                    }}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            {/* Price history line chart */}
            <div className="glass-card p-6">
              <h2 className="font-semibold text-sm mb-4">Histórico de Preços (12M)</h2>
              {priceChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={priceChartData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                    <XAxis
                      dataKey="month"
                      tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(v: string) => v.slice(5)} // "MM" from "YYYY-MM"
                    />
                    <YAxis
                      tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(v: number) => `R$${v.toFixed(0)}`}
                      width={52}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "hsl(var(--background))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "8px",
                        fontSize: "11px",
                      }}
                      formatter={(val: number, name: string) => [`R$ ${val.toFixed(2)}`, name]}
                    />
                    <Legend
                      wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }}
                    />
                    {compareData.map((fii, idx) => (
                      <Line
                        key={fii.ticker}
                        type="monotone"
                        dataKey={fii.ticker}
                        stroke={FII_COLORS[idx % FII_COLORS.length]}
                        strokeWidth={2}
                        dot={false}
                        connectNulls
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">
                  Histórico de preços indisponível
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
