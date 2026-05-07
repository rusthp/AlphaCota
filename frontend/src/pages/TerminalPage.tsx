/**
 * TerminalPage.tsx — Bloomberg-style terminal with POLYMARKET / CRYPTO mode toggle.
 *
 * CRYPTO mode layout:
 *   TOP BAR  — mode tabs · balance · P&L · win rate · fear/greed · clock
 *   LEFT     — positions · signal queue · news feed
 *   RIGHT    — TradingView chart (top) + pairs table (bottom)
 *   BOTTOM   — stats grid · log feed
 */

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import "./TerminalPage.css";

function BarFill({ pct, className }: { pct: number; className: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    ref.current?.style.setProperty("--ob-w", `${pct}%`);
  }, [pct]);
  return <div ref={ref} className={className} />;
}

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

function fmtVol(n: number) {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

function fmtAge(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return `${Math.floor(diff)}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

function useNow() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

function sparkline(values: number[], width = 20): string {
  if (values.length === 0) return "─".repeat(width);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const blocks = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"];
  const step = values.length / width;
  return Array.from({ length: width }, (_, i) => {
    const idx = Math.min(Math.floor(i * step), values.length - 1);
    const level = Math.round(((values[idx] - min) / range) * (blocks.length - 1));
    return blocks[level];
  }).join("");
}

function bar(pct: number, width = 22): string {
  const filled = Math.round((pct / 100) * width);
  return "█".repeat(filled) + "░".repeat(width - filled);
}

// ---------------------------------------------------------------------------
// Types — Polymarket
// ---------------------------------------------------------------------------

interface Position {
  condition_id: string; question: string; side: string;
  size_usd: number; entry_price: number; current_price: number;
  unrealized_pnl: number; unrealized_pct: number;
}
interface PnlSnapshot { date: string; equity_usd: number; daily_pnl: number; }
interface LiveStatus { mode: string; usdc_balance: number; daily_realized_pnl: number; open_positions: number; wallet_healthy: boolean; }
interface BotStatus { running: boolean; mode: string; kill_switch_active: boolean; uptime_seconds: number | null; }
interface TrendingMarket { condition_id: string; question: string; volume_1wk: number; outcomes: string[]; prices: number[]; }
interface PolyOrder { order_id: string; market_id: string; question: string; direction: string; size_usd: number; fill_price: number | null; status: string; mode: string; created_at: number; }
interface PolyCalibration { overall_brier: number; overall_win_rate: number; total_resolved: number; lookback_days: number; categories: { category: string; brier_score: number; win_rate: number; mean_edge: number; resolved_count: number }[]; }

// ---------------------------------------------------------------------------
// Types — Crypto
// ---------------------------------------------------------------------------

interface CryptoStatus { mode: string; active: boolean; balance_usd: number; open_positions: number; }
interface CryptoPosition { id: number; symbol: string; side: string; entry_price: number; qty_usd: number; current_price: number; stop_loss: number; take_profit: number; opened_at: number; }
interface CryptoPnl { total_pnl: number; today_pnl: number; win_rate: number; trade_count: number; }
interface CryptoSymbol {
  symbol: string; error?: string; price?: number;
  regime?: "trending" | "ranging" | "volatile" | "unknown"; adx?: number;
  tech?: { direction: "long" | "short" | "flat"; confidence: number; signed: number; weight_contribution: number };
  combined?: number; threshold?: number;
  decision?: "long" | "short" | "flat"; would_enter?: boolean; skip_reason?: string | null;
  ml?: { available: boolean; direction: string; confidence: number; prob_long: number; prob_flat: number; prob_short: number };
  htf_trend?: "bullish" | "bearish" | "neutral";
  vwap?: { value: number; price_vs_vwap: number; above: boolean };
  volume_spike?: { detected: boolean; direction: string };
}
interface FearGreed { value: number; label: string; score: number; }
interface NewsItem { title: string; url: string; source: string; published_at: number; }

// ---------------------------------------------------------------------------
// Sub-components — shared
// ---------------------------------------------------------------------------

function TBar({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <span className="mr-3">
      <span className="text-[#4a5568]">{label}:</span>
      <span className={`ml-1 font-bold ${color}`}>{value}</span>
    </span>
  );
}

function SectionHeader({ title }: { title: string }) {
  return (
    <div className="text-[10px] font-bold tracking-widest text-[#4a9eff] border-b border-[#1a2a3a] pb-0.5 mb-1">
      ── {title} {"─".repeat(Math.max(0, 36 - title.length - 4))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components — Polymarket
// ---------------------------------------------------------------------------

function PositionRow({ pos }: { pos: Position }) {
  const pnlColor = pos.unrealized_pnl >= 0 ? "text-[#00ff88]" : "text-[#ff4444]";
  const sideColor = pos.side === "YES" ? "text-[#4a9eff]" : "text-[#ff9900]";
  const short = pos.question.length > 26 ? pos.question.slice(0, 25) + "…" : pos.question;
  return (
    <div className="flex gap-1 text-[10px] font-mono leading-5">
      <span className="text-[#888] w-[170px] truncate">{short}</span>
      <span className={`w-8 font-bold ${sideColor}`}>{pos.side}</span>
      <span className="text-[#ccc] w-12 text-right">${pos.size_usd.toFixed(0)}</span>
      <span className={`w-14 text-right font-bold ${pnlColor}`}>{fmt$(pos.unrealized_pnl, 2)}</span>
    </div>
  );
}

function MarketRow({ mkt, idx }: { mkt: TrendingMarket; idx: number }) {
  const price = mkt.prices[0] ?? 0;
  const priceColor = price >= 70 ? "text-[#00ff88]" : price >= 40 ? "text-[#ffcc00]" : "text-[#ff4444]";
  const short = mkt.question.length > 32 ? mkt.question.slice(0, 31) + "…" : mkt.question;
  return (
    <div className="flex items-center gap-2 text-[10px] font-mono leading-5">
      <span className="text-[#4a5568] w-4">{String(idx + 1).padStart(2)}.</span>
      <span className="text-[#aaa] w-[210px] truncate">{short}</span>
      <span className={`w-8 font-bold ${priceColor}`}>{price.toFixed(0)}%</span>
      <span className="text-[#2a4a2a] w-[90px] font-mono text-[8px] leading-5">{bar(price, 14)}</span>
      <span className="text-[#4a5568] w-12 text-right">{fmtVol(mkt.volume_1wk)}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components — Crypto
// ---------------------------------------------------------------------------

function CryptoPosRow({ pos }: { pos: CryptoPosition }) {
  const unrealized =
    pos.side === "long"
      ? ((pos.current_price - pos.entry_price) / pos.entry_price) * pos.qty_usd
      : ((pos.entry_price - pos.current_price) / pos.entry_price) * pos.qty_usd;
  const pnlColor = unrealized >= 0 ? "text-[#00ff88]" : "text-[#ff4444]";
  const sideColor = pos.side === "long" ? "text-[#00ff88]" : "text-[#ff4444]";
  const sym = pos.symbol.replace("USDT", "");
  const ep = pos.entry_price < 1 ? pos.entry_price.toFixed(5) : pos.entry_price.toFixed(2);
  return (
    <div className="flex gap-1 text-[10px] font-mono leading-5">
      <span className="text-[#ccc] w-10 font-bold">{sym}</span>
      <span className={`w-8 font-bold ${sideColor}`}>{pos.side.toUpperCase()}</span>
      <span className="text-[#888] w-20 text-right">${ep}</span>
      <span className="text-[#ccc] w-12 text-right">${pos.qty_usd.toFixed(0)}</span>
      <span className={`w-14 text-right font-bold ${pnlColor}`}>{fmt$(unrealized, 2)}</span>
    </div>
  );
}

function CryptoPairRow({ sym, idx }: { sym: CryptoSymbol; idx: number }) {
  const combined = sym.combined ?? 0;
  const thresh = sym.threshold ?? 0.63;
  const dir = sym.tech?.direction ?? "flat";
  const regime = sym.regime ?? "unknown";
  const combinedColor = Math.abs(combined) >= thresh
    ? (combined > 0 ? "text-[#00ff88]" : "text-[#ff4444]") : "text-[#ffcc00]";
  const dirColor = dir === "long" ? "text-[#00ff88]" : dir === "short" ? "text-[#ff4444]" : "text-[#444]";
  const regColor = regime === "trending" ? "text-[#4a9eff]" : regime === "volatile" ? "text-[#ff9900]" : "text-[#666]";
  const decColor = sym.would_enter ? (sym.decision === "long" ? "text-[#00ff88]" : "text-[#ff4444]") : "text-[#2a3a2a]";
  const mlStr = sym.ml?.available
    ? `${(sym.ml.prob_long * 100).toFixed(0)}L/${(sym.ml.prob_short * 100).toFixed(0)}S`
    : "—";
  const price = sym.price
    ? (sym.price < 1 ? sym.price.toFixed(4) : sym.price < 100 ? sym.price.toFixed(2) : sym.price.toFixed(0))
    : "—";
  const vwapMark = sym.vwap?.above ? "▲" : "▼";
  const vwapColor = sym.vwap?.above ? "text-[#00aa55]" : "text-[#aa3333]";
  const volSpike = sym.volume_spike?.detected ? "⚡" : "";

  const flags = `${vwapMark}${volSpike}`;

  return (
    <div className="flex items-center gap-2 text-[10px] font-mono leading-5">
      <span className="text-[#4a5568] w-5 flex-shrink-0">{String(idx + 1).padStart(2)}.</span>
      <span className="text-[#ddd] w-10 font-bold flex-shrink-0">{sym.symbol.replace("USDT", "")}</span>
      <span className="text-[#777] w-20 text-right flex-shrink-0">${price}</span>
      <span className={`w-16 flex-shrink-0 ${regColor}`}>{regime.slice(0, 8)}</span>
      <span className="text-[#666] w-8 text-right flex-shrink-0">{(sym.adx ?? 0).toFixed(0)}</span>
      <span className={`w-6 text-center font-bold flex-shrink-0 ${dirColor}`}>{dir.slice(0, 1).toUpperCase()}</span>
      <span className="text-[#555] w-8 text-right flex-shrink-0">{((sym.tech?.confidence ?? 0) * 100).toFixed(0)}%</span>
      <span className={`w-16 text-right font-bold flex-shrink-0 ${combinedColor}`}>{combined.toFixed(3)}</span>
      <span className={`w-5 text-center flex-shrink-0 ${vwapColor}`}>{flags}</span>
      <span className="text-[#445] w-14 text-right flex-shrink-0">{mlStr}</span>
      <span className={`w-10 text-right font-bold flex-shrink-0 ${decColor}`}>
        {sym.would_enter ? (sym.decision ?? "—").toUpperCase() : "PASS"}
      </span>
    </div>
  );
}

interface OrderBookData {
  bids: [number, number][];
  asks: [number, number][];
  imbalance: number;
}

function OrderBook({ data, symbol }: { data: OrderBookData | undefined; symbol: string }) {
  if (!data) return <div className="text-[#4a5568] text-[9px] p-2">carregando…</div>;

  const { bids, asks, imbalance } = data;
  const maxQty = Math.max(
    ...bids.slice(0, 12).map((b) => b[1]),
    ...asks.slice(0, 12).map((a) => a[1]),
    1,
  );

  const fmtP = (p: number) =>
    p < 1 ? p.toFixed(5) : p < 100 ? p.toFixed(3) : p < 10000 ? p.toFixed(1) : p.toFixed(0);
  const fmtQ = (q: number) =>
    q >= 1000 ? `${(q / 1000).toFixed(1)}K` : q.toFixed(2);

  const imbalancePct = Math.round((imbalance + 1) / 2 * 100);
  const imbalanceColor =
    imbalance > 0.15 ? "text-[#00ff88]" : imbalance < -0.15 ? "text-[#ff4444]" : "text-[#ffcc00]";

  return (
    <div className="flex flex-col h-full">
      <SectionHeader title={`ORDER BOOK · ${symbol.replace("USDT", "")}`} />

      {/* Imbalance bar */}
      <div className="flex items-center gap-1 mb-1 text-[9px]">
        <span className="text-[#ff4444] w-6 text-right">{100 - imbalancePct}%</span>
        <div className="flex-1 h-2 bg-[#0a1520] rounded overflow-hidden flex">
          <BarFill pct={imbalancePct} className="ob-bar-imb bg-[#00aa55] h-full transition-all" />
          <div className="bg-[#aa3333] h-full flex-1" />
        </div>
        <span className="text-[#00ff88] w-6">{imbalancePct}%</span>
        <span className={`ml-1 font-bold ${imbalanceColor}`}>
          {imbalance > 0 ? "BUY" : imbalance < 0 ? "SELL" : "NEU"}
        </span>
      </div>

      {/* Header */}
      <div className="flex text-[8px] text-[#4a5568] mb-0.5 gap-1">
        <span className="w-16">PREÇO</span>
        <span className="flex-1 text-right">QTD</span>
        <span className="w-12 text-[#2a3a4a]"></span>
      </div>

      {/* Asks — reversed so highest ask is at top */}
      <div className="flex-1 overflow-hidden flex flex-col-reverse">
        {asks.slice(0, 10).map(([p, q], i) => {
          const barW = Math.round((q / maxQty) * 100);
          return (
            <div key={i} className="flex items-center gap-1 text-[9px] font-mono leading-[15px] relative">
              <BarFill pct={barW} className="ob-bar-ask absolute right-0 top-0 h-full bg-[#3a0a0a] opacity-60" />
              <span className="text-[#ff5555] w-16 z-10">{fmtP(p)}</span>
              <span className="flex-1 text-right text-[#cc4444] z-10">{fmtQ(q)}</span>
            </div>
          );
        })}
      </div>

      {/* Spread */}
      {bids[0] && asks[0] && (
        <div className="text-[8px] text-center text-[#4a5568] border-y border-[#1a2a3a] py-0.5 my-0.5">
          spread: {(asks[0][0] - bids[0][0]).toFixed(asks[0][0] < 1 ? 5 : asks[0][0] < 100 ? 3 : 1)}
        </div>
      )}

      {/* Bids */}
      <div className="flex-1 overflow-hidden">
        {bids.slice(0, 10).map(([p, q], i) => {
          const barW = Math.round((q / maxQty) * 100);
          return (
            <div key={i} className="flex items-center gap-1 text-[9px] font-mono leading-[15px] relative">
              <BarFill pct={barW} className="ob-bar-bid absolute right-0 top-0 h-full bg-[#0a3a0a] opacity-60" />
              <span className="text-[#44cc44] w-16 z-10">{fmtP(p)}</span>
              <span className="flex-1 text-right text-[#33aa33] z-10">{fmtQ(q)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FearGreedBar({ fg }: { fg: FearGreed | null }) {
  if (!fg) return null;
  const v = fg.value;
  const color = v >= 75 ? "text-[#00ff88]" : v >= 50 ? "text-[#ffcc00]" : v >= 25 ? "text-[#ff9900]" : "text-[#ff4444]";
  const label = fg.label ?? (v >= 75 ? "Ganância Extrema" : v >= 55 ? "Ganância" : v >= 45 ? "Neutro" : v >= 25 ? "Medo" : "Medo Extremo");
  return (
    <div className="flex items-center gap-2 text-[9px]">
      <span className="text-[#4a5568]">FEAR&GREED</span>
      <span className={`font-bold text-[11px] ${color}`}>{v}</span>
      <span className="text-[#4a5568] font-mono text-[8px]">{bar(v, 12)}</span>
      <span className={`${color}`}>{label}</span>
    </div>
  );
}

interface IndicatorSnap {
  price: number;
  rsi: number; rsi_signal: string;
  ema9: number; ema20: number; ema50: number;
  ma_signal: string; triple_ema_aligned: string;
  macd: number; macd_signal: number; macd_hist: number; macd_signal_label: string;
  bb_upper: number; bb_mid: number; bb_lower: number; pct_b: number; bb_width: number;
  stoch_k: number; stoch_d: number; stoch_signal: string;
  adx: number; di_plus: number; di_minus: number;
  supertrend_dir: number;
  rel_vol: number;
  atr: number;
}

function IndicatorPanel({ data }: { data: IndicatorSnap | undefined }) {
  if (!data) return <div className="text-[#4a5568] text-[9px] py-2">calculando…</div>;

  const rsi = data.rsi ?? 50;
  const macdH = data.macd_hist ?? 0;
  const bbPct = Math.round((data.pct_b ?? 0.5) * 100);
  const stochK = data.stoch_k ?? 50;
  const stochD = data.stoch_d ?? 50;
  const relVol = data.rel_vol ?? 1;
  const adx = data.adx ?? 0;
  const diPlus = data.di_plus ?? 0;
  const diMinus = data.di_minus ?? 0;
  const stDir = data.supertrend_dir === 1;

  // Score: count bull signals
  const bulls = [
    rsi < 50,
    macdH > 0,
    data.triple_ema_aligned === "bull",
    stDir,
    diPlus > diMinus,
    stochK < 50,
    bbPct < 55,
    relVol > 1,
  ].filter(Boolean).length;
  const total = 8;
  const sentiment = bulls >= 6 ? "BULL" : bulls <= 2 ? "BEAR" : "NEUTR";
  const sentColor = bulls >= 6 ? "text-[#00ff88] bg-[#0a2a0a]" : bulls <= 2 ? "text-[#ff4444] bg-[#2a0a0a]" : "text-[#ffcc00] bg-[#1a1a0a]";

  type RowProps = { label: string; value: string; color: string; tag?: string; tagColor?: string };
  const Row = ({ label, value, color, tag, tagColor }: RowProps) => (
    <div className="flex items-center gap-1 text-[9px] leading-[17px] border-b border-[#0d1a24]">
      <span className="text-[#3a5a6a] w-[72px] flex-shrink-0">{label}</span>
      <span className={`font-bold flex-shrink-0 ${color}`}>{value}</span>
      {tag && <span className={`ml-auto text-[8px] font-bold px-1 rounded ${tagColor ?? "text-[#4a5568]"}`}>{tag}</span>}
    </div>
  );

  return (
    <div className="flex flex-col gap-0 text-[9px] font-mono">
      {/* Sentiment summary */}
      <div className={`flex items-center justify-between px-1 py-0.5 rounded mb-1 ${sentColor}`}>
        <span className="text-[10px] font-bold">{sentiment}</span>
        <span className="text-[9px]">{bulls}/{total} bull</span>
      </div>

      <Row label="RSI(14)"
        value={rsi.toFixed(1)}
        color={rsi < 30 ? "text-[#00ff88]" : rsi > 70 ? "text-[#ff4444]" : "text-[#ffcc00]"}
        tag={rsi < 30 ? "OVERSOLD" : rsi > 70 ? "OVERBOUGHT" : undefined}
        tagColor={rsi < 30 ? "text-[#00ff88]" : "text-[#ff4444]"} />

      <Row label="MACD hist"
        value={macdH.toFixed(5)}
        color={macdH > 0 ? "text-[#00ff88]" : "text-[#ff4444]"}
        tag={macdH > 0 ? "▲" : "▼"}
        tagColor={macdH > 0 ? "text-[#00ff88]" : "text-[#ff4444]"} />

      <Row label="EMA 9/21/50"
        value={data.triple_ema_aligned.toUpperCase()}
        color={data.triple_ema_aligned === "bull" ? "text-[#00ff88]" : data.triple_ema_aligned === "bear" ? "text-[#ff4444]" : "text-[#ffcc00]"}
        tag={data.triple_ema_aligned === "bull" ? "▲▲▲" : data.triple_ema_aligned === "bear" ? "▼▼▼" : "MIX"}
        tagColor={data.triple_ema_aligned === "bull" ? "text-[#00ff88]" : data.triple_ema_aligned === "bear" ? "text-[#ff4444]" : "text-[#ffcc00]"} />

      <Row label="Supertrend"
        value={stDir ? "BULL" : "BEAR"}
        color={stDir ? "text-[#00ff88]" : "text-[#ff4444]"}
        tag={stDir ? "▲" : "▼"}
        tagColor={stDir ? "text-[#00ff88]" : "text-[#ff4444]"} />

      <Row label="ADX(14)"
        value={adx.toFixed(1)}
        color={adx > 25 ? "text-[#4a9eff]" : adx > 12 ? "text-[#ffcc00]" : "text-[#666]"}
        tag={adx > 25 ? "TREND" : adx > 12 ? "FRACO" : "FLAT"}
        tagColor={adx > 25 ? "text-[#4a9eff]" : adx > 12 ? "text-[#ffcc00]" : "text-[#555]"} />

      <Row label="DI+ / DI-"
        value={`${diPlus.toFixed(1)} / ${diMinus.toFixed(1)}`}
        color={diPlus > diMinus ? "text-[#00ff88]" : "text-[#ff4444]"}
        tag={diPlus > diMinus ? "BULL" : "BEAR"}
        tagColor={diPlus > diMinus ? "text-[#00ff88]" : "text-[#ff4444]"} />

      <Row label="Stoch K/D"
        value={`${stochK.toFixed(0)} / ${stochD.toFixed(0)}`}
        color={stochK < 20 ? "text-[#00ff88]" : stochK > 80 ? "text-[#ff4444]" : "text-[#ccc]"}
        tag={stochK < 20 ? "OVERSOLD" : stochK > 80 ? "OVERBOUGHT" : undefined}
        tagColor={stochK < 20 ? "text-[#00ff88]" : "text-[#ff4444]"} />

      <Row label="BB %B"
        value={`${bbPct}%`}
        color={bbPct > 85 ? "text-[#ff4444]" : bbPct < 15 ? "text-[#00ff88]" : "text-[#ccc]"}
        tag={bbPct > 85 ? "UPPER" : bbPct < 15 ? "LOWER" : "MID"}
        tagColor={bbPct > 85 ? "text-[#ff4444]" : bbPct < 15 ? "text-[#00ff88]" : "text-[#555]"} />

      <Row label="Vol relat."
        value={`${relVol.toFixed(2)}×`}
        color={relVol > 2 ? "text-[#ffcc00]" : relVol > 1.5 ? "text-[#ccc]" : "text-[#666]"}
        tag={relVol > 2 ? "⚡SPIKE" : relVol > 1.5 ? "HIGH" : undefined}
        tagColor={relVol > 2 ? "text-[#ffcc00]" : "text-[#aaa]"} />

      <Row label="ATR(14)"
        value={data.atr < 0.001 ? data.atr.toFixed(6) : data.atr < 1 ? data.atr.toFixed(4) : data.atr.toFixed(2)}
        color="text-[#4a6a7a]" />
    </div>
  );
}

// TradingView iframe chart — includes EMA20/50, BB, RSI, MACD, Volume
function TradingViewChart({ symbol, interval }: { symbol: string; interval: string }) {
  const tvSymbol = `BINANCE:${symbol}`;
  const studies = [
    "RSI@tv-basicstudies",
    "MACD@tv-basicstudies",
    "BB@tv-basicstudies",
    "MAExp@tv-basicstudies",
    "Volume@tv-basicstudies",
  ].join(",");
  const src = [
    `https://s.tradingview.com/widgetembed/`,
    `?symbol=${encodeURIComponent(tvSymbol)}`,
    `&interval=${interval}`,
    `&theme=dark&style=1&locale=pt_BR`,
    `&toolbar_bg=%230a1520`,
    `&hide_top_toolbar=0&hide_legend=0&hide_side_toolbar=1`,
    `&withdateranges=1`,
    `&studies=${encodeURIComponent(studies)}`,
    `&show_popup_button=0`,
    `&utm_source=alphacota`,
  ].join("");
  return (
    <iframe
      key={`${symbol}-${interval}`}
      src={src}
      title={`chart-${symbol}`}
      className="w-full h-full border-0"
      allow="fullscreen"
    />
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

type TermMode = "poly" | "crypto";

const CHART_INTERVALS = ["1", "5", "15", "60", "240", "D"] as const;
const INTERVAL_LABELS: Record<string, string> = { "1": "1m", "5": "5m", "15": "15m", "60": "1h", "240": "4h", "D": "1D" };

export default function TerminalPage() {
  const qc = useQueryClient();
  const now = useNow();
  const logRef = useRef<HTMLDivElement>(null);
  const [termMode, setTermMode] = useState<TermMode>("poly");
  const [chartSymbol, setChartSymbol] = useState("BTCUSDT");
  const [chartInterval, setChartInterval] = useState("15");
  const [autoMode, setAutoMode] = useState(false);
  const [logs, setLogs] = useState<{ ts: string; msg: string; level: "info" | "ok" | "warn" | "err" }[]>([
    { ts: new Date().toLocaleTimeString("pt-BR"), msg: "AlphaCota Terminal iniciado", level: "info" },
  ]);

  const pushLog = (msg: string, level: "info" | "ok" | "warn" | "err" = "info") => {
    setLogs((prev) => [
      ...prev.slice(-80),
      { ts: new Date().toLocaleTimeString("pt-BR"), msg, level },
    ]);
    setTimeout(() => logRef.current?.scrollTo(0, logRef.current.scrollHeight), 50);
  };

  // ── Polymarket queries ────────────────────────────────────────────────────

  const liveQ = useQuery<LiveStatus>({
    queryKey: ["term-live"],
    queryFn: () => API("/api/polymarket/live-status"),
    refetchInterval: 5000,
    enabled: termMode === "poly",
  });
  const statusQ = useQuery<BotStatus>({
    queryKey: ["term-status"],
    queryFn: () => API("/api/polymarket/status"),
    refetchInterval: 5000,
    enabled: termMode === "poly",
  });
  const positionsQ = useQuery<{ positions: Position[] }>({
    queryKey: ["term-positions"],
    queryFn: () => API("/api/polymarket/positions"),
    refetchInterval: 8000,
    enabled: termMode === "poly",
  });
  const pnlQ = useQuery<{ snapshots: PnlSnapshot[] }>({
    queryKey: ["term-pnl"],
    queryFn: () => API("/api/polymarket/pnl"),
    refetchInterval: 30000,
    enabled: termMode === "poly",
  });
  const trendingQ = useQuery<{ markets: TrendingMarket[] }>({
    queryKey: ["term-trending"],
    queryFn: () => API("/api/polymarket/trending-markets?limit=12"),
    staleTime: 120_000, refetchInterval: 120_000,
    enabled: termMode === "poly",
  });
  const polyOrdersQ = useQuery<{ orders: PolyOrder[]; total: number }>({
    queryKey: ["term-poly-orders"],
    queryFn: () => API("/api/polymarket/orders?limit=10"),
    refetchInterval: 15_000,
    enabled: termMode === "poly",
  });
  const polyCalibQ = useQuery<PolyCalibration>({
    queryKey: ["term-poly-calib"],
    queryFn: () => API("/api/polymarket/calibration?lookback_days=30"),
    staleTime: 300_000, refetchInterval: 300_000,
    enabled: termMode === "poly",
  });

  // ── Crypto queries ────────────────────────────────────────────────────────

  const cryptoStatusQ = useQuery<CryptoStatus>({
    queryKey: ["term-crypto-status"],
    queryFn: () => API("/api/crypto/status"),
    refetchInterval: 10000, enabled: termMode === "crypto",
  });
  const cryptoPosQ = useQuery<{ positions: CryptoPosition[] }>({
    queryKey: ["term-crypto-positions"],
    queryFn: () => API("/api/crypto/positions"),
    refetchInterval: 10000, enabled: termMode === "crypto",
  });
  const cryptoPnlQ = useQuery<CryptoPnl>({
    queryKey: ["term-crypto-pnl"],
    queryFn: () => API("/api/crypto/pnl"),
    refetchInterval: 30000, enabled: termMode === "crypto",
  });
  const cryptoDecompQ = useQuery<{ symbols: CryptoSymbol[]; fear_greed: FearGreed }>({
    queryKey: ["term-crypto-decomp"],
    queryFn: () =>
      fetch("/api/crypto/signal/decomposition?interval=15m", {
        headers: getAuthHeader() as Record<string, string>,
      }).then((r) => r.json()),
    refetchInterval: 60000, staleTime: 55000, enabled: termMode === "crypto",
  });
  const cryptoNewsQ = useQuery<{ news: NewsItem[] }>({
    queryKey: ["term-crypto-news"],
    queryFn: () => API("/api/crypto/news?limit=12"),
    refetchInterval: 120000, staleTime: 110000, enabled: termMode === "crypto",
  });
  const cryptoOrderBookQ = useQuery<OrderBookData>({
    queryKey: ["term-crypto-ob", chartSymbol],
    queryFn: () => API(`/api/crypto/orderbook/${chartSymbol}?limit=15`),
    refetchInterval: 3000, staleTime: 2500, enabled: termMode === "crypto",
  });
  const cryptoIndicatorsQ = useQuery<IndicatorSnap>({
    queryKey: ["term-crypto-ind", chartSymbol],
    queryFn: () => API(`/api/crypto/indicators/${chartSymbol}?interval=15m&limit=100`),
    refetchInterval: 30000, staleTime: 25000, enabled: termMode === "crypto",
  });

  // ── Mutations ─────────────────────────────────────────────────────────────

  const killMut = useMutation({
    mutationFn: () =>
      fetch("/api/polymarket/kill", { method: "POST", headers: getAuthHeader() }).then((r) => r.json()),
    onSuccess: () => {
      pushLog("Kill switch ativado", "warn");
      qc.invalidateQueries({ queryKey: ["term-status"] });
    },
  });

  // ── Side effects ──────────────────────────────────────────────────────────

  useEffect(() => {
    if (statusQ.data?.running) pushLog("Bot Polymarket RUNNING", "ok");
  }, [statusQ.data?.running]);

  useEffect(() => {
    if (liveQ.data) {
      const d = liveQ.data;
      pushLog(`Poly — saldo: $${d.usdc_balance.toFixed(2)} | P&L dia: ${fmt$(d.daily_realized_pnl)} | pos: ${d.open_positions}`, "info");
    }
  }, [liveQ.dataUpdatedAt]);

  useEffect(() => {
    if (cryptoStatusQ.data) {
      const d = cryptoStatusQ.data;
      pushLog(`Crypto — saldo: $${d.balance_usd.toFixed(2)} | pos: ${d.open_positions}`, "info");
    }
  }, [cryptoStatusQ.dataUpdatedAt]);

  // Sync chart symbol when decomp loads (first time only)
  useEffect(() => {
    const syms = cryptoDecompQ.data?.symbols ?? [];
    if (syms.length > 0 && !syms.find((s) => s.symbol === chartSymbol)) {
      setChartSymbol(syms[0].symbol);
    }
  }, [cryptoDecompQ.data]);

  // AUTO mode: rotate chart to hottest pair every 20s
  useEffect(() => {
    if (!autoMode || termMode !== "crypto") return;
    const pick = () => {
      const syms = (cryptoDecompQ.data?.symbols ?? []).filter((s) => !s.error);
      if (syms.length === 0) return;
      // Priority: would_enter first, then highest |combined|
      const sorted = [...syms].sort((a, b) => {
        if (a.would_enter && !b.would_enter) return -1;
        if (!a.would_enter && b.would_enter) return 1;
        return Math.abs(b.combined ?? 0) - Math.abs(a.combined ?? 0);
      });
      const next = sorted[0].symbol;
      setChartSymbol((prev) => {
        if (prev === next) {
          // Rotate to second-best if already showing top
          return sorted[1]?.symbol ?? next;
        }
        return next;
      });
    };
    pick();
    const id = setInterval(pick, 20000);
    return () => clearInterval(id);
  }, [autoMode, termMode, cryptoDecompQ.data]);

  // ── Keyboard shortcuts ────────────────────────────────────────────────────

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "r" || e.key === "R") { qc.invalidateQueries(); pushLog("Dados atualizados", "info"); }
      if (e.key === "k" || e.key === "K") { if (window.confirm("Ativar kill switch?")) killMut.mutate(); }
      if (e.key === "1") setTermMode("poly");
      if (e.key === "2") setTermMode("crypto");
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // ── Derived values — polymarket ───────────────────────────────────────────

  const live = liveQ.data;
  const status = statusQ.data;
  const positions = positionsQ.data?.positions ?? [];
  const snapshots = pnlQ.data?.snapshots ?? [];
  const equityCurve = snapshots.map((s) => s.equity_usd).reverse();
  const totalPnl = snapshots.reduce((acc, s) => acc + s.daily_pnl, 0);
  const totalUnrealized = positions.reduce((acc, p) => acc + p.unrealized_pnl, 0);
  const markets = trendingQ.data?.markets ?? [];
  const polyOrders = polyOrdersQ.data?.orders ?? [];
  const polyCalib = polyCalibQ.data ?? null;
  const modeColor = status?.mode === "live" ? "text-[#00ff88]" : "text-[#ffcc00]";
  const runColor = status?.running ? "text-[#00ff88]" : "text-[#ff4444]";
  const pnlColor = totalPnl + totalUnrealized >= 0 ? "text-[#00ff88]" : "text-[#ff4444]";

  function fmtUptime(sec: number | null | undefined): string {
    if (!sec) return "—";
    if (sec < 60) return `${sec}s`;
    if (sec < 3600) return `${Math.floor(sec / 60)}m`;
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    return `${h}h ${m}m`;
  }

  // ── Derived values — crypto ───────────────────────────────────────────────

  const cryptoStatus = cryptoStatusQ.data;
  const cryptoPositions = cryptoPosQ.data?.positions ?? [];
  const cryptoPnl = cryptoPnlQ.data;
  const fearGreed = cryptoDecompQ.data?.fear_greed ?? null;
  const cryptoSymbols = (cryptoDecompQ.data?.symbols ?? [])
    .filter((s) => !s.error)
    .sort((a, b) => Math.abs(b.combined ?? 0) - Math.abs(a.combined ?? 0));
  const cryptoNews = cryptoNewsQ.data?.news ?? [];

  const cryptoUnrealized = cryptoPositions.reduce((acc, p) => {
    const pnl = p.side === "long"
      ? ((p.current_price - p.entry_price) / p.entry_price) * p.qty_usd
      : ((p.entry_price - p.current_price) / p.entry_price) * p.qty_usd;
    return acc + pnl;
  }, 0);

  const cryptoTotalPnl = (cryptoPnl?.total_pnl ?? 0) + cryptoUnrealized;
  const cryptoPnlColor = cryptoTotalPnl >= 0 ? "text-[#00ff88]" : "text-[#ff4444]";
  const cryptoModeColor = cryptoStatus?.mode === "live" ? "text-[#00ff88]" : "text-[#ffcc00]";
  const chartSymbols = cryptoSymbols.map((s) => s.symbol);

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="terminal-root min-h-screen bg-[#060d14] text-[#c8d0db] font-mono text-[11px] flex flex-col select-none">

      {/* ── TOP STATUS BAR ── */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#0a1520] border-b border-[#1a2a3a] flex-shrink-0">
        <div className="flex items-center gap-1 flex-wrap">
          <span className="text-[#4a9eff] font-bold tracking-wider text-[12px] mr-2">ALPHACOTA</span>

          <button type="button" onClick={() => setTermMode("poly")}
            className={`px-2 py-0.5 text-[9px] font-bold tracking-widest rounded mr-1 border transition-colors ${
              termMode === "poly" ? "bg-[#1a3a5a] border-[#4a9eff] text-[#4a9eff]" : "bg-transparent border-[#1a2a3a] text-[#4a5568] hover:text-[#6a8aaa]"
            }`}>[1] POLYMARKET</button>
          <button type="button" onClick={() => setTermMode("crypto")}
            className={`px-2 py-0.5 text-[9px] font-bold tracking-widest rounded mr-3 border transition-colors ${
              termMode === "crypto" ? "bg-[#1a3a1a] border-[#00ff88] text-[#00ff88]" : "bg-transparent border-[#1a2a3a] text-[#4a5568] hover:text-[#6a8aaa]"
            }`}>[2] CRYPTO</button>

          {termMode === "poly" ? (
            <>
              <TBar label="MODE" value={status?.mode?.toUpperCase() ?? "—"} color={modeColor} />
              <TBar label="BOT" value={status?.running ? "RUNNING" : "STOPPED"} color={runColor} />
              <TBar label="SALDO" value={`$${(live?.usdc_balance ?? 0).toFixed(2)}`} color="text-[#ccc]" />
              <TBar label="P&L" value={fmt$(totalPnl + totalUnrealized)} color={pnlColor} />
              <TBar label="POSIÇÕES" value={String(positions.length)} color="text-[#ccc]" />
              {live?.wallet_healthy === false && <span className="text-[#ff4444] font-bold ml-2 animate-pulse">⚠ WALLET ERROR</span>}
              {status?.kill_switch_active && <span className="text-[#ff4444] font-bold ml-2 animate-pulse">🔴 KILL ACTIVE</span>}
            </>
          ) : (
            <>
              <TBar label="MODE" value={cryptoStatus?.mode?.toUpperCase() ?? "—"} color={cryptoModeColor} />
              <TBar label="SALDO" value={`$${(cryptoStatus?.balance_usd ?? 0).toFixed(2)}`} color="text-[#ccc]" />
              <TBar label="P&L TOTAL" value={fmt$(cryptoTotalPnl)} color={cryptoPnlColor} />
              <TBar label="HOJE" value={fmt$(cryptoPnl?.today_pnl ?? 0)} color={(cryptoPnl?.today_pnl ?? 0) >= 0 ? "text-[#00ff88]" : "text-[#ff4444]"} />
              <TBar label="WIN" value={`${cryptoPnl?.win_rate?.toFixed(1) ?? "—"}%`} color="text-[#ffcc00]" />
              <TBar label="POSIÇÕES" value={String(cryptoPositions.length)} color="text-[#ccc]" />
              {fearGreed && (
                <span className="ml-2">
                  <FearGreedBar fg={fearGreed} />
                </span>
              )}
            </>
          )}
        </div>
        <div className="text-[#4a5568] text-[10px] tracking-wider flex-shrink-0">
          {now.toLocaleTimeString("pt-BR")} UTC-3
        </div>
      </div>

      {/* ── MAIN GRID ── */}
      <div className="flex flex-1 overflow-hidden min-h-0">

        {/* ── LEFT COLUMN ── */}
        <div className={`${termMode === "crypto" ? "w-[300px]" : "w-[420px]"} flex-shrink-0 border-r border-[#1a2a3a] flex flex-col min-h-0`}>

          {/* Equity / summary */}
          <div className="px-3 pt-2 pb-1 border-b border-[#1a2a3a] flex-shrink-0">
            <SectionHeader title="EQUITY CURVE" />
            {termMode === "poly" ? (
              <>
                <div className="flex items-end gap-3">
                  <span className="text-[#2a7a2a] text-[9px] leading-none">{sparkline(equityCurve, 32)}</span>
                  <span className={`text-[13px] font-bold ${pnlColor}`}>{fmt$(totalPnl + totalUnrealized)}</span>
                </div>
                <div className="flex gap-3 mt-1 text-[9px] text-[#4a5568]">
                  {snapshots.slice(0, 5).reverse().map((s) => (
                    <span key={s.date}>{s.date.slice(5)} <span className={s.daily_pnl >= 0 ? "text-[#00aa55]" : "text-[#aa3333]"}>{fmt$(s.daily_pnl, 0)}</span></span>
                  ))}
                </div>
              </>
            ) : (
              <div className="flex items-center gap-3">
                <span className={`text-[13px] font-bold ${cryptoPnlColor}`}>{fmt$(cryptoTotalPnl)}</span>
                <span className="text-[9px] text-[#4a5568]">{cryptoPnl?.trade_count ?? 0} trades · {cryptoPnl?.win_rate?.toFixed(1) ?? "—"}% win</span>
              </div>
            )}
          </div>

          {/* Open positions */}
          <div className="px-3 pt-2 pb-1 border-b border-[#1a2a3a] flex-shrink-0">
            {termMode === "poly" ? (
              <>
                <SectionHeader title={`POSIÇÕES ABERTAS (${positions.length})`} />
                {positions.length === 0 ? (
                  <div className="text-[#2a3a2a] text-[10px] py-1">nenhuma posição aberta</div>
                ) : (
                  <>
                    <div className="flex gap-1 text-[9px] text-[#4a5568] mb-0.5">
                      <span className="w-[170px]">MERCADO</span><span className="w-8">LADO</span>
                      <span className="w-12 text-right">TAM</span><span className="w-14 text-right">P&L</span>
                    </div>
                    {positions.map((p) => <PositionRow key={p.condition_id} pos={p} />)}
                    <div className="flex gap-1 text-[9px] border-t border-[#1a2a3a] mt-1 pt-0.5">
                      <span className="text-[#4a5568] flex-1">TOTAL</span>
                      <span className={`w-14 text-right font-bold ${totalUnrealized >= 0 ? "text-[#00ff88]" : "text-[#ff4444]"}`}>{fmt$(totalUnrealized, 2)}</span>
                    </div>
                  </>
                )}
              </>
            ) : (
              <>
                <SectionHeader title={`POSIÇÕES ABERTAS (${cryptoPositions.length})`} />
                {cryptoPositions.length === 0 ? (
                  <div className="text-[#2a3a2a] text-[10px] py-1">nenhuma posição aberta</div>
                ) : (
                  <>
                    <div className="flex gap-1 text-[9px] text-[#4a5568] mb-0.5">
                      <span className="w-10">PAR</span><span className="w-8">LADO</span>
                      <span className="w-20 text-right">ENTRADA</span><span className="w-12 text-right">TAM</span>
                      <span className="w-14 text-right">P&L</span>
                    </div>
                    {cryptoPositions.map((p) => <CryptoPosRow key={p.id} pos={p} />)}
                    <div className="flex gap-1 text-[9px] border-t border-[#1a2a3a] mt-1 pt-0.5">
                      <span className="text-[#4a5568] flex-1">TOTAL</span>
                      <span className={`w-14 text-right font-bold ${cryptoUnrealized >= 0 ? "text-[#00ff88]" : "text-[#ff4444]"}`}>{fmt$(cryptoUnrealized, 2)}</span>
                    </div>
                  </>
                )}
              </>
            )}
          </div>

          {/* Signal queue */}
          <div className="px-3 pt-2 pb-1 border-b border-[#1a2a3a] flex-shrink-0">
            <SectionHeader title="FILA DE SINAIS" />
            {termMode === "poly" ? (
              <>
                <div className="text-[9px] text-[#4a5568] mb-0.5 flex gap-2">
                  <span className="w-[150px]">MERCADO</span>
                  <span className="w-10 text-right">SCORE</span><span className="w-8 text-right">LIQ</span><span className="w-8 text-right">LADO</span>
                </div>
                {markets.slice(0, 7).map((m) => {
                  const price = m.prices[0] ?? 50;
                  const edge = Math.abs(price - 50);
                  const volScore = Math.min(30, Math.log10(m.volume_1wk + 1) * 7);
                  const score = Math.min(99, Math.round(25 + edge * 0.9 + volScore));
                  const liq = Math.min(99, Math.round(Math.log10(m.volume_1wk + 1) * 14));
                  const side = price < 50 ? "NO" : "YES";
                  const sideColor = side === "YES" ? "text-[#4a9eff]" : "text-[#ff9900]";
                  const scoreColor = score >= 70 ? "text-[#00ff88]" : score >= 50 ? "text-[#ffcc00]" : "text-[#ff4444]";
                  return (
                    <div key={m.condition_id} className="flex gap-2 text-[10px] font-mono leading-[17px]">
                      <span className="text-[#888] w-[150px] truncate">{m.question.slice(0, 19)}…</span>
                      <span className={`w-10 text-right font-bold ${scoreColor}`}>{score}</span>
                      <span className="text-[#ccc] w-8 text-right">{liq}</span>
                      <span className={`w-8 text-right font-bold ${sideColor}`}>{side}</span>
                    </div>
                  );
                })}
              </>
            ) : (
              <>
                <div className="text-[9px] text-[#4a5568] mb-0.5 flex gap-1">
                  <span className="w-10">PAR</span><span className="w-14">REGIME</span>
                  <span className="w-6 text-right">ADX</span><span className="w-6 text-right">D</span>
                  <span className="w-14 text-right">COMB</span><span className="w-10 text-right">DEC</span>
                </div>
                {cryptoSymbols.slice(0, 8).map((s) => {
                  const combined = s.combined ?? 0;
                  const thresh = s.threshold ?? 0.63;
                  const dir = s.tech?.direction ?? "flat";
                  const regime = s.regime ?? "unknown";
                  const cColor = Math.abs(combined) >= thresh ? (combined > 0 ? "text-[#00ff88]" : "text-[#ff4444]") : "text-[#ffcc00]";
                  const dColor = dir === "long" ? "text-[#00ff88]" : dir === "short" ? "text-[#ff4444]" : "text-[#444]";
                  const rColor = regime === "trending" ? "text-[#4a9eff]" : regime === "volatile" ? "text-[#ff9900]" : "text-[#555]";
                  const decColor = s.would_enter ? (s.decision === "long" ? "text-[#00ff88]" : "text-[#ff4444]") : "text-[#2a3a2a]";
                  return (
                    <div key={s.symbol} className="flex gap-1 text-[10px] font-mono leading-[17px]">
                      <span className="text-[#ccc] w-10 font-bold">{s.symbol.replace("USDT", "")}</span>
                      <span className={`w-14 ${rColor}`}>{regime.slice(0, 7)}</span>
                      <span className="text-[#555] w-6 text-right">{(s.adx ?? 0).toFixed(0)}</span>
                      <span className={`w-6 text-right font-bold ${dColor}`}>{dir.slice(0, 1).toUpperCase()}</span>
                      <span className={`w-14 text-right font-bold ${cColor}`}>{combined.toFixed(3)}</span>
                      <span className={`w-10 text-right font-bold ${decColor}`}>{s.would_enter ? (s.decision ?? "—").toUpperCase() : "PASS"}</span>
                    </div>
                  );
                })}
              </>
            )}
          </div>

          {/* News feed — crypto only */}
          {termMode === "crypto" && (
            <div className="px-3 pt-2 pb-1 flex-1 overflow-hidden min-h-0">
              <SectionHeader title="NOTÍCIAS CRYPTO" />
              <div className="overflow-y-auto h-full space-y-0.5 pr-1">
                {cryptoNews.length === 0 ? (
                  <div className="text-[#2a3a2a] text-[10px]">sem notícias</div>
                ) : (
                  cryptoNews.map((n, i) => (
                    <div key={i} className="leading-4">
                      <a
                        href={n.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[9px] text-[#8ab4cf] hover:text-[#4a9eff] leading-4 block truncate"
                        title={n.title}
                      >
                        {n.title}
                      </a>
                      <span className="text-[8px] text-[#2a4a5a]">
                        {n.source && `${n.source} · `}{fmtAge(n.published_at)} atrás
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* Recent orders — polymarket only */}
          {termMode === "poly" && (
            <div className="px-3 pt-2 pb-1 border-b border-[#1a2a3a] flex-shrink-0">
              <SectionHeader title="ÚLTIMAS ORDENS" />
              {polyOrders.length === 0 ? (
                <div className="text-[#2a3a2a] text-[10px] py-1">sem ordens registradas</div>
              ) : (
                <>
                  <div className="text-[9px] text-[#4a5568] mb-0.5 flex gap-1">
                    <span className="w-[140px]">MERCADO</span>
                    <span className="w-8">DIR</span>
                    <span className="w-12 text-right">TAM</span>
                    <span className="w-12 text-right">PREÇO</span>
                    <span className="w-10 text-right">STATUS</span>
                  </div>
                  {polyOrders.slice(0, 6).map((o, i) => {
                    const dirColor = o.direction === "buy" ? "text-[#4a9eff]" : "text-[#ff9900]";
                    const stColor = o.status === "filled" ? "text-[#00ff88]" : o.status === "cancelled" ? "text-[#ff4444]" : "text-[#ffcc00]";
                    const q = o.question || o.market_id;
                    return (
                      <div key={i} className="flex gap-1 text-[10px] font-mono leading-[17px]">
                        <span className="text-[#888] w-[140px] truncate">{q.slice(0, 18)}…</span>
                        <span className={`w-8 font-bold ${dirColor}`}>{o.direction.toUpperCase()}</span>
                        <span className="text-[#ccc] w-12 text-right">${o.size_usd.toFixed(0)}</span>
                        <span className="text-[#777] w-12 text-right">{o.fill_price != null ? (o.fill_price * 100).toFixed(1) + "%" : "—"}</span>
                        <span className={`w-10 text-right ${stColor}`}>{o.status.slice(0, 6).toUpperCase()}</span>
                      </div>
                    );
                  })}
                </>
              )}
            </div>
          )}

          {/* Log — polymarket only in left panel */}
          {termMode === "poly" && (
            <div className="px-3 pt-2 pb-1 flex-1 overflow-hidden min-h-0">
              <SectionHeader title="LOG" />
              <div ref={logRef} className="flex-1 overflow-y-auto h-full">
                {logs.map((l, i) => {
                  const col = l.level === "ok" ? "text-[#00ff88]" : l.level === "warn" ? "text-[#ffcc00]" : l.level === "err" ? "text-[#ff4444]" : "text-[#4a7a9a]";
                  return (
                    <div key={i} className="flex gap-2 text-[9px] leading-4">
                      <span className="text-[#2a3a4a] flex-shrink-0">{l.ts}</span>
                      <span className={col}>{l.msg}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* ── RIGHT COLUMN ── */}
        <div className="flex-1 flex flex-col overflow-hidden min-h-0">

          {termMode === "poly" ? (
            /* ── POLYMARKET RIGHT ── */
            <>
              {/* Markets + calibration sidebar */}
              <div className="flex flex-1 overflow-hidden min-h-0">
                {/* Markets list */}
                <div className="flex-1 px-3 pt-2 pb-1 border-r border-[#1a2a3a] overflow-auto">
                  <SectionHeader title={`MERCADOS ATIVOS — TOP ${markets.length} POR VOLUME SEMANAL`} />
                  <div className="text-[9px] text-[#4a5568] mb-1 flex gap-2">
                    <span className="w-4">#</span><span className="w-[210px]">PERGUNTA</span>
                    <span className="w-8 text-right">PROB</span><span className="w-[90px] ml-1">BARRA</span>
                    <span className="w-12 text-right">VOL/SEM</span>
                  </div>
                  {markets.map((m, i) => <MarketRow key={m.condition_id} mkt={m} idx={i} />)}
                </div>

                {/* Calibration + loop stats sidebar */}
                <div className="w-[220px] flex-shrink-0 flex flex-col overflow-hidden">
                  {/* Loop status */}
                  <div className="px-3 pt-2 pb-1 border-b border-[#1a2a3a] flex-shrink-0">
                    <SectionHeader title="LOOP STATUS" />
                    <div className="space-y-0.5 text-[9px] font-mono">
                      <div className="flex justify-between">
                        <span className="text-[#4a5568]">STATUS</span>
                        <span className={status?.running ? "text-[#00ff88] font-bold" : "text-[#ff4444] font-bold"}>
                          {status?.running ? "▶ RUNNING" : "■ STOPPED"}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[#4a5568]">MODE</span>
                        <span className={modeColor}>{status?.mode?.toUpperCase() ?? "—"}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[#4a5568]">UPTIME</span>
                        <span className="text-[#ccc]">{fmtUptime(status?.uptime_seconds)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[#4a5568]">ORDENS</span>
                        <span className="text-[#ccc]">{polyOrdersQ.data?.total ?? "—"}</span>
                      </div>
                      {status?.kill_switch_active && (
                        <div className="text-[#ff4444] font-bold animate-pulse mt-1">🔴 KILL ATIVO</div>
                      )}
                    </div>
                  </div>

                  {/* Calibration */}
                  <div className="px-3 pt-2 pb-1 border-b border-[#1a2a3a] flex-shrink-0">
                    <SectionHeader title="CALIBRAÇÃO 30D" />
                    {polyCalib == null ? (
                      <div className="text-[#2a3a2a] text-[9px]">sem dados</div>
                    ) : (
                      <div className="space-y-0.5 text-[9px] font-mono">
                        <div className="flex justify-between">
                          <span className="text-[#4a5568]">WIN RATE</span>
                          <span className={polyCalib.overall_win_rate >= 0.55 ? "text-[#00ff88] font-bold" : polyCalib.overall_win_rate >= 0.45 ? "text-[#ffcc00] font-bold" : "text-[#ff4444] font-bold"}>
                            {(polyCalib.overall_win_rate * 100).toFixed(1)}%
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[#4a5568]">BRIER</span>
                          <span className={polyCalib.overall_brier < 0.2 ? "text-[#00ff88]" : polyCalib.overall_brier < 0.3 ? "text-[#ffcc00]" : "text-[#ff4444]"}>
                            {polyCalib.overall_brier.toFixed(4)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[#4a5568]">RESOLVIDOS</span>
                          <span className="text-[#ccc]">{polyCalib.total_resolved}</span>
                        </div>
                        {polyCalib.categories.slice(0, 4).map((c) => (
                          <div key={c.category} className="flex justify-between leading-[15px]">
                            <span className="text-[#2a4a5a] truncate w-[100px]">{c.category.slice(0, 12)}</span>
                            <span className={c.win_rate >= 0.55 ? "text-[#00aa55]" : c.win_rate >= 0.45 ? "text-[#886600]" : "text-[#663333]"}>
                              {(c.win_rate * 100).toFixed(0)}%
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Daily P&L history */}
                  <div className="px-3 pt-2 pb-1 flex-1 overflow-auto">
                    <SectionHeader title="HISTÓRICO DIÁRIO" />
                    {snapshots.length === 0 ? (
                      <div className="text-[#2a3a2a] text-[9px]">sem histórico</div>
                    ) : (
                      <div className="space-y-0.5 text-[9px] font-mono">
                        {snapshots.slice(0, 10).map((s) => (
                          <div key={s.date} className="flex justify-between leading-[15px]">
                            <span className="text-[#3a5a6a]">{s.date.slice(5)}</span>
                            <span className={s.daily_pnl >= 0 ? "text-[#00aa55]" : "text-[#aa3333]"}>
                              {fmt$(s.daily_pnl, 2)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Stats bar — expanded to 6 cards */}
              <div className="px-3 py-2 border-t border-[#1a2a3a] grid grid-cols-6 gap-2 flex-shrink-0">
                {[
                  { label: "SALDO USDC", value: `$${(live?.usdc_balance ?? 0).toFixed(2)}`, color: "text-[#ccc]" },
                  { label: "P&L REALIZADO", value: fmt$(live?.daily_realized_pnl ?? 0), color: (live?.daily_realized_pnl ?? 0) >= 0 ? "text-[#00ff88]" : "text-[#ff4444]" },
                  { label: "P&L NÃO REAL.", value: fmt$(totalUnrealized), color: totalUnrealized >= 0 ? "text-[#00ff88]" : "text-[#ff4444]" },
                  { label: "P&L TOTAL", value: fmt$(totalPnl + totalUnrealized), color: (totalPnl + totalUnrealized) >= 0 ? "text-[#00ff88]" : "text-[#ff4444]" },
                  { label: "WIN RATE", value: polyCalib != null ? `${(polyCalib.overall_win_rate * 100).toFixed(1)}%` : "—", color: polyCalib != null && polyCalib.overall_win_rate >= 0.55 ? "text-[#00ff88]" : "text-[#ffcc00]" },
                  { label: "POSIÇÕES", value: String(positions.length), color: "text-[#4a9eff]" },
                ].map((s) => (
                  <div key={s.label} className="bg-[#0a1520] rounded px-2 py-1.5">
                    <div className="text-[8px] text-[#4a5568] tracking-wider">{s.label}</div>
                    <div className={`text-[13px] font-bold mt-0.5 ${s.color}`}>{s.value}</div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            /* ── CRYPTO RIGHT — chart top + table bottom ── */
            <>
              {/* Chart area */}
              <div className="terminal-chart-area flex flex-col border-b border-[#1a2a3a]">
                {/* Symbol + interval selector */}
                <div className="flex items-center gap-1 px-2 py-1 bg-[#0a1520] border-b border-[#1a2a3a] flex-shrink-0 flex-wrap">
                  <span className="text-[#4a5568] text-[9px] mr-1">SYMBOL:</span>
                  {chartSymbols.slice(0, 10).map((sym) => (
                    <button
                      key={sym}
                      type="button"
                      onClick={() => setChartSymbol(sym)}
                      className={`px-1.5 py-0 text-[9px] font-bold rounded border transition-colors ${
                        chartSymbol === sym
                          ? "bg-[#1a3a1a] border-[#00ff88] text-[#00ff88]"
                          : "bg-transparent border-[#1a2a3a] text-[#4a5568] hover:text-[#aaa]"
                      }`}
                    >
                      {sym.replace("USDT", "")}
                    </button>
                  ))}
                  <span className="text-[#2a3a4a] mx-1">|</span>
                  {/* AUTO mode toggle */}
                  <button
                    type="button"
                    onClick={() => setAutoMode((v) => !v)}
                    className={`px-2 py-0 text-[9px] font-bold rounded border transition-colors mr-1 ${
                      autoMode
                        ? "bg-[#1a2a0a] border-[#88ff44] text-[#88ff44] animate-pulse"
                        : "bg-transparent border-[#1a2a3a] text-[#4a5568] hover:text-[#aaa]"
                    }`}
                    title="AUTO: troca para o par mais quente a cada 20s"
                  >
                    {autoMode ? "⚡AUTO" : "AUTO"}
                  </button>
                  <span className="text-[#2a3a4a] mx-1">|</span>
                  <span className="text-[#4a5568] text-[9px] mr-1">INTV:</span>
                  {CHART_INTERVALS.map((iv) => (
                    <button
                      key={iv}
                      type="button"
                      onClick={() => setChartInterval(iv)}
                      className={`px-1.5 py-0 text-[9px] font-bold rounded border transition-colors ${
                        chartInterval === iv
                          ? "bg-[#1a3a5a] border-[#4a9eff] text-[#4a9eff]"
                          : "bg-transparent border-[#1a2a3a] text-[#4a5568] hover:text-[#aaa]"
                      }`}
                    >
                      {INTERVAL_LABELS[iv]}
                    </button>
                  ))}
                  {/* Live price + VWAP indicator for selected symbol */}
                  {(() => {
                    const s = cryptoSymbols.find((x) => x.symbol === chartSymbol);
                    if (!s) return null;
                    const price = s.price ?? 0;
                    const vwapColor = s.vwap?.above ? "text-[#00ff88]" : "text-[#ff4444]";
                    const vwapLabel = s.vwap?.above ? "▲ VWAP" : "▼ VWAP";
                    const volSpike = s.volume_spike?.detected;
                    return (
                      <span className="ml-auto flex items-center gap-2 text-[10px]">
                        <span className="text-[#ddd] font-bold">
                          ${price < 1 ? price.toFixed(5) : price < 100 ? price.toFixed(2) : price.toFixed(0)}
                        </span>
                        <span className={vwapColor}>{vwapLabel}</span>
                        {volSpike && <span className="text-[#ffcc00]">⚡ VOL SPIKE</span>}
                      </span>
                    );
                  })()}
                </div>
                {/* TradingView iframe */}
                <div className="flex-1 min-h-0">
                  <TradingViewChart symbol={chartSymbol} interval={chartInterval} />
                </div>
              </div>

              {/* Pairs table + Order book — side by side */}
              <div className="flex flex-1 overflow-hidden min-h-0">
                {/* Pairs table */}
                <div className="flex-1 overflow-auto min-h-0 px-3 pt-2 pb-1">
                  <SectionHeader title={`SINAIS CRYPTO — ${cryptoSymbols.length} PARES · 15m`} />
                  <div className="text-[9px] text-[#4a5568] mb-1 flex gap-2">
                    <span className="w-5 flex-shrink-0">#</span>
                    <span className="w-10 flex-shrink-0">PAR</span>
                    <span className="w-20 text-right flex-shrink-0">PREÇO</span>
                    <span className="w-16 flex-shrink-0">REGIME</span>
                    <span className="w-8 text-right flex-shrink-0">ADX</span>
                    <span className="w-6 text-center flex-shrink-0">DIR</span>
                    <span className="w-8 text-right flex-shrink-0">CONF</span>
                    <span className="w-16 text-right flex-shrink-0">COMBINADO</span>
                    <span className="w-5 flex-shrink-0"></span>
                    <span className="w-14 text-right flex-shrink-0">ML L/S</span>
                    <span className="w-10 text-right flex-shrink-0">DECISÃO</span>
                  </div>
                  {cryptoSymbols.map((s, i) => (
                    <div key={s.symbol} className="cursor-pointer hover:bg-[#0a1a0a]" onClick={() => setChartSymbol(s.symbol)}>
                      <CryptoPairRow sym={s} idx={i} />
                    </div>
                  ))}
                  {cryptoDecompQ.isLoading && <div className="text-[#4a5568] text-[10px] py-4">carregando sinais…</div>}
                </div>

                {/* Order book panel */}
                <div className="w-[185px] flex-shrink-0 border-l border-[#1a2a3a] px-2 pt-2 pb-1 overflow-hidden">
                  <OrderBook data={cryptoOrderBookQ.data} symbol={chartSymbol} />
                </div>

                {/* Indicator panel */}
                <div className="w-[175px] flex-shrink-0 border-l border-[#1a2a3a] px-2 pt-2 pb-1 overflow-hidden">
                  <SectionHeader title="INDICADORES" />
                  <IndicatorPanel data={cryptoIndicatorsQ.data} />
                  {cryptoIndicatorsQ.isLoading && (
                    <div className="text-[#4a5568] text-[9px] mt-1">calculando…</div>
                  )}
                </div>
              </div>
            </>
          )}

          {/* Stats grid — crypto */}
          {termMode === "crypto" && (
            <div className="px-3 py-2 border-t border-[#1a2a3a] grid grid-cols-4 gap-3 flex-shrink-0">
              {[
                { label: "SALDO USDT", value: `$${(cryptoStatus?.balance_usd ?? 0).toFixed(2)}`, color: "text-[#ccc]" },
                { label: "P&L HOJE", value: fmt$(cryptoPnl?.today_pnl ?? 0), color: (cryptoPnl?.today_pnl ?? 0) >= 0 ? "text-[#00ff88]" : "text-[#ff4444]" },
                { label: "P&L TOTAL", value: fmt$(cryptoPnl?.total_pnl ?? 0), color: (cryptoPnl?.total_pnl ?? 0) >= 0 ? "text-[#00ff88]" : "text-[#ff4444]" },
                { label: "WIN RATE", value: `${cryptoPnl?.win_rate?.toFixed(1) ?? "—"}%`, color: "text-[#ffcc00]" },
              ].map((s) => (
                <div key={s.label} className="bg-[#0a1520] rounded px-2 py-1.5">
                  <div className="text-[8px] text-[#4a5568] tracking-wider">{s.label}</div>
                  <div className={`text-[14px] font-bold mt-0.5 ${s.color}`}>{s.value}</div>
                </div>
              ))}
            </div>
          )}

          {/* Log feed — crypto mode (right panel bottom) */}
          {termMode === "crypto" && (
            <div className="px-3 pt-1.5 pb-1 border-t border-[#1a2a3a] h-24 flex flex-col flex-shrink-0">
              <SectionHeader title="LOG" />
              <div ref={logRef} className="flex-1 overflow-y-auto">
                {logs.map((l, i) => {
                  const col = l.level === "ok" ? "text-[#00ff88]" : l.level === "warn" ? "text-[#ffcc00]" : l.level === "err" ? "text-[#ff4444]" : "text-[#4a7a9a]";
                  return (
                    <div key={i} className="flex gap-2 text-[9px] leading-4">
                      <span className="text-[#2a3a4a] flex-shrink-0">{l.ts}</span>
                      <span className={col}>{l.msg}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── BOTTOM BAR ── */}
      <div className="flex items-center justify-between px-3 py-1 bg-[#0a1520] border-t border-[#1a2a3a] text-[9px] text-[#2a4a5a] flex-shrink-0">
        <div className="flex gap-4">
          <span><span className="text-[#4a9eff]">[1]</span> Polymarket</span>
          <span><span className="text-[#00ff88]">[2]</span> Crypto</span>
          <span><span className="text-[#4a9eff]">[R]</span> Atualizar</span>
          <span><span className="text-[#ff4444]">[K]</span> Kill switch</span>
          <span className="text-[#1a3a4a]">AlphaCota Terminal v2.0</span>
        </div>
        <div className="flex gap-3">
          <span>
            {termMode === "poly"
              ? `poly: ${liveQ.dataUpdatedAt ? new Date(liveQ.dataUpdatedAt).toLocaleTimeString("pt-BR") : "—"}`
              : `sinais: ${cryptoDecompQ.dataUpdatedAt ? new Date(cryptoDecompQ.dataUpdatedAt).toLocaleTimeString("pt-BR") : "—"}`}
          </span>
          <span className={termMode === "poly"
            ? (status?.running ? "text-[#00aa55]" : "text-[#aa3333]")
            : (cryptoStatus?.active ? "text-[#00aa55]" : "text-[#aa3333]")
          }>
            ● {termMode === "poly" ? (status?.running ? "ONLINE" : "OFFLINE") : (cryptoStatus?.active ? "ONLINE" : "OFFLINE")}
          </span>
        </div>
      </div>
    </div>
  );
}
