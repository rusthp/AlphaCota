import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Activity, TrendingUp, TrendingDown, DollarSign, Zap,
  AlertTriangle, CheckCircle2, XCircle, RefreshCw, Power,
  BarChart2, Wallet, Clock, ShieldAlert, ArrowUpRight, ArrowDownRight,
  LineChart as LineChartIcon, Users, Star,
} from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, LineChart, Line, Legend,
} from "recharts";

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

function getAuthHeader(): Record<string, string> {
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface LoopStatus {
  running: boolean;
  mode: string;
  uptime_seconds: number | null;
  kill_switch_active: boolean;
}

interface LiveStatus {
  mode: string;
  usdc_balance: number;
  daily_realized_pnl: number;
  open_positions: number;
  wallet_healthy: boolean;
}

interface Position {
  position_id: string;
  condition_id: string;
  direction: string;
  size_usd: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  mode: string;
  opened_at: number;
}

interface Order {
  order_id: string;
  market_id: string;
  question: string;
  direction: string;
  size_usd: number;
  fill_price: number | null;
  status: string;
  mode: string;
  created_at: number;
}

interface PnlSnapshot {
  date: string;
  equity_usd: number;
  open_positions: number;
  daily_pnl: number;
  mode: string;
}

interface WalletRank {
  address: string;
  alpha_score: number;
  win_rate: number;
  resolved_count: number;
  last_active: number;
  rank_change: "promoted" | "demoted" | "stable";
}

interface PriceHistorySeries {
  ts: number;
  [outcome: string]: number;
}

interface MarketPriceHistory {
  condition_id: string;
  question: string;
  outcomes: string[];
  series: PriceHistorySeries[];
}

interface CalibrationBin {
  bin_low: number;
  bin_high: number;
  predicted_prob: number;
  actual_win_rate: number;
  count: number;
}

interface Calibration {
  overall_brier: number;
  overall_win_rate: number;
  total_resolved: number;
  lookback_days: number;
  reliability_bins: CalibrationBin[];
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatusBadge({ running, mode, kill }: { running: boolean; mode: string; kill: boolean }) {
  if (kill) return <Badge variant="destructive" className="gap-1"><ShieldAlert className="w-3 h-3" /> Kill-switch ativo</Badge>;
  if (!running) return <Badge variant="secondary" className="gap-1"><XCircle className="w-3 h-3" /> Parado</Badge>;
  if (mode === "live") return <Badge className="bg-green-600 hover:bg-green-600 gap-1"><Zap className="w-3 h-3" /> Live</Badge>;
  return <Badge className="bg-blue-600 hover:bg-blue-600 gap-1"><Activity className="w-3 h-3" /> Paper</Badge>;
}

function PnlBadge({ value }: { value: number }) {
  if (value > 0) return <span className="text-green-400 flex items-center gap-1"><ArrowUpRight className="w-4 h-4" />${value.toFixed(2)}</span>;
  if (value < 0) return <span className="text-red-400 flex items-center gap-1"><ArrowDownRight className="w-4 h-4" />-${Math.abs(value).toFixed(2)}</span>;
  return <span className="text-muted-foreground">$0.00</span>;
}

function formatAge(ts: number): string {
  const diff = Math.floor((Date.now() / 1000) - ts);
  if (diff < 60) return `${diff}s atrás`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m atrás`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h atrás`;
  return `${Math.floor(diff / 86400)}d atrás`;
}

function formatUptime(seconds: number | null): string {
  if (!seconds) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

// ---------------------------------------------------------------------------
// Sections
// ---------------------------------------------------------------------------

function OverviewCards({ live, status }: { live: LiveStatus; status: LoopStatus }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <Card>
        <CardContent className="pt-5">
          <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1"><Wallet className="w-3 h-3" /> Saldo USDC</div>
          <div className="text-2xl font-bold">${live.usdc_balance.toFixed(2)}</div>
          <div className="text-xs mt-1">{live.wallet_healthy ? <span className="text-green-400 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" />Wallet OK</span> : <span className="text-red-400 flex items-center gap-1"><AlertTriangle className="w-3 h-3" />Wallet inválida</span>}</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-5">
          <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1"><DollarSign className="w-3 h-3" /> PnL Hoje</div>
          <div className="text-2xl font-bold"><PnlBadge value={live.daily_realized_pnl} /></div>
          <div className="text-xs text-muted-foreground mt-1">Realizado</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-5">
          <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1"><BarChart2 className="w-3 h-3" /> Posições abertas</div>
          <div className="text-2xl font-bold">{live.open_positions}</div>
          <div className="text-xs text-muted-foreground mt-1">Modo: {live.mode}</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-5">
          <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1"><Clock className="w-3 h-3" /> Uptime</div>
          <div className="text-2xl font-bold">{formatUptime(status.uptime_seconds)}</div>
          <div className="text-xs mt-1"><StatusBadge running={status.running} mode={status.mode} kill={status.kill_switch_active} /></div>
        </CardContent>
      </Card>
    </div>
  );
}

function PositionsTable({ positions }: { positions: Position[] }) {
  if (positions.length === 0)
    return <div className="text-center text-muted-foreground py-12">Nenhuma posição aberta</div>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border/40 text-muted-foreground text-xs">
            <th className="text-left py-2 pr-4">Mercado</th>
            <th className="text-left py-2 pr-4">Direção</th>
            <th className="text-right py-2 pr-4">Tamanho</th>
            <th className="text-right py-2 pr-4">Entrada</th>
            <th className="text-right py-2 pr-4">Atual</th>
            <th className="text-right py-2 pr-4">PnL</th>
            <th className="text-right py-2">Aberta</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.position_id} className="border-b border-border/20 hover:bg-muted/30">
              <td className="py-2 pr-4 font-mono text-xs">{p.condition_id.slice(0, 12)}…</td>
              <td className="py-2 pr-4">
                {p.direction === "YES"
                  ? <Badge className="bg-green-600/20 text-green-400 border-green-600/30">YES</Badge>
                  : <Badge className="bg-red-600/20 text-red-400 border-red-600/30">NO</Badge>}
              </td>
              <td className="py-2 pr-4 text-right">${p.size_usd.toFixed(2)}</td>
              <td className="py-2 pr-4 text-right">{(p.entry_price * 100).toFixed(1)}¢</td>
              <td className="py-2 pr-4 text-right">{(p.current_price * 100).toFixed(1)}¢</td>
              <td className="py-2 pr-4 text-right"><PnlBadge value={p.unrealized_pnl} /></td>
              <td className="py-2 text-right text-muted-foreground text-xs">{formatAge(p.opened_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OrdersTable({ orders }: { orders: Order[] }) {
  if (orders.length === 0)
    return <div className="text-center text-muted-foreground py-12">Nenhuma ordem registrada</div>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border/40 text-muted-foreground text-xs">
            <th className="text-left py-2 pr-4">Pergunta</th>
            <th className="text-left py-2 pr-4">Direção</th>
            <th className="text-right py-2 pr-4">Tamanho</th>
            <th className="text-right py-2 pr-4">Fill</th>
            <th className="text-left py-2 pr-4">Status</th>
            <th className="text-right py-2">Criada</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.order_id} className="border-b border-border/20 hover:bg-muted/30">
              <td className="py-2 pr-4 max-w-xs">
                {o.question
                  ? <span className="line-clamp-2 text-xs leading-relaxed">{o.question}</span>
                  : <span className="font-mono text-xs text-muted-foreground">{o.market_id.slice(0, 14)}…</span>}
              </td>
              <td className="py-2 pr-4">
                {o.direction.toUpperCase() === "YES"
                  ? <Badge className="bg-green-600/20 text-green-400 border-green-600/30">YES</Badge>
                  : <Badge className="bg-red-600/20 text-red-400 border-red-600/30">NO</Badge>}
              </td>
              <td className="py-2 pr-4 text-right font-mono">${o.size_usd.toFixed(2)}</td>
              <td className="py-2 pr-4 text-right font-mono">{o.fill_price != null ? `${(o.fill_price * 100).toFixed(1)}¢` : "—"}</td>
              <td className="py-2 pr-4">
                <Badge
                  variant={o.status === "filled" ? "default" : o.status === "cancelled" ? "secondary" : "outline"}
                  className={`text-xs ${o.status === "filled" ? "bg-green-600/20 text-green-400 border-green-600/30" : ""}`}
                >
                  {o.status}
                </Badge>
              </td>
              <td className="py-2 text-right text-muted-foreground text-xs whitespace-nowrap">{formatAge(o.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PnlHistory({ snapshots }: { snapshots: PnlSnapshot[] }) {
  if (snapshots.length === 0)
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-3">
        <BarChart2 className="w-10 h-10 opacity-30" />
        <p className="text-sm">Nenhum dado ainda — inicie o loop para gerar histórico</p>
        <code className="text-xs bg-muted px-3 py-1 rounded">python -m core.polymarket_loop --mode paper</code>
      </div>
    );

  const sorted = [...snapshots].reverse();
  const startEquity = sorted[0]?.equity_usd ?? 0;
  const totalPnl = sorted.reduce((a, s) => a + s.daily_pnl, 0);
  const bestDay = Math.max(...sorted.map((s) => s.daily_pnl));
  const worstDay = Math.min(...sorted.map((s) => s.daily_pnl));
  const positiveDays = sorted.filter((s) => s.daily_pnl > 0).length;

  const chartData = sorted.map((s) => ({
    date: s.date.slice(5), // MM-DD
    equity: s.equity_usd,
    pnl: s.daily_pnl,
  }));

  const isUp = totalPnl >= 0;
  const strokeColor = isUp ? "#22c55e" : "#ef4444";
  const fillColor = isUp ? "#22c55e" : "#ef4444";

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    return (
      <div className="bg-popover border border-border rounded px-3 py-2 text-xs space-y-1 shadow-lg">
        <div className="font-medium">{label}</div>
        <div className="flex justify-between gap-4">
          <span className="text-muted-foreground">Saldo</span>
          <span className="font-mono">${d.equity.toFixed(2)}</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-muted-foreground">PnL dia</span>
          <span className={`font-mono ${d.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
            {d.pnl >= 0 ? "+" : ""}${d.pnl.toFixed(2)}
          </span>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Equity curve */}
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={fillColor} stopOpacity={0.25} />
                <stop offset="95%" stopColor={fillColor} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#888" }} tickLine={false} axisLine={false} />
            <YAxis
              tick={{ fontSize: 10, fill: "#888" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `$${v}`}
              width={55}
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine y={startEquity} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 4" />
            <Area
              type="monotone"
              dataKey="equity"
              stroke={strokeColor}
              strokeWidth={2}
              fill="url(#equityGrad)"
              dot={false}
              activeDot={{ r: 4, fill: strokeColor }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-2 border-t border-border/30">
        <div>
          <div className="text-muted-foreground text-xs mb-1">PnL acumulado</div>
          <PnlBadge value={totalPnl} />
        </div>
        <div>
          <div className="text-muted-foreground text-xs mb-1">Dias positivos</div>
          <span className="text-green-400 font-medium">{positiveDays}</span>
          <span className="text-muted-foreground text-sm"> / {sorted.length}</span>
        </div>
        <div>
          <div className="text-muted-foreground text-xs mb-1">Melhor dia</div>
          <PnlBadge value={bestDay} />
        </div>
        <div>
          <div className="text-muted-foreground text-xs mb-1">Pior dia</div>
          <PnlBadge value={worstDay} />
        </div>
      </div>
    </div>
  );
}

// Colour palette for outcome lines — matches native Polymarket chart feel
const OUTCOME_COLORS = [
  "#3b82f6", // blue
  "#f97316", // orange
  "#22c55e", // green
  "#a855f7", // purple
  "#ec4899", // pink
  "#14b8a6", // teal
  "#eab308", // yellow
  "#ef4444", // red
];

function MarketPriceCard({ conditionId }: { conditionId: string }) {
  const [interval, setInterval] = useState<string>("max");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["pm-price-history", conditionId, interval],
    queryFn: () =>
      fetchJSON<MarketPriceHistory>(`/api/polymarket/price-history/${conditionId}?interval=${interval}`),
    staleTime: 60_000,
  });

  const INTERVALS = ["1d", "1w", "1m", "6m", "1y", "max"];

  const formatTs = (ts: number) => {
    const d = new Date(ts * 1000);
    return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  };

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const ts = payload[0]?.payload?.ts;
    const dateStr = ts ? new Date(ts * 1000).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit" }) : label;
    return (
      <div className="bg-popover border border-border rounded px-3 py-2 text-xs space-y-1 shadow-lg min-w-[140px]">
        <div className="font-medium text-muted-foreground">{dateStr}</div>
        {payload.map((p: any) => (
          <div key={p.dataKey} className="flex justify-between gap-4">
            <span style={{ color: p.color }}>{p.dataKey}</span>
            <span className="font-mono font-medium">{p.value?.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2 flex-wrap">
          <CardTitle className="text-sm font-medium leading-snug max-w-xl">
            {isLoading ? (
              <span className="text-muted-foreground font-mono text-xs">{conditionId.slice(0, 16)}…</span>
            ) : isError ? (
              <span className="text-destructive text-xs">Erro ao carregar mercado</span>
            ) : (
              data?.question || conditionId.slice(0, 32)
            )}
          </CardTitle>
          <div className="flex gap-1 flex-shrink-0">
            {INTERVALS.map((iv) => (
              <button
                key={iv}
                onClick={() => setInterval(iv)}
                className={`text-xs px-2 py-0.5 rounded ${
                  interval === iv
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-muted/80"
                }`}
              >
                {iv}
              </button>
            ))}
          </div>
        </div>
        {data?.outcomes && (
          <div className="flex flex-wrap gap-2 pt-1 items-center">
            {data.outcomes.map((o, i) => {
              // Show current probability (last series point) next to the label
              const lastPoint = data.series.length > 0 ? data.series[data.series.length - 1] : null;
              const currentPct = lastPoint ? (lastPoint as Record<string, number>)[o] : null;
              return (
                <span
                  key={o}
                  className="text-xs px-2 py-0.5 rounded-full font-medium flex items-center gap-1"
                  style={{ backgroundColor: OUTCOME_COLORS[i % OUTCOME_COLORS.length] + "22", color: OUTCOME_COLORS[i % OUTCOME_COLORS.length] }}
                >
                  {o}
                  {currentPct !== null && (
                    <span className="font-mono font-bold">{currentPct.toFixed(1)}%</span>
                  )}
                </span>
              );
            })}
            {/* For binary markets only the primary outcome is shown — note the implied complement */}
            {data.outcomes.length === 1 && data.series.length > 0 && (() => {
              const last = data.series[data.series.length - 1] as Record<string, number>;
              const primaryPct = last[data.outcomes[0]] ?? 0;
              const complementPct = Math.max(0, 100 - primaryPct);
              return (
                <span className="text-xs px-2 py-0.5 rounded-full font-medium flex items-center gap-1"
                  style={{ backgroundColor: OUTCOME_COLORS[1] + "22", color: OUTCOME_COLORS[1] }}>
                  No <span className="font-mono font-bold">{complementPct.toFixed(1)}%</span>
                </span>
              );
            })()}
          </div>
        )}
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="h-40 flex items-center justify-center text-muted-foreground text-xs">
            Carregando histórico...
          </div>
        )}
        {isError && (
          <div className="h-40 flex items-center justify-center text-destructive text-xs">
            Falha ao buscar dados do Polymarket
          </div>
        )}
        {data && data.series.length === 0 && (
          <div className="h-40 flex items-center justify-center text-muted-foreground text-xs">
            Sem dados de preço para este período
          </div>
        )}
        {data && data.series.length > 0 && (() => {
          // Compute dynamic Y domain with padding so lines aren't glued to edges
          const allValues = data.series.flatMap((row) =>
            data.outcomes.map((o) => (row as Record<string, number>)[o] ?? null).filter((v) => v !== null) as number[]
          );
          const minVal = Math.max(0, Math.floor(Math.min(...allValues) - 5));
          const maxVal = Math.min(100, Math.ceil(Math.max(...allValues) + 5));
          const showRef50 = minVal < 50 && maxVal > 50;

          return (
            <div className="h-52">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.series} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
                  <XAxis
                    dataKey="ts"
                    tickFormatter={formatTs}
                    tick={{ fontSize: 9, fill: "#666" }}
                    tickLine={false}
                    axisLine={false}
                    interval="preserveStartEnd"
                    minTickGap={40}
                  />
                  <YAxis
                    domain={[minVal, maxVal]}
                    tick={{ fontSize: 9, fill: "#666" }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => `${v}%`}
                    width={38}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  {showRef50 && (
                    <ReferenceLine y={50} stroke="rgba(255,255,255,0.12)" strokeDasharray="4 4" />
                  )}
                  {data.outcomes.map((outcome, i) => (
                    <Line
                      key={outcome}
                      type="linear"
                      dataKey={outcome}
                      stroke={OUTCOME_COLORS[i % OUTCOME_COLORS.length]}
                      strokeWidth={1.5}
                      dot={false}
                      activeDot={{ r: 3, strokeWidth: 0 }}
                      connectNulls
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          );
        })()}
      </CardContent>
    </Card>
  );
}

function MarketCharts({ conditionIds }: { conditionIds: string[] }) {
  if (conditionIds.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-3">
        <LineChartIcon className="w-10 h-10 opacity-30" />
        <p className="text-sm">Nenhum mercado rastreado ainda</p>
        <p className="text-xs opacity-60">Os gráficos aparecerão quando o loop abrir posições ou ordens</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {conditionIds.map((cid) => (
        <MarketPriceCard key={cid} conditionId={cid} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Simulation modal
// ---------------------------------------------------------------------------

interface SimTrade { date: string; market_id: string; outcome: string; side: string; bet_usd: number; pnl: number; equity: number; }
interface SimResult { address: string; bankroll: number; total_trades: number; wins: number; win_rate: number; total_pnl: number; final_equity: number; roi_pct: number; equity_curve: { date: string; equity: number }[]; trades: SimTrade[]; }

function SimModal({ address, onClose }: { address: string; onClose: () => void }) {
  const [bankroll, setBankroll] = useState(100);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["pm-sim", address, bankroll],
    queryFn: () => fetchJSON<SimResult>(`/api/polymarket/wallets/${address}/simulate?bankroll=${bankroll}`),
    enabled: true,
    staleTime: 60_000,
  });

  const isUp = (data?.total_pnl ?? 0) >= 0;
  const strokeColor = isUp ? "#22c55e" : "#ef4444";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="bg-background border border-border rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between p-4 border-b border-border/40">
          <div>
            <h2 className="font-semibold text-sm">Simulação de cópia</h2>
            <p className="text-muted-foreground text-xs font-mono mt-0.5">{address.slice(0, 10)}…{address.slice(-8)}</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-lg leading-none">✕</button>
        </div>

        <div className="p-4 space-y-4">
          {/* Bankroll input */}
          <div className="flex items-center gap-3">
            <label className="text-xs text-muted-foreground w-24 flex-shrink-0">Banca inicial</label>
            <div className="flex gap-2">
              {[50, 100, 250, 500, 1000].map(v => (
                <button key={v} onClick={() => setBankroll(v)}
                  className={`text-xs px-3 py-1 rounded ${bankroll === v ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/80"}`}>
                  ${v}
                </button>
              ))}
            </div>
          </div>

          {isLoading && <div className="text-center text-muted-foreground py-8 text-sm">Simulando...</div>}

          {data && (
            <>
              {/* Stats */}
              <div className="grid grid-cols-4 gap-3">
                {[
                  { label: "PnL total", value: `${data.total_pnl >= 0 ? "+" : ""}$${data.total_pnl.toFixed(2)}`, color: data.total_pnl >= 0 ? "text-green-400" : "text-red-400" },
                  { label: "ROI", value: `${data.roi_pct >= 0 ? "+" : ""}${data.roi_pct.toFixed(1)}%`, color: data.roi_pct >= 0 ? "text-green-400" : "text-red-400" },
                  { label: "Win Rate", value: `${(data.win_rate * 100).toFixed(1)}%`, color: data.win_rate >= 0.6 ? "text-green-400" : "text-yellow-400" },
                  { label: "Operações", value: `${data.wins}/${data.total_trades}`, color: "text-foreground" },
                ].map(s => (
                  <div key={s.label} className="bg-muted/40 rounded-lg p-3 text-center">
                    <div className="text-muted-foreground text-[10px] mb-1">{s.label}</div>
                    <div className={`text-sm font-bold ${s.color}`}>{s.value}</div>
                  </div>
                ))}
              </div>

              {/* Equity curve */}
              {data.equity_curve.length > 1 && (
                <div className="h-40">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={data.equity_curve} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="simGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={strokeColor} stopOpacity={0.25} />
                          <stop offset="95%" stopColor={strokeColor} stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                      <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#888" }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                      <YAxis tick={{ fontSize: 9, fill: "#888" }} tickLine={false} axisLine={false} tickFormatter={v => `$${v}`} width={50} />
                      <Tooltip formatter={(v: number) => [`$${v.toFixed(2)}`, "Saldo"]} />
                      <ReferenceLine y={bankroll} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 4" />
                      <Area type="monotone" dataKey="equity" stroke={strokeColor} strokeWidth={2} fill="url(#simGrad)" dot={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Last trades */}
              <div>
                <p className="text-xs font-medium mb-2">Últimas operações (simuladas)</p>
                <div className="space-y-1 max-h-48 overflow-y-auto">
                  {[...data.trades].reverse().map((t, i) => (
                    <div key={i} className="flex items-center justify-between text-xs px-2 py-1 rounded hover:bg-muted/30">
                      <span className="text-muted-foreground w-14 flex-shrink-0">{t.date.slice(5)}</span>
                      <span className="flex-1 truncate text-muted-foreground text-[11px]">{t.outcome}</span>
                      <Badge className={`text-[10px] mx-2 ${t.side === "YES" ? "bg-green-600/20 text-green-400 border-green-600/30" : "bg-red-600/20 text-red-400 border-red-600/30"}`}>{t.side}</Badge>
                      <span className="font-mono w-16 text-right text-muted-foreground">${t.bet_usd.toFixed(2)}</span>
                      <span className={`font-mono w-16 text-right ${t.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                        {t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(2)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Wallets panel
// ---------------------------------------------------------------------------

function WalletsPanel({ wallets, onSeed, seeding }: { wallets: WalletRank[]; onSeed: () => void; seeding: boolean }) {
  const qc = useQueryClient();
  const [sortBy, setSortBy] = useState<"alpha_score" | "win_rate" | "resolved_count">("alpha_score");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  const [simAddress, setSimAddress] = useState<string | null>(null);
  const [followed, setFollowed] = useState<Set<string>>(new Set());

  // Load followed wallets
  const followedQ = useQuery({
    queryKey: ["pm-followed"],
    queryFn: () => fetchJSON<{ followed: { address: string }[] }>("/api/polymarket/wallets/followed"),
    staleTime: 30_000,
  });
  const followedSet = new Set(followedQ.data?.followed.map(f => f.address) ?? []);

  const followMut = useMutation({
    mutationFn: (addr: string) => fetchJSON(`/api/polymarket/wallets/${addr}/follow`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pm-followed"] }),
  });
  const unfollowMut = useMutation({
    mutationFn: (addr: string) => fetchJSON(`/api/polymarket/wallets/${addr}/follow`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pm-followed"] }),
  });

  const toggleSort = (col: typeof sortBy) => {
    if (sortBy === col) setSortDir(d => d === "desc" ? "asc" : "desc");
    else { setSortBy(col); setSortDir("desc"); }
  };

  const sorted = [...wallets].sort((a, b) => {
    const diff = a[sortBy] - b[sortBy];
    return sortDir === "desc" ? -diff : diff;
  });

  const SortHeader = ({ col, label }: { col: typeof sortBy; label: string }) => (
    <button onClick={() => toggleSort(col)} className="flex items-center gap-0.5 hover:text-foreground transition-colors ml-auto">
      {label}
      <span className="text-[10px]">{sortBy === col ? (sortDir === "desc" ? " ↓" : " ↑") : " ↕"}</span>
    </button>
  );

  const rankColor = (c: string) => c === "promoted" ? "text-green-400" : c === "demoted" ? "text-red-400" : "text-muted-foreground";
  const rankLabel = (c: string) => c === "promoted" ? "▲" : c === "demoted" ? "▼" : "—";

  if (wallets.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-3">
        <Users className="w-10 h-10 opacity-30" />
        <p className="text-sm">Nenhuma wallet rastreada ainda</p>
        <p className="text-xs opacity-60 text-center max-w-xs">
          Clique em "Descobrir wallets" para escanear mercados resolvidos e encontrar os melhores traders
        </p>
        <Button size="sm" onClick={onSeed} disabled={seeding} className="mt-2">
          {seeding ? <><RefreshCw className="w-3 h-3 mr-1 animate-spin" />Escaneando...</> : <><Users className="w-3 h-3 mr-1" />Descobrir wallets</>}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {simAddress && <SimModal address={simAddress} onClose={() => setSimAddress(null)} />}

      <div className="flex justify-between items-center">
        <p className="text-xs text-muted-foreground">{wallets.length} wallets elegíveis · clique no cabeçalho para ordenar</p>
        <Button size="sm" variant="outline" onClick={onSeed} disabled={seeding}>
          {seeding ? <><RefreshCw className="w-3 h-3 mr-1 animate-spin" />Escaneando...</> : <><RefreshCw className="w-3 h-3 mr-1" />Atualizar</>}
        </Button>
      </div>

      {/* Header */}
      <div className="grid grid-cols-12 text-xs text-muted-foreground px-2 pb-1 border-b border-border/30 gap-1">
        <span className="col-span-4">Wallet</span>
        <span className="col-span-2 flex justify-end"><SortHeader col="alpha_score" label="Score" /></span>
        <span className="col-span-2 flex justify-end"><SortHeader col="win_rate" label="Win Rate" /></span>
        <span className="col-span-2 flex justify-end"><SortHeader col="resolved_count" label="Trades" /></span>
        <span className="col-span-2 text-right">Ações</span>
      </div>

      {sorted.map((w, i) => {
        const isFollowed = followedSet.has(w.address);
        return (
          <div key={w.address} className="grid grid-cols-12 items-center gap-1 px-2 py-2 rounded hover:bg-muted/30 border border-border/10">
            {/* Address + rank badge */}
            <div className="col-span-4 flex items-center gap-2 min-w-0">
              <span className="text-muted-foreground text-xs w-4 flex-shrink-0">#{i + 1}</span>
              <span className={`text-[10px] flex-shrink-0 ${rankColor(w.rank_change)}`}>{rankLabel(w.rank_change)}</span>
              <span className="font-mono text-xs truncate">{w.address.slice(0, 7)}…{w.address.slice(-5)}</span>
            </div>

            {/* Alpha score */}
            <div className="col-span-2 flex items-center justify-end gap-1">
              <Star className="w-3 h-3 text-yellow-400 flex-shrink-0" />
              <span className="font-mono text-xs">{(w.alpha_score * 100).toFixed(0)}</span>
            </div>

            {/* Win rate */}
            <div className="col-span-2 text-right">
              <span className={`text-xs font-medium ${w.win_rate >= 0.65 ? "text-green-400" : w.win_rate < 0.55 ? "text-red-400" : "text-yellow-400"}`}>
                {(w.win_rate * 100).toFixed(1)}%
              </span>
            </div>

            {/* Trade count */}
            <div className="col-span-2 text-right text-xs text-muted-foreground">{w.resolved_count}</div>

            {/* Actions */}
            <div className="col-span-2 flex items-center justify-end gap-1">
              <button
                title="Simular cópia"
                onClick={() => setSimAddress(w.address)}
                className="text-xs px-2 py-0.5 rounded bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 border border-blue-600/30"
              >
                Sim
              </button>
              <button
                title={isFollowed ? "Parar de seguir" : "Seguir"}
                onClick={() => isFollowed ? unfollowMut.mutate(w.address) : followMut.mutate(w.address)}
                className={`text-xs px-2 py-0.5 rounded border ${isFollowed ? "bg-green-600/20 text-green-400 border-green-600/30 hover:bg-red-600/20 hover:text-red-400 hover:border-red-600/30" : "bg-muted text-muted-foreground border-border/40 hover:bg-green-600/20 hover:text-green-400 hover:border-green-600/30"}`}
              >
                {isFollowed ? "✓" : "+"}
              </button>
            </div>
          </div>
        );
      })}

      <p className="text-xs text-muted-foreground pt-1 border-t border-border/20">
        Win ≥65% = promovida (▲) · &lt;55% = rebaixada (▼) · mínimo 5 trades resolvidos nos últimos 30 dias
      </p>
    </div>
  );
}

function CalibrationPanel({ cal }: { cal: Calibration }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-4">
            <div className="text-xs text-muted-foreground mb-1">Brier Score</div>
            <div className="text-2xl font-bold">{cal.overall_brier.toFixed(4)}</div>
            <div className="text-xs text-muted-foreground">Menor = melhor (0 = perfeito)</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-xs text-muted-foreground mb-1">Win Rate</div>
            <div className="text-2xl font-bold">{(cal.overall_win_rate * 100).toFixed(1)}%</div>
            <div className="text-xs text-muted-foreground">{cal.total_resolved} mercados resolvidos</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-xs text-muted-foreground mb-1">Lookback</div>
            <div className="text-2xl font-bold">{cal.lookback_days}d</div>
            <div className="text-xs text-muted-foreground">janela de análise</div>
          </CardContent>
        </Card>
      </div>

      {cal.reliability_bins.length > 0 && (
        <div>
          <div className="text-sm font-medium mb-3">Calibração (previsto vs real)</div>
          <div className="space-y-2">
            {cal.reliability_bins.map((b, i) => (
              <div key={i} className="flex items-center gap-3 text-xs">
                <span className="w-20 text-muted-foreground">{(b.bin_low * 100).toFixed(0)}-{(b.bin_high * 100).toFixed(0)}%</span>
                <div className="flex-1 bg-muted rounded-full h-2 relative">
                  <div className="absolute h-2 bg-blue-500/60 rounded-full" style={{ width: `${b.predicted_prob * 100}%` }} />
                  <div className="absolute h-2 bg-green-500 rounded-full opacity-70" style={{ width: `${b.actual_win_rate * 100}%` }} />
                </div>
                <span className="w-24 text-right text-muted-foreground">{b.count} mercados</span>
              </div>
            ))}
            <div className="flex gap-4 text-xs text-muted-foreground pt-1">
              <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 bg-blue-500/60 rounded" /> Previsto</span>
              <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 bg-green-500 rounded" /> Real</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function PolymarketPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState("overview");

  const statusQ = useQuery({
    queryKey: ["pm-status"],
    queryFn: () => fetchJSON<LoopStatus>("/api/polymarket/status"),
    refetchInterval: 10000,
  });

  const liveQ = useQuery({
    queryKey: ["pm-live"],
    queryFn: () => fetchJSON<LiveStatus>("/api/polymarket/live-status"),
    refetchInterval: 15000,
  });

  const positionsQ = useQuery({
    queryKey: ["pm-positions"],
    queryFn: () => fetchJSON<{ positions: Position[] }>("/api/polymarket/positions"),
    refetchInterval: 30000,
  });

  const ordersQ = useQuery({
    queryKey: ["pm-orders"],
    queryFn: () => fetchJSON<{ orders: Order[] }>("/api/polymarket/orders"),
    refetchInterval: 30000,
  });

  const pnlQ = useQuery({
    queryKey: ["pm-pnl"],
    queryFn: () => fetchJSON<{ snapshots: PnlSnapshot[] }>("/api/polymarket/pnl"),
    refetchInterval: 60000,
  });

  const calQ = useQuery({
    queryKey: ["pm-calibration"],
    queryFn: () => fetchJSON<Calibration>("/api/polymarket/calibration"),
    refetchInterval: 120000,
  });

  const walletsQ = useQuery({
    queryKey: ["pm-wallets"],
    queryFn: () => fetchJSON<{ wallets: WalletRank[]; total: number }>("/api/polymarket/wallets"),
    refetchInterval: 300000, // 5 min — wallet data changes slowly
  });

  const killMutation = useMutation({
    mutationFn: () => fetchJSON("/api/polymarket/kill", { method: "POST", headers: getAuthHeader() }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pm-status"] }),
  });

  const seedMutation = useMutation({
    mutationFn: () => fetchJSON("/api/polymarket/wallets/seed?markets=100&min_size=5", { method: "POST" }),
    onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ["pm-wallets"] }), 5000),
  });

  const trendingQ = useQuery({
    queryKey: ["pm-trending-markets"],
    queryFn: () => fetchJSON<{ markets: { condition_id: string; question: string; volume_1wk: number }[] }>("/api/polymarket/trending-markets?limit=10"),
    staleTime: 300_000,
  });

  const status = statusQ.data;
  const live = liveQ.data;
  const isLoading = statusQ.isLoading || liveQ.isLoading;

  // Unique condition_ids: bot's open positions/orders first, then trending markets to fill up to 10
  const botConditionIds = Array.from(
    new Set([
      ...(ordersQ.data?.orders.map((o) => o.market_id) ?? []),
      ...(positionsQ.data?.positions.map((p) => p.condition_id) ?? []),
    ])
  );
  const trendingIds = (trendingQ.data?.markets ?? []).map((m) => m.condition_id);
  const trackedConditionIds = Array.from(new Set([...botConditionIds, ...trendingIds])).slice(0, 10);

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <TrendingUp className="w-6 h-6 text-blue-400" />
            Polymarket
          </h1>
          <p className="text-muted-foreground text-sm mt-1">Trading autônomo de mercados de predição</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => qc.invalidateQueries({ queryKey: ["pm-status", "pm-live", "pm-positions", "pm-orders"] })}
          >
            <RefreshCw className="w-3 h-3 mr-1" /> Atualizar
          </Button>
          {status && !status.kill_switch_active && (
            <Button
              variant="destructive"
              size="sm"
              onClick={() => { if (confirm("Ativar kill-switch? O loop vai parar no próximo ciclo.")) killMutation.mutate(); }}
              disabled={killMutation.isPending}
            >
              <Power className="w-3 h-3 mr-1" /> Kill-switch
            </Button>
          )}
        </div>
      </div>

      {isLoading && (
        <div className="text-center text-muted-foreground py-8">Carregando...</div>
      )}

      {status && live && (
        <>
          <OverviewCards live={live} status={status} />

          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="overview">Posições</TabsTrigger>
              <TabsTrigger value="orders">Ordens</TabsTrigger>
              <TabsTrigger value="markets">Mercados</TabsTrigger>
              <TabsTrigger value="pnl">PnL</TabsTrigger>
              <TabsTrigger value="wallets">Copiar</TabsTrigger>
              <TabsTrigger value="calibration">Calibração</TabsTrigger>
            </TabsList>

            <TabsContent value="overview">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Activity className="w-4 h-4" /> Posições abertas ({positionsQ.data?.positions.length ?? 0})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <PositionsTable positions={positionsQ.data?.positions ?? []} />
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="orders">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <BarChart2 className="w-4 h-4" /> Histórico de ordens ({ordersQ.data?.orders.length ?? 0})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <OrdersTable orders={ordersQ.data?.orders ?? []} />
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="markets">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <LineChartIcon className="w-4 h-4" />
                    Evolução de probabilidade
                    <span className="text-xs font-normal text-muted-foreground ml-1">
                      {botConditionIds.length > 0
                        ? `${botConditionIds.length} abertos pelo bot · ${trackedConditionIds.length - botConditionIds.length} trending`
                        : `${trackedConditionIds.length} mercados trending`}
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <MarketCharts conditionIds={trackedConditionIds} />
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="pnl">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <DollarSign className="w-4 h-4" /> Histórico de PnL (últimos 90 dias)
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <PnlHistory snapshots={pnlQ.data?.snapshots ?? []} />
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="wallets">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Users className="w-4 h-4" /> Wallets alpha ({walletsQ.data?.total ?? 0} rastreadas)
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {walletsQ.isLoading && (
                    <div className="text-center text-muted-foreground py-8 text-sm">Carregando wallets...</div>
                  )}
                  {walletsQ.isError && (
                    <div className="text-center text-destructive py-8 text-sm">Erro ao carregar wallets</div>
                  )}
                  {walletsQ.data && (
                    <WalletsPanel
                      wallets={walletsQ.data.wallets}
                      onSeed={() => seedMutation.mutate()}
                      seeding={seedMutation.isPending}
                    />
                  )}
                  {!walletsQ.data && !walletsQ.isLoading && !walletsQ.isError && (
                    <WalletsPanel wallets={[]} onSeed={() => seedMutation.mutate()} seeding={seedMutation.isPending} />
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="calibration">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4" /> Calibração do modelo
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {calQ.data ? <CalibrationPanel cal={calQ.data} /> : <div className="text-muted-foreground text-center py-8">Sem dados de calibração ainda</div>}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  );
}
