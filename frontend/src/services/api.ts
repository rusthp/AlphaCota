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
  pvp: number | null;
  score: number;
  liquidity: number;
  _source: string;
  data_confidence?: number;
  low_liquidity?: boolean;
  dividend_trap?: boolean;
  pvp_outlier?: boolean;
  volatilidade_30d?: number;
}

export interface ScannerResponse {
  fiis: FII[];
  total: number;
}

export interface PricePoint {
  month: string; // "YYYY-MM"
  price: number;
}

export interface DividendPoint {
  month: string; // "YYYY-MM"
  value: number;
}

export interface ScoreBreakdown {
  fundamentos: number; // 0-25
  rendimento: number; // 0-25
  risco: number; // 0-25
  liquidez: number; // 0-25
  total: number; // 0-100
}

export interface FundInfo {
  administrador?: string;
  cnpj?: string;
  patrimonio_liquido?: number;
  num_cotistas?: number;
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
  // Extended fields (enhance-fii-detail-page)
  score_breakdown?: ScoreBreakdown;
  price_history?: PricePoint[];
  dividend_history?: DividendPoint[];
  fund_info?: FundInfo;
  cap_rate?: number | null;
  volatilidade_30d?: number | null;
  num_imoveis?: number | null;
  num_locatarios?: number | null;
  data_confidence?: number;
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
  sentiment_score?: number;
  cached?: boolean;
}

export interface DeepAnalysisMacro {
  ciclo_juros: string;
  impacto_fii: string;
  spread_atrativo: boolean;
  dy_real: number;
  spread_cdi: number;
  yield_minimo_aceitavel: number;
  contexto: string;
  alerta: string | null;
}

export interface DeepAnalysisFundamental {
  qualidade: string;
  pvp_status: string;
  dy_sustentavel: boolean;
  ddm_preco_justo: number | null;
  ddm_upside_pct: number | null;
  pontos_fortes: string[];
  pontos_fracos: string[];
  resumo: string;
}

export interface DeepAnalysisRisk {
  nivel_risco: string;
  risco_liquidez: string;
  risco_credito: string;
  risco_vacancia: string;
  risco_juros: string;
  var_estimado_5pct: string;
  cenario_stress: string;
  resumo_risco: string;
}

export interface DeepAnalysisPersona {
  opiniao: "comprar" | "aguardar" | "evitar";
  raciocinio: string;
  condicao_entrada: string;
}

export interface DeepAnalysisDecision {
  recomendacao: "COMPRAR" | "AGUARDAR" | "EVITAR";
  forca_sinal: "forte" | "moderado" | "fraco";
  preco_entrada_ideal: number | null;
  preco_alvo_12m: number | null;
  stop_sugerido: number | null;
  dy_alvo_minimo: number;
  tese: string;
  gatilhos_compra: string[];
  gatilhos_saida: string[];
  rating: "A" | "B" | "C" | "D" | "F";
}

export interface DeepAnalysisResult {
  success: boolean;
  error?: string;
  ticker: string;
  macro_analysis: DeepAnalysisMacro;
  fundamental_analysis: DeepAnalysisFundamental;
  risk_analysis: DeepAnalysisRisk;
  persona_analysis: {
    barsi: DeepAnalysisPersona;
    crescimento: DeepAnalysisPersona;
  };
  final_decision: DeepAnalysisDecision;
  pipeline_meta: {
    agents_run: number;
    errors: string[];
    timings_s: Record<string, number>;
    total_s: number;
  };
}

export interface AIBatchResponse {
  success: boolean;
  results: AIAnalysisResult[];
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
export function fetchStressTest(
  tickers: string[],
  quantities: Record<string, number> = {},
  scenarios: string[] = [],
  custom_scenario?: { name: string; price_shock: Record<string, number>; dividend_shock: Record<string, number> }
) {
  return fetchJSON<{ scenarios: Array<Record<string, unknown>> }>(
    "/api/stress",
    { method: "POST", body: JSON.stringify({ tickers, quantities, scenarios, custom_scenario }) },
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
  target_allocation?: Record<string, number>;
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
  override_initial_capital?: number;
  growth_rates?: Record<string, number>;
  volatilities?: Record<string, number>;
}) {
  return fetchJSON<any>("/api/monte-carlo", {
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

/** Deep pipeline analysis — 5 agents (Macro → Fundamental → Risk → Persona → Decision) */
export function fetchDeepAnalysis(ticker: string, apiKey?: string): Promise<DeepAnalysisResult> {
  return fetchJSON(`/api/ai/deep-analysis/${ticker.toUpperCase()}`, {
    method: "POST",
    body: JSON.stringify({ api_key: apiKey }),
  });
}

/** AI Batch analysis */
export function fetchAIBatchAnalysis(tickers: string[], apiKey?: string): Promise<AIBatchResponse> {
  return fetchJSON("/api/ai/analyze-batch", {
    method: "POST",
    body: JSON.stringify({ tickers, api_key: apiKey }),
  });
}

/** Obter Histórico de Score SQLite */
export function fetchScoreHistory(ticker: string, limit: number = 12): Promise<{ ticker: string, timeline: { date: string, score: number, details: any }[] }> {
  return fetchJSON(`/api/fiis/${ticker}/history?limit=${limit}`);
}

/** Obter Histórico de Sentimento SQLite */
export function fetchSentimentTrend(ticker: string, limit: number = 5): Promise<{ ticker: string, trend: { date: string, sentiment: string, reason: string }[] }> {
  return fetchJSON(`/api/ai/sentiment/trend/${ticker}?limit=${limit}`);
}

/** Obter Alertas de Queda de Score (SQLite) */
export function fetchScoreAlerts(tickers: string[], threshold: number = 10.0): Promise<{ alerts: { ticker: string, latest_score: number, previous_score: number, drop: number, date: string }[], count: number }> {
  const ts = tickers.join(",");
  return fetchJSON(`/api/fiis/alerts?tickers=${ts}&threshold=${threshold}`);
}

/** Notícias de um FII */
export function fetchNews(ticker: string, limit = 5) {
  return fetchJSON<{ ticker: string; news: NewsItem[]; count: number }>(`/api/news/${ticker.toUpperCase()}?limit=${limit}`);
}

/** Health check */
export function fetchHealth() {
  return fetchJSON<{ status: string; version: string }>("/health");
}

// ---------------------------------------------------------------------------
// Dividend Calendar
// ---------------------------------------------------------------------------

export interface DividendEvent {
  ticker: string;
  ex_date: string;
  pay_date: string;
  valor_por_cota: number;
  tipo: string;
  fonte: string;
  confirmado: boolean;
  setor: string;
}

export interface CalendarMonth {
  year: number;
  month: number;
  events: DividendEvent[];
  total: number;
}

export interface IncomeMonth {
  month: string;
  total_renda: number;
  events: DividendEvent[];
}

export function fetchDividendCalendar(year: number, month: number, tickers?: string): Promise<CalendarMonth> {
  const params = new URLSearchParams({ year: String(year), month: String(month) });
  if (tickers) params.set("tickers", tickers);
  return fetchJSON<CalendarMonth>(`/api/dividends/calendar?${params}`);
}

export interface UpcomingDividendEvent extends DividendEvent {
  days_to_pay: number;
  days_to_ex: number;
  is_ex_soon: boolean;
}

export function fetchUpcomingDividends(daysAhead = 30, tickers?: string): Promise<{ events: UpcomingDividendEvent[]; total: number }> {
  const params = new URLSearchParams({ days_ahead: String(daysAhead) });
  if (tickers) params.set("tickers", tickers);
  return fetchJSON(`/api/dividends/upcoming?${params}`);
}

export function fetchPortfolioIncome(holdings: Record<string, number>, monthsAhead = 12): Promise<{ projection: IncomeMonth[] }> {
  const params = new URLSearchParams({
    holdings: JSON.stringify(holdings),
    months_ahead: String(monthsAhead),
  });
  return fetchJSON<{ projection: IncomeMonth[] }>(`/api/dividends/portfolio-income?${params}`);
}

// ---------------------------------------------------------------------------
// Rebalanceamento
// ---------------------------------------------------------------------------

export interface RebalanceSuggestion {
  ticker: string;
  segment: string;
  action: "buy" | "overweight";
  quantity: number;
  value: number;
  currentPct: number;
  targetPct: number;
  score: number;
}

// ---------------------------------------------------------------------------
// FII Comparador
// ---------------------------------------------------------------------------

export interface CompareableFII extends FIIDetail {
  dy: number;
  pvp: number;
  liquidez: number;
  vacancia: number;
  score: number;
}

export interface CompareResponse {
  fiis: CompareableFII[];
}

export function fetchCompare(tickers: string[]): Promise<CompareResponse> {
  return fetchJSON<CompareResponse>(
    `/api/fiis/compare?tickers=${tickers.map((t) => encodeURIComponent(t)).join(",")}`,
  );
}
