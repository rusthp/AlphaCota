/**
 * CryptoConfidencePage.tsx — Full signal decomposition for every watched pair.
 *
 * Shows exactly what the live loop sees before deciding to enter or skip:
 *   Regime · ADX · Tech (direction + weight) · On-chain breakdown
 *   News sentiment · Combined score vs threshold · ML gate · Final decision
 *
 * Data: GET /api/crypto/signal/decomposition?interval=15m
 * Auto-refreshes every 60 s (candle TTL).
 */

import { useState, useRef, useLayoutEffect } from "react";
import "./CryptoConfidencePage.css";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  RefreshCw, TrendingUp, TrendingDown, Minus,
  Activity, Brain, Newspaper, Zap, AlertTriangle,
  CheckCircle2, XCircle,
} from "lucide-react";

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

interface OnchainDetail {
  available: boolean;
  aggregate?: number;
  funding_score?: number;
  oi_score?: number;
  ls_score?: number;
  weight_contribution?: number;
}

interface MLDetail {
  available: boolean;
  direction: "long" | "short" | "flat";
  confidence: number;
  prob_long: number;
  prob_flat: number;
  prob_short: number;
}

interface FearGreed {
  value: number;
  label: string;
  score: number;
  size_multiplier: number;
}

interface SymbolDecomp {
  symbol: string;
  error?: string;
  price?: number;
  regime?: "trending" | "ranging" | "volatile" | "unknown";
  adx?: number;
  tech?: {
    direction: "long" | "short" | "flat";
    confidence: number;
    signed: number;
    weight_contribution: number;
  };
  onchain?: OnchainDetail;
  news_score?: number;
  news_weight_contribution?: number;
  combined?: number;
  threshold?: number;
  htf_trend?: "bullish" | "bearish" | "neutral";
  decision?: "long" | "short" | "flat";
  would_enter?: boolean;
  skip_reason?: string | null;
  ml?: MLDetail;
  fear_greed?: FearGreed;
  vwap?: { value: number; price_vs_vwap: number; above: boolean };
  volume_spike?: { detected: boolean; direction: "long" | "short" | "none" };
}

interface DecompResponse {
  interval: string;
  fear_greed: FearGreed;
  symbols: SymbolDecomp[];
  timestamp: number;
}

function getAuthHeader() {
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchDecomposition(interval: string): Promise<DecompResponse> {
  const res = await fetch(`/api/crypto/signal/decomposition?interval=${interval}`, {
    headers: getAuthHeader() as Record<string, string>,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function pct(n: number) { return `${(n * 100).toFixed(1)}%`; }
function fmt2(n: number) { return n.toFixed(2); }

function DirectionBadge({ dir }: { dir: "long" | "short" | "flat" }) {
  if (dir === "long") return (
    <Badge className="bg-emerald-600 text-white text-xs gap-1">
      <TrendingUp className="h-3 w-3" /> LONG
    </Badge>
  );
  if (dir === "short") return (
    <Badge className="bg-red-600 text-white text-xs gap-1">
      <TrendingDown className="h-3 w-3" /> SHORT
    </Badge>
  );
  return (
    <Badge variant="secondary" className="text-xs gap-1">
      <Minus className="h-3 w-3" /> FLAT
    </Badge>
  );
}

const REGIME_PT: Record<string, string> = {
  trending: "Tendência",
  ranging: "Lateral",
  volatile: "Volátil",
  unknown: "Desconhecido",
};

function RegimeBadge({ regime }: { regime?: string }) {
  const cls =
    regime === "trending" ? "bg-blue-600 text-white" :
    regime === "volatile" ? "bg-yellow-600 text-white" :
    "bg-slate-600 text-white";
  return <Badge className={`text-xs ${cls}`}>{regime ? (REGIME_PT[regime] ?? regime) : "—"}</Badge>;
}

const SKIP_REASON_PT: Record<string, string> = {
  ranging_market_adx_too_low: "mercado lateral (ADX baixo)",
  below_threshold: "abaixo do limiar",
  above_threshold_wrong_direction: "limiar cruzado, direção errada",
  ml_gate_failed: "ML bloqueou",
  ml_direction_mismatch: "ML diverge da direção",
  htf_trend_conflict: "conflito com tendência HTF",
  win_rate_too_low: "taxa de acerto baixa",
  no_signal: "sem sinal",
  insufficient_data: "dados insuficientes",
  volatile_market: "mercado volátil",
};

function translateSkipReason(reason: string): string {
  return SKIP_REASON_PT[reason] ?? reason.replace(/_/g, " ");
}

function ScoreBar({
  value, min = -1, max = 1, threshold,
}: { value: number; min?: number; max?: number; threshold?: number }) {
  const ref = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const range = max - min;
    const pctPos = ((value - min) / range) * 100;
    const zeroPct = ((-min) / range) * 100;
    const threshPos = threshold != null ? ((threshold - min) / range) * 100 : null;
    const negThreshPos = threshold != null ? ((-threshold - min) / range) * 100 : null;
    const barColor =
      value > (threshold ?? 0.63) ? "#10b981" :
      value < -(threshold ?? 0.63) ? "#ef4444" :
      "#6b7280";
    const fillLeft = value >= 0 ? `${zeroPct}%` : `${pctPos}%`;
    const fillWidth = `${Math.abs(pctPos - zeroPct)}%`;
    el.style.setProperty("--zero-pct", `${zeroPct}%`);
    el.style.setProperty("--thresh-pos", threshPos != null ? `${threshPos}%` : "0%");
    el.style.setProperty("--neg-thresh-pos", negThreshPos != null ? `${negThreshPos}%` : "0%");
    el.style.setProperty("--fill-left", fillLeft);
    el.style.setProperty("--fill-width", fillWidth);
    el.style.setProperty("--fill-color", barColor);
    el.style.setProperty("--cursor-left", `${pctPos}%`);
  });

  const threshPos = threshold != null ? ((threshold - min) / (max - min)) * 100 : null;
  const negThreshPos = threshold != null ? ((-threshold - min) / (max - min)) * 100 : null;

  return (
    <div ref={ref} className="relative h-3 bg-slate-700 rounded w-full overflow-hidden score-bar-root">
      <div className="absolute top-0 bottom-0 w-px bg-slate-400 score-bar-zero" />
      {threshPos != null && (
        <div className="absolute top-0 bottom-0 w-px bg-yellow-400 opacity-60 score-bar-thresh-pos" />
      )}
      {negThreshPos != null && (
        <div className="absolute top-0 bottom-0 w-px bg-yellow-400 opacity-60 score-bar-thresh-neg" />
      )}
      <div className="absolute top-0 bottom-0 score-bar-fill" />
      <div className="absolute top-0 bottom-0 w-0.5 bg-white score-bar-cursor" />
    </div>
  );
}

function ProbBar({ pLong, pFlat, pShort }: { pLong: number; pFlat: number; pShort: number }) {
  const ref = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty("--w-short", pct(pShort));
    el.style.setProperty("--w-flat", pct(pFlat));
    el.style.setProperty("--w-long", pct(pLong));
  });

  return (
    <div ref={ref} className="flex h-2 rounded overflow-hidden w-full">
      <div className="prob-bar-short" />
      <div className="prob-bar-flat" />
      <div className="prob-bar-long" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fear & Greed widget
// ---------------------------------------------------------------------------

function FearGreedWidget({ fg }: { fg: FearGreed }) {
  const color =
    fg.value <= 24 ? "text-emerald-400" :
    fg.value <= 46 ? "text-green-400" :
    fg.value <= 53 ? "text-slate-300" :
    fg.value <= 74 ? "text-orange-400" :
    "text-red-400";

  return (
    <Card className="bg-slate-800 border-slate-700">
      <CardContent className="py-3 px-4 flex items-center gap-4">
        <div>
          <div className="text-xs text-slate-400 mb-0.5">Fear & Greed</div>
          <div className={`text-2xl font-bold ${color}`}>{fg.value}</div>
          <div className={`text-xs ${color}`}>{fg.label}</div>
        </div>
        <div className="border-l border-slate-600 pl-4">
          <div className="text-xs text-slate-400 mb-0.5">Mult. tamanho</div>
          <div className="text-base font-semibold text-white">×{fg.size_multiplier.toFixed(2)}</div>
        </div>
        <div className="border-l border-slate-600 pl-4">
          <div className="text-xs text-slate-400 mb-0.5">Score contrarian</div>
          <div className="text-base font-semibold text-white">{fg.score > 0 ? "+" : ""}{fg.score.toFixed(1)}</div>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Symbol row
// ---------------------------------------------------------------------------

function SymbolRow({ s }: { s: SymbolDecomp }) {
  const [expanded, setExpanded] = useState(false);

  if (s.error) {
    return (
      <tr className="border-t border-slate-700 text-slate-500 text-xs">
        <td className="py-2 px-3 font-mono">{s.symbol}</td>
        <td colSpan={8} className="py-2 px-3 text-red-400">{s.error}</td>
      </tr>
    );
  }

  const t = s.tech ?? { direction: "flat" as const, confidence: 0, signed: 0, weight_contribution: 0 };
  const oc = s.onchain ?? { available: false };
  const ml = s.ml ?? { available: false, direction: "flat" as const, confidence: 0, prob_long: 0, prob_flat: 1, prob_short: 0 };
  const combined = s.combined ?? 0;

  return (
    <>
      <tr
        className={`border-t border-slate-700 text-sm cursor-pointer hover:bg-slate-800/50 transition-colors ${
          s.would_enter ? "bg-emerald-950/20" : ""
        }`}
        onClick={() => setExpanded(e => !e)}
      >
        {/* Symbol + price */}
        <td className="py-2.5 px-3">
          <div className="font-mono font-semibold text-white">{s.symbol.replace("USDT", "")}</div>
          <div className="text-xs text-slate-400">${s.price?.toLocaleString(undefined, { maximumFractionDigits: 4 })}</div>
        </td>

        {/* Regime + ADX */}
        <td className="py-2.5 px-3">
          <RegimeBadge regime={s.regime} />
          <div className="text-xs text-slate-400 mt-0.5">ADX {s.adx?.toFixed(1)}</div>
        </td>

        {/* Technical */}
        <td className="py-2.5 px-3">
          <DirectionBadge dir={t.direction} />
          <div className="text-xs text-slate-400 mt-0.5">
            conf {pct(t.confidence)} · peso {t.weight_contribution > 0 ? "+" : ""}{fmt2(t.weight_contribution)}
          </div>
        </td>

        {/* On-chain */}
        <td className="py-2.5 px-3">
          {oc.available ? (
            <>
              <div className={`text-sm font-medium ${oc.aggregate! >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {oc.aggregate! >= 0 ? "+" : ""}{oc.aggregate?.toFixed(3)}
              </div>
              <div className="text-xs text-slate-500 mt-0.5">
                f:{oc.funding_score?.toFixed(2)} oi:{oc.oi_score?.toFixed(2)} ls:{oc.ls_score?.toFixed(2)}
              </div>
            </>
          ) : (
            <span className="text-xs text-slate-500">—</span>
          )}
        </td>

        {/* News */}
        <td className="py-2.5 px-3">
          <div className={`text-sm font-medium ${(s.news_score ?? 0) > 0.05 ? "text-emerald-400" : (s.news_score ?? 0) < -0.05 ? "text-red-400" : "text-slate-400"}`}>
            {(s.news_score ?? 0) >= 0 ? "+" : ""}{s.news_score?.toFixed(3)}
          </div>
        </td>

        {/* Combined bar */}
        <td className="py-2.5 px-3 min-w-[120px]">
          <div className="mb-1 flex justify-between text-xs">
            <span className={combined >= 0 ? "text-emerald-400" : "text-red-400"}>
              {combined >= 0 ? "+" : ""}{combined.toFixed(3)}
            </span>
            <span className="text-slate-500">lim ±{s.threshold?.toFixed(2)}</span>
          </div>
          <ScoreBar value={combined} threshold={s.threshold} />
        </td>

        {/* ML */}
        <td className="py-2.5 px-3">
          {ml.available ? (
            <>
              <DirectionBadge dir={ml.direction} />
              <div className="text-xs text-slate-400 mt-0.5">{pct(ml.confidence)}</div>
              <ProbBar pLong={ml.prob_long} pFlat={ml.prob_flat} pShort={ml.prob_short} />
            </>
          ) : (
            <span className="text-xs text-slate-500">sem modelo</span>
          )}
        </td>

        {/* HTF */}
        <td className="py-2.5 px-3">
          <span className={`text-xs font-medium ${
            s.htf_trend === "bullish" ? "text-emerald-400" :
            s.htf_trend === "bearish" ? "text-red-400" : "text-slate-400"
          }`}>
          {s.htf_trend === "bullish" ? "Alta" : s.htf_trend === "bearish" ? "Baixa" : s.htf_trend === "neutral" ? "Neutro" : "—"}
        </span>
        </td>

        {/* Decision */}
        <td className="py-2.5 px-3">
          {s.would_enter ? (
            <div className="flex items-center gap-1 text-emerald-400">
              <CheckCircle2 className="h-4 w-4" />
              <span className="text-xs font-semibold">ENTRAR</span>
            </div>
          ) : (
            <div className="flex flex-col">
              <div className="flex items-center gap-1 text-slate-400">
                <XCircle className="h-4 w-4" />
                <span className="text-xs">PASSAR</span>
              </div>
              {s.skip_reason && (
                <span className="text-xs text-slate-500 mt-0.5">{translateSkipReason(s.skip_reason)}</span>
              )}
            </div>
          )}
        </td>
      </tr>

      {/* Expanded detail row */}
      {expanded && (
        <tr className="border-t border-slate-700 bg-slate-900">
          <td colSpan={9} className="px-4 py-3">
            <div className="grid grid-cols-4 gap-4 text-xs">
              <div>
                <div className="text-slate-400 font-medium mb-1 flex items-center gap-1">
                  <Activity className="h-3 w-3" /> Técnico (75%)
                </div>
                <div className="space-y-0.5 text-slate-300">
                  <div>Direção: <span className={t.direction === "long" ? "text-emerald-400" : t.direction === "short" ? "text-red-400" : "text-slate-400"}>{t.direction}</span></div>
                  <div>Confiança: {pct(t.confidence)}</div>
                  <div>Signed: {t.signed >= 0 ? "+" : ""}{t.signed.toFixed(4)}</div>
                  <div>Contribuição: {t.weight_contribution >= 0 ? "+" : ""}{t.weight_contribution.toFixed(4)}</div>
                </div>
              </div>

              <div>
                <div className="text-slate-400 font-medium mb-1 flex items-center gap-1">
                  <Zap className="h-3 w-3" /> On-chain (15%)
                </div>
                {oc.available ? (
                  <div className="space-y-0.5 text-slate-300">
                    <div>Agregado: {oc.aggregate! >= 0 ? "+" : ""}{oc.aggregate?.toFixed(4)}</div>
                    <div>Funding: {oc.funding_score?.toFixed(4)}</div>
                    <div>OI: {oc.oi_score?.toFixed(4)}</div>
                    <div>L/S: {oc.ls_score?.toFixed(4)}</div>
                    <div>Contribuição: {(oc.weight_contribution ?? 0) >= 0 ? "+" : ""}{oc.weight_contribution?.toFixed(4)}</div>
                  </div>
                ) : <div className="text-slate-500">Não disponível</div>}
              </div>

              <div>
                <div className="text-slate-400 font-medium mb-1 flex items-center gap-1">
                  <Newspaper className="h-3 w-3" /> Notícias (10%)
                </div>
                <div className="space-y-0.5 text-slate-300">
                  <div>Pontuação: {(s.news_score ?? 0) >= 0 ? "+" : ""}{s.news_score?.toFixed(4)}</div>
                  <div>Contribuição: {(s.news_weight_contribution ?? 0) >= 0 ? "+" : ""}{(s.news_weight_contribution ?? 0).toFixed(4)}</div>
                </div>
              </div>

              <div>
                <div className="text-slate-400 font-medium mb-1 flex items-center gap-1">
                  <Brain className="h-3 w-3" /> ML LightGBM (gate)
                </div>
                {ml.available ? (
                  <div className="space-y-0.5 text-slate-300">
                    <div>Direção: <span className={ml.direction === "long" ? "text-emerald-400" : ml.direction === "short" ? "text-red-400" : "text-slate-400"}>{ml.direction}</span></div>
                    <div>Confiança: {pct(ml.confidence)} (mín. 55%)</div>
                    <div>P(long): {pct(ml.prob_long)}</div>
                    <div>P(flat): {pct(ml.prob_flat)}</div>
                    <div>P(short): {pct(ml.prob_short)}</div>
                  </div>
                ) : <div className="text-slate-500">Modelo não carregado</div>}
              </div>
            </div>

            {/* VWAP + Volume row */}
            <div className="grid grid-cols-2 gap-4 mt-3 text-xs">
              <div>
                <div className="text-slate-400 font-medium mb-1">VWAP (50 velas)</div>
                {s.vwap ? (
                  <div className="space-y-0.5 text-slate-300">
                    <div>Valor: ${s.vwap.value.toLocaleString(undefined, { maximumFractionDigits: 4 })}</div>
                    <div>
                      Preço vs VWAP:{" "}
                      <span className={s.vwap.above ? "text-emerald-400" : "text-red-400"}>
                        {s.vwap.price_vs_vwap >= 0 ? "+" : ""}{s.vwap.price_vs_vwap.toFixed(3)}%{" "}
                        ({s.vwap.above ? "acima ↑" : "abaixo ↓"})
                      </span>
                    </div>
                  </div>
                ) : <div className="text-slate-500">—</div>}
              </div>
              <div>
                <div className="text-slate-400 font-medium mb-1">Volume Spike (&gt;1.5× média)</div>
                {s.volume_spike ? (
                  <div className="text-slate-300">
                    {s.volume_spike.detected ? (
                      <span className={s.volume_spike.direction === "long" ? "text-emerald-400" : s.volume_spike.direction === "short" ? "text-red-400" : "text-slate-400"}>
                        Spike detectado — {s.volume_spike.direction === "long" ? "bullish ↑" : s.volume_spike.direction === "short" ? "bearish ↓" : "sem direção"}
                      </span>
                    ) : <span className="text-slate-500">Sem spike</span>}
                  </div>
                ) : <div className="text-slate-500">—</div>}
              </div>
            </div>

            <div className="mt-3 pt-2 border-t border-slate-700 text-xs text-slate-400">
              <span className="font-medium">Fórmula:</span>{" "}
              combinado = 0.75 × {t.signed >= 0 ? "+" : ""}{t.signed.toFixed(3)} + 0.15 × {(oc.aggregate ?? 0) >= 0 ? "+" : ""}{(oc.aggregate ?? 0).toFixed(3)} + 0.10 × {(s.news_score ?? 0) >= 0 ? "+" : ""}{(s.news_score ?? 0).toFixed(3)} = <span className={combined > 0 ? "text-emerald-400" : combined < 0 ? "text-red-400" : "text-slate-300"}>{combined >= 0 ? "+" : ""}{combined.toFixed(4)}</span>
              {" "}· limiar ±{s.threshold?.toFixed(2)}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function CryptoConfidencePage() {
  const [interval, setInterval] = useState<"15m" | "1h" | "4h">("15m");

  const { data, isLoading, error, refetch, isFetching, dataUpdatedAt } = useQuery({
    queryKey: ["crypto-decomposition", interval],
    queryFn: () => fetchDecomposition(interval),
    refetchInterval: 60_000,
    staleTime: 55_000,
  });

  const updatedAt = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString()
    : "—";

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Brain className="h-5 w-5 text-yellow-400" />
            Confiança IA
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Decomposição completa de cada sinal — exatamente o que o loop usa para entrar ou passar
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded overflow-hidden border border-slate-600">
            {(["15m", "1h", "4h"] as const).map(iv => (
              <button
                key={iv}
                onClick={() => setInterval(iv)}
                className={`px-3 py-1 text-xs font-medium transition-colors ${
                  interval === iv
                    ? "bg-yellow-500 text-black"
                    : "bg-slate-800 text-slate-300 hover:bg-slate-700"
                }`}
              >
                {iv}
              </button>
            ))}
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => refetch()}
            disabled={isFetching}
            className="border-slate-600 text-slate-300"
          >
            <RefreshCw className={`h-3 w-3 mr-1 ${isFetching ? "animate-spin" : ""}`} />
            {updatedAt}
          </Button>
        </div>
      </div>

      {/* Fear & Greed */}
      {data?.fear_greed && <FearGreedWidget fg={data.fear_greed} />}

      {/* Table */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader className="py-3 px-4">
          <CardTitle className="text-sm font-medium text-slate-300 flex items-center gap-2">
            <Activity className="h-4 w-4" />
            Análise por par — clique para expandir decomposição completa
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading && (
            <div className="text-center py-12 text-slate-400 text-sm">
              Carregando sinais... (on-chain + ML podem levar ~10s)
            </div>
          )}
          {error && (
            <div className="text-center py-8 text-red-400 text-sm flex items-center justify-center gap-2">
              <AlertTriangle className="h-4 w-4" />
              {(error as Error).message}
            </div>
          )}
          {data && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700 text-xs text-slate-400 uppercase tracking-wide">
                    <th className="py-2 px-3 text-left">Par</th>
                    <th className="py-2 px-3 text-left">Regime</th>
                    <th className="py-2 px-3 text-left">Técnico 75%</th>
                    <th className="py-2 px-3 text-left">On-chain 15%</th>
                    <th className="py-2 px-3 text-left">Notícias 10%</th>
                    <th className="py-2 px-3 text-left min-w-[140px]">Combinado</th>
                    <th className="py-2 px-3 text-left">Filtro ML</th>
                    <th className="py-2 px-3 text-left">HTF</th>
                    <th className="py-2 px-3 text-left">Decisão</th>
                  </tr>
                </thead>
                <tbody>
                  {data.symbols.map(s => (
                    <SymbolRow key={s.symbol} s={s} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Legend */}
      <div className="text-xs text-slate-500 space-y-1 border-t border-slate-700 pt-3">
        <div>
          <span className="text-yellow-400 font-medium">Threshold:</span>{" "}
          linhas amarelas na barra = ±0.63 (trending) ou ±0.70 (ranging + on-chain override).
          Combined precisa cruzar o threshold E ML gate ≥55% confiança na mesma direção para entrar.
        </div>
        <div>
          <span className="text-slate-400 font-medium">On-chain:</span>{" "}
          Funding Rate + Open Interest + Long/Short Ratio da Binance Futures (contrarian).
          Sinal negativo = bearish crowd → oportunidade contrarian long.
        </div>
      </div>
    </div>
  );
}
