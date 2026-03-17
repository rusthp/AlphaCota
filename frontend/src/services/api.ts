/**
 * services/api.ts
 *
 * Camada de acesso à API Python do AlphaCota.
 * Todas as chamadas passam pelo proxy do Vite (/api -> localhost:8000).
 */

const BASE = "";

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
export interface FII {
  ticker: string;
  name: string;
  segment: string;
  price: number;
  change: number;
  dy: number;
  pvp: number;
  score: number;
  liquidity: number;
  _source: string;
}

export interface ScannerResponse {
  fiis: FII[];
  total: number;
}

export interface FIIDetail {
  ticker: string;
  segment: string;
  price: number;
  price_source: string;
  dividend_monthly: number;
  dividend_source: string;
  fundamentals: Record<string, unknown>;
  evaluation: Record<string, unknown>;
}

export interface MacroSnapshot {
  selic: number;
  cdi: number;
  ipca: number;
  selic_source: string;
  cdi_source: string;
  ipca_source: string;
  [key: string]: unknown;
}

export interface MomentumItem {
  ticker: string;
  score: number;
  ret_3m: number;
  ret_6m: number;
  ret_12m: number;
}

export interface FireResult {
  years_to_fire: number;
  required_capital: number;
  monthly_income_at_fire: number;
  current_patrimony: number;
}

export interface NewsItem {
  titulo: string;
  data: string;
  link: string;
}

export interface AIAnalysisResult {
  success: boolean;
  raw_response?: string;
  error?: string;
  ticker: string;
  news?: NewsItem[];
  news_count?: number;
}

// ---------------------------------------------------------------------------
// API Functions
// ---------------------------------------------------------------------------

/** Scanner — lista todos os FIIs com score e fundamentals reais */
export function fetchScanner(sectors?: string): Promise<ScannerResponse> {
  const params = sectors ? `?sectors=${encodeURIComponent(sectors)}` : "";
  return fetchJSON(`/api/scanner${params}`);
}

/** Detalhe de um FII */
export function fetchFIIDetail(ticker: string): Promise<FIIDetail> {
  return fetchJSON(`/api/fii/${ticker.toUpperCase()}`);
}

/** Universo de FIIs disponíveis */
export function fetchUniverse(sectors?: string) {
  const params = sectors ? `?sectors=${encodeURIComponent(sectors)}` : "";
  return fetchJSON<{ fiis: Array<Record<string, unknown>>; sectors: Record<string, number> }>(`/api/universe${params}`);
}

/** Snapshot macroeconômico */
export function fetchMacro(): Promise<MacroSnapshot> {
  return fetchJSON("/api/macro");
}

/** Matriz de correlação */
export function fetchCorrelation(tickers: string[], startDate = "2023-01-01", endDate = "2025-12-31") {
  return fetchJSON<{ tickers: string[]; matrix: Record<string, Record<string, number>>; sources: Record<string, string> }>(
    "/api/correlation",
    { method: "POST", body: JSON.stringify({ tickers, start_date: startDate, end_date: endDate }) },
  );
}

/** Stress test */
export function fetchStressTest(tickers: string[], quantities: Record<string, number> = {}, scenarios: string[] = []) {
  return fetchJSON<{ scenarios: Array<Record<string, unknown>> }>(
    "/api/stress",
    { method: "POST", body: JSON.stringify({ tickers, quantities, scenarios }) },
  );
}

/** Momentum ranking */
export function fetchMomentum(topN = 10) {
  return fetchJSON<{ ranking: MomentumItem[]; total_analyzed: number }>(`/api/momentum?top_n=${topN}`);
}

/** Cluster analysis */
export function fetchClusters() {
  return fetchJSON<Record<string, unknown>>("/api/clusters");
}

/** FIRE calculator */
export function fetchFire(params: {
  patrimonio_atual: number;
  aporte_mensal: number;
  taxa_anual?: number;
  renda_alvo_anual?: number;
}): Promise<FireResult> {
  return fetchJSON("/api/fire", { method: "POST", body: JSON.stringify(params) });
}

/** Simulação 12 meses */
export function fetchSimulate(params: {
  tickers: string[];
  quantities?: Record<string, number>;
  aporte_mensal?: number;
  target_allocation?: Record<string, float>;
  meses?: number;
}) {
  return fetchJSON<Record<string, unknown>>("/api/simulate", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/** Monte Carlo */
export function fetchMonteCarlo(params: {
  tickers: string[];
  quantities?: Record<string, number>;
  aporte_mensal?: number;
  meses?: number;
  simulacoes?: number;
}) {
  return fetchJSON<Record<string, unknown>>("/api/monte-carlo", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/** AI analysis */
export function fetchAIAnalysis(ticker: string, apiKey?: string): Promise<AIAnalysisResult> {
  return fetchJSON("/api/ai/analyze", {
    method: "POST",
    body: JSON.stringify({ ticker, api_key: apiKey }),
  });
}

/** Notícias de um FII */
export function fetchNews(ticker: string, limit = 5) {
  return fetchJSON<{ ticker: string; news: NewsItem[]; count: number }>(`/api/news/${ticker.toUpperCase()}?limit=${limit}`);
}

/** Health check */
export function fetchHealth() {
  return fetchJSON<{ status: string; version: string }>("/health");
}
