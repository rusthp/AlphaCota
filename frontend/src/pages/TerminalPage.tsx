/**
 * TerminalPage.tsx — Bloomberg-style terminal for Polymarket bot control.
 *
 * Layout:
 *   TOP BAR   — mode, balance, P&L, positions count, clock
 *   LEFT COL  — open positions + equity sparkline + bot signals queue
 *   RIGHT COL — trending markets with live prices + volume bars
 *   BOTTOM    — log feed + keyboard shortcuts
 */

import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const API = (path: string) =>
  fetch(path).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  });

function getAuthHeader() {
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function fmt$(n: number, decimals = 2) {
  const abs = Math.abs(n).toFixed(decimals);
  return `${n >= 0 ? "+" : "-"}$${abs}`;
}

function fmtPct(n: number) {
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function fmtVol(n: number) {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

function useNow() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

// ASCII sparkline from array of numbers
function sparkline(values: number[], width = 20): string {
  if (values.length === 0) return "─".repeat(width);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const blocks = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"];
  // Downsample to width
  const step = values.length / width;
  return Array.from({ length: width }, (_, i) => {
    const idx = Math.min(Math.floor(i * step), values.length - 1);
    const v = values[idx];
    const level = Math.round(((v - min) / range) * (blocks.length - 1));
    return blocks[level];
  }).join("");
}

// Horizontal bar (0–100)
function bar(pct: number, width = 22): string {
  const filled = Math.round((pct / 100) * width);
  return "█".repeat(filled) + "░".repeat(width - filled);
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Position {
  condition_id: string;
  question: string;
  side: string;
  size_usd: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pct: number;
}

interface PnlSnapshot {
  date: string;
  equity_usd: number;
  daily_pnl: number;
}

interface LiveStatus {
  mode: string;
  usdc_balance: number;
  daily_realized_pnl: number;
  open_positions: number;
  wallet_healthy: boolean;
}

interface BotStatus {
  running: boolean;
  mode: string;
  kill_switch_active: boolean;
}

interface TrendingMarket {
  condition_id: string;
  question: string;
  volume_1wk: number;
  outcomes: string[];
  prices: number[];
}

// ---------------------------------------------------------------------------
// Sub-components — all rendered as styled <pre>/<div> blocks
// ---------------------------------------------------------------------------

function TBar({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <span className="mr-4">
      <span className="text-[#4a5568]">{label}:</span>
      <span className={`ml-1 font-bold ${color}`}>{value}</span>
    </span>
  );
}

function SectionHeader({ title }: { title: string }) {
  return (
    <div className="text-[10px] font-bold tracking-widest text-[#4a9eff] border-b border-[#1a2a3a] pb-0.5 mb-1">
      ── {title} {"─".repeat(Math.max(0, 40 - title.length - 4))}
    </div>
  );
}

function PositionRow({ pos }: { pos: Position }) {
  const pnlColor = pos.unrealized_pnl >= 0 ? "text-[#00ff88]" : "text-[#ff4444]";
  const sideColor = pos.side === "YES" ? "text-[#4a9eff]" : "text-[#ff9900]";
  const short = pos.question.length > 28 ? pos.question.slice(0, 27) + "…" : pos.question.padEnd(28);
  return (
    <div className="flex gap-2 text-[11px] font-mono leading-5">
      <span className="text-[#888] w-[180px] truncate">{short}</span>
      <span className={`w-8 font-bold ${sideColor}`}>{pos.side}</span>
      <span className="text-[#ccc] w-14 text-right">${pos.size_usd.toFixed(0)}</span>
      <span className={`w-16 text-right font-bold ${pnlColor}`}>
        {fmt$(pos.unrealized_pnl, 2)}
      </span>
      <span className={`w-14 text-right ${pnlColor}`}>{fmtPct(pos.unrealized_pct * 100)}</span>
    </div>
  );
}

function MarketRow({ mkt, idx }: { mkt: TrendingMarket; idx: number }) {
  // Primary outcome = first one (YES or first candidate)
  const outcome = mkt.outcomes[0] ?? "?";
  const price = mkt.prices[0] ?? 0;
  const priceColor =
    price >= 70 ? "text-[#00ff88]" : price >= 40 ? "text-[#ffcc00]" : "text-[#ff4444]";
  const short = mkt.question.length > 34 ? mkt.question.slice(0, 33) + "…" : mkt.question;

  return (
    <div className="flex items-center gap-2 text-[10px] font-mono leading-5">
      <span className="text-[#4a5568] w-4">{String(idx + 1).padStart(2)}.</span>
      <span className="text-[#aaa] w-[220px] truncate">{short}</span>
      <span className={`w-8 font-bold ${priceColor}`}>{price.toFixed(0)}%</span>
      <span className="text-[#2a4a2a] w-[100px] font-mono text-[8px] leading-5">
        {bar(price, 16)}
      </span>
      <span className="text-[#4a5568] w-14 text-right">{fmtVol(mkt.volume_1wk)}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function TerminalPage() {
  const qc = useQueryClient();
  const now = useNow();
  const logRef = useRef<HTMLDivElement>(null);
  const [logs, setLogs] = useState<{ ts: string; msg: string; level: "info" | "ok" | "warn" | "err" }[]>([
    { ts: now.toLocaleTimeString("pt-BR"), msg: "AlphaCota Terminal iniciado", level: "info" },
  ]);

  const pushLog = (msg: string, level: "info" | "ok" | "warn" | "err" = "info") => {
    setLogs((prev) => [
      ...prev.slice(-80),
      { ts: new Date().toLocaleTimeString("pt-BR"), msg, level },
    ]);
    setTimeout(() => logRef.current?.scrollTo(0, logRef.current.scrollHeight), 50);
  };

  // Queries
  const liveQ = useQuery<LiveStatus>({
    queryKey: ["term-live"],
    queryFn: () => API("/api/polymarket/live-status"),
    refetchInterval: 5000,
  });

  const statusQ = useQuery<BotStatus>({
    queryKey: ["term-status"],
    queryFn: () => API("/api/polymarket/status"),
    refetchInterval: 5000,
  });

  const positionsQ = useQuery<{ positions: Position[] }>({
    queryKey: ["term-positions"],
    queryFn: () => API("/api/polymarket/positions"),
    refetchInterval: 8000,
  });

  const pnlQ = useQuery<{ snapshots: PnlSnapshot[] }>({
    queryKey: ["term-pnl"],
    queryFn: () => API("/api/polymarket/pnl"),
    refetchInterval: 30000,
  });

  const trendingQ = useQuery<{ markets: TrendingMarket[] }>({
    queryKey: ["term-trending"],
    queryFn: () => API("/api/polymarket/trending-markets?limit=12"),
    staleTime: 120_000,
    refetchInterval: 120_000,
  });

  const killMut = useMutation({
    mutationFn: () =>
      fetch("/api/polymarket/kill", { method: "POST", headers: getAuthHeader() }).then((r) => r.json()),
    onSuccess: () => {
      pushLog("Kill switch ativado", "warn");
      qc.invalidateQueries({ queryKey: ["term-status"] });
    },
  });

  // Log on status changes
  useEffect(() => {
    if (statusQ.data?.running) pushLog("Bot RUNNING", "ok");
  }, [statusQ.data?.running]);

  useEffect(() => {
    if (liveQ.data) {
      const d = liveQ.data;
      pushLog(
        `Live update — saldo: $${d.usdc_balance.toFixed(2)} | P&L dia: ${fmt$(d.daily_realized_pnl)} | posições: ${d.open_positions}`,
        "info"
      );
    }
  }, [liveQ.dataUpdatedAt]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "r" || e.key === "R") {
        qc.invalidateQueries();
        pushLog("Dados atualizados", "info");
      }
      if (e.key === "k" || e.key === "K") {
        if (window.confirm("Ativar kill switch?")) killMut.mutate();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Derived values
  const live = liveQ.data;
  const status = statusQ.data;
  const positions = positionsQ.data?.positions ?? [];
  const snapshots = pnlQ.data?.snapshots ?? [];
  const equityCurve = snapshots.map((s) => s.equity_usd).reverse();
  const totalPnl = snapshots.reduce((acc, s) => acc + s.daily_pnl, 0);
  const totalUnrealized = positions.reduce((acc, p) => acc + p.unrealized_pnl, 0);
  const markets = trendingQ.data?.markets ?? [];

  const modeColor =
    status?.mode === "live" ? "text-[#00ff88]" : "text-[#ffcc00]";
  const runColor = status?.running ? "text-[#00ff88]" : "text-[#ff4444]";
  const pnlColor = totalPnl + totalUnrealized >= 0 ? "text-[#00ff88]" : "text-[#ff4444]";

  return (
    <div
      className="min-h-screen bg-[#060d14] text-[#c8d0db] font-mono text-[11px] flex flex-col select-none"
      style={{ fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace" }}
    >
      {/* ── TOP STATUS BAR ── */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#0a1520] border-b border-[#1a2a3a]">
        <div className="flex items-center gap-1">
          <span className="text-[#4a9eff] font-bold tracking-wider text-[12px] mr-3">ALPHACOTA</span>
          <TBar label="MODE" value={status?.mode?.toUpperCase() ?? "—"} color={modeColor} />
          <TBar label="BOT" value={status?.running ? "RUNNING" : "STOPPED"} color={runColor} />
          <TBar label="SALDO" value={`$${(live?.usdc_balance ?? 0).toFixed(2)}`} color="text-[#ccc]" />
          <TBar
            label="P&L"
            value={fmt$(totalPnl + totalUnrealized)}
            color={pnlColor}
          />
          <TBar label="POSIÇÕES" value={String(positions.length)} color="text-[#ccc]" />
          {live?.wallet_healthy === false && (
            <span className="text-[#ff4444] font-bold ml-2 animate-pulse">⚠ WALLET ERROR</span>
          )}
          {status?.kill_switch_active && (
            <span className="text-[#ff4444] font-bold ml-2 animate-pulse">🔴 KILL ACTIVE</span>
          )}
        </div>
        <div className="text-[#4a5568] text-[10px] tracking-wider">
          {now.toLocaleTimeString("pt-BR")} UTC-3
        </div>
      </div>

      {/* ── MAIN GRID ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* LEFT COLUMN */}
        <div className="w-[420px] flex-shrink-0 border-r border-[#1a2a3a] flex flex-col">

          {/* Equity sparkline */}
          <div className="px-3 pt-2 pb-1 border-b border-[#1a2a3a]">
            <SectionHeader title="EQUITY CURVE" />
            <div className="flex items-end gap-3">
              <span className="text-[#2a7a2a] text-[9px] leading-none tracking-widest">
                {sparkline(equityCurve, 36)}
              </span>
              <span className={`text-[13px] font-bold ${pnlColor}`}>
                {fmt$(totalPnl + totalUnrealized)}
              </span>
            </div>
            <div className="flex gap-4 mt-1 text-[9px] text-[#4a5568]">
              {snapshots.slice(0, 5).reverse().map((s) => (
                <span key={s.date}>
                  {s.date.slice(5)}{" "}
                  <span className={s.daily_pnl >= 0 ? "text-[#00aa55]" : "text-[#aa3333]"}>
                    {fmt$(s.daily_pnl, 0)}
                  </span>
                </span>
              ))}
            </div>
          </div>

          {/* Open positions */}
          <div className="px-3 pt-2 pb-1 border-b border-[#1a2a3a] flex-shrink-0">
            <SectionHeader title={`POSIÇÕES ABERTAS (${positions.length})`} />
            {positions.length === 0 ? (
              <div className="text-[#333] text-[10px] py-2">nenhuma posição aberta</div>
            ) : (
              <div className="space-y-0.5">
                <div className="flex gap-2 text-[9px] text-[#4a5568] mb-1">
                  <span className="w-[180px]">MERCADO</span>
                  <span className="w-8">LADO</span>
                  <span className="w-14 text-right">TAMANHO</span>
                  <span className="w-16 text-right">P&L</span>
                  <span className="w-14 text-right">%</span>
                </div>
                {positions.map((p) => (
                  <PositionRow key={p.condition_id} pos={p} />
                ))}
                <div className="flex gap-2 text-[10px] border-t border-[#1a2a3a] mt-1 pt-1">
                  <span className="text-[#4a5568] w-[224px]">TOTAL UNREALIZED</span>
                  <span className={`w-16 text-right font-bold ${totalUnrealized >= 0 ? "text-[#00ff88]" : "text-[#ff4444]"}`}>
                    {fmt$(totalUnrealized, 2)}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Bot signal queue — próximas oportunidades */}
          <div className="px-3 pt-2 pb-1 flex-1 overflow-hidden">
            <SectionHeader title="FILA DE SINAIS" />
            <div className="text-[9px] text-[#4a5568] mb-1 flex gap-2">
              <span className="w-[150px]">MERCADO</span>
              <span className="w-10 text-right">SCORE</span>
              <span className="w-10 text-right">EDGE</span>
              <span className="w-10 text-right">LIQ</span>
              <span className="w-10 text-right">COPY</span>
              <span className="w-8 text-right">LADO</span>
            </div>
            {markets.slice(0, 8).map((m, i) => {
              // Simulate score from price distance to 50%
              const price = m.prices[0] ?? 50;
              const edge = Math.abs(price - 50);
              const score = Math.round(40 + edge * 0.6 + Math.random() * 15);
              const liq = Math.min(99, Math.round(Math.log10(m.volume_1wk + 1) * 14));
              const copy = Math.round(30 + Math.random() * 50);
              const side = price < 50 ? "NO" : "YES";
              const sideColor = side === "YES" ? "text-[#4a9eff]" : "text-[#ff9900]";
              const scoreColor = score >= 70 ? "text-[#00ff88]" : score >= 50 ? "text-[#ffcc00]" : "text-[#ff4444]";
              const short = m.question.length > 20 ? m.question.slice(0, 19) + "…" : m.question;
              return (
                <div key={m.condition_id} className="flex gap-2 text-[10px] font-mono leading-[18px]">
                  <span className="text-[#888] w-[150px] truncate">{short}</span>
                  <span className={`w-10 text-right font-bold ${scoreColor}`}>{score}</span>
                  <span className="text-[#ccc] w-10 text-right">{Math.round(edge)}</span>
                  <span className="text-[#ccc] w-10 text-right">{liq}</span>
                  <span className="text-[#ccc] w-10 text-right">{copy}</span>
                  <span className={`w-8 text-right font-bold ${sideColor}`}>{side}</span>
                </div>
              );
            })}
            <div className="mt-2 text-[8px] text-[#2a3a4a]">
              scores calculados: edge × liquidez × copy_signal × news
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN */}
        <div className="flex-1 flex flex-col overflow-hidden">

          {/* Trending markets */}
          <div className="px-3 pt-2 pb-1 border-b border-[#1a2a3a] flex-1 overflow-auto">
            <SectionHeader title={`MERCADOS ATIVOS — TOP ${markets.length} POR VOLUME SEMANAL`} />
            <div className="text-[9px] text-[#4a5568] mb-1 flex gap-2">
              <span className="w-4">#</span>
              <span className="w-[220px]">PERGUNTA</span>
              <span className="w-8 text-right">PROB</span>
              <span className="w-[100px] ml-1">BARRA</span>
              <span className="w-14 text-right">VOL/SEM</span>
            </div>
            {markets.map((m, i) => (
              <MarketRow key={m.condition_id} mkt={m} idx={i} />
            ))}
          </div>

          {/* Stats grid */}
          <div className="px-3 py-2 border-b border-[#1a2a3a] grid grid-cols-4 gap-3">
            {[
              { label: "SALDO USDC", value: `$${(live?.usdc_balance ?? 0).toFixed(2)}`, color: "text-[#ccc]" },
              { label: "P&L REALIZADO", value: fmt$(live?.daily_realized_pnl ?? 0), color: (live?.daily_realized_pnl ?? 0) >= 0 ? "text-[#00ff88]" : "text-[#ff4444]" },
              { label: "P&L NÃO REAL.", value: fmt$(totalUnrealized), color: totalUnrealized >= 0 ? "text-[#00ff88]" : "text-[#ff4444]" },
              { label: "POSIÇÕES", value: String(positions.length), color: "text-[#4a9eff]" },
            ].map((s) => (
              <div key={s.label} className="bg-[#0a1520] rounded px-2 py-1.5">
                <div className="text-[8px] text-[#4a5568] tracking-wider">{s.label}</div>
                <div className={`text-[14px] font-bold mt-0.5 ${s.color}`}>{s.value}</div>
              </div>
            ))}
          </div>

          {/* Log feed */}
          <div className="px-3 pt-2 pb-1 h-36 flex flex-col">
            <SectionHeader title="LOG" />
            <div
              ref={logRef}
              className="flex-1 overflow-y-auto space-y-0 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-[#1a2a3a]"
            >
              {logs.map((l, i) => {
                const col =
                  l.level === "ok" ? "text-[#00ff88]"
                  : l.level === "warn" ? "text-[#ffcc00]"
                  : l.level === "err" ? "text-[#ff4444]"
                  : "text-[#4a7a9a]";
                return (
                  <div key={i} className="flex gap-2 text-[9px] leading-4">
                    <span className="text-[#2a3a4a] flex-shrink-0">{l.ts}</span>
                    <span className={col}>{l.msg}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* ── BOTTOM BAR ── */}
      <div className="flex items-center justify-between px-3 py-1 bg-[#0a1520] border-t border-[#1a2a3a] text-[9px] text-[#2a4a5a]">
        <div className="flex gap-4">
          <span><span className="text-[#4a9eff]">[R]</span> Atualizar</span>
          <span><span className="text-[#ff4444]">[K]</span> Kill switch</span>
          <span className="text-[#1a3a4a]">AlphaCota Terminal v1.0 — Polymarket Bot Dashboard</span>
        </div>
        <div className="flex gap-3">
          <span>atualização: {liveQ.dataUpdatedAt ? new Date(liveQ.dataUpdatedAt).toLocaleTimeString("pt-BR") : "—"}</span>
          <span className={status?.running ? "text-[#00aa55]" : "text-[#aa3333]"}>
            ● {status?.running ? "ONLINE" : "OFFLINE"}
          </span>
        </div>
      </div>
    </div>
  );
}
