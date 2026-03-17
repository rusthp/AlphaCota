/**
 * hooks/use-api.ts
 *
 * TanStack Query hooks para consumir a API Python do AlphaCota.
 * Usa staleTime de 5min para dados que mudam pouco (scanner, macro).
 */

import { useQuery, useMutation } from "@tanstack/react-query";
import {
  fetchScanner,
  fetchFIIDetail,
  fetchMacro,
  fetchMomentum,
  fetchClusters,
  fetchCorrelation,
  fetchStressTest,
  fetchFire,
  fetchSimulate,
  fetchMonteCarlo,
  fetchAIAnalysis,
  fetchNews,
  fetchHealth,
} from "@/services/api";

const STALE_5MIN = 5 * 60 * 1000;
const STALE_1MIN = 60 * 1000;

/** Scanner — lista de FIIs com score */
export function useScanner(sectors?: string) {
  return useQuery({
    queryKey: ["scanner", sectors],
    queryFn: () => fetchScanner(sectors),
    staleTime: STALE_5MIN,
  });
}

/** Detalhe de um FII */
export function useFIIDetail(ticker: string) {
  return useQuery({
    queryKey: ["fii", ticker],
    queryFn: () => fetchFIIDetail(ticker),
    staleTime: STALE_5MIN,
    enabled: !!ticker,
  });
}

/** Macro snapshot */
export function useMacro() {
  return useQuery({
    queryKey: ["macro"],
    queryFn: fetchMacro,
    staleTime: STALE_5MIN,
  });
}

/** Momentum ranking */
export function useMomentum(topN = 10) {
  return useQuery({
    queryKey: ["momentum", topN],
    queryFn: () => fetchMomentum(topN),
    staleTime: STALE_5MIN,
  });
}

/** Cluster analysis */
export function useClusters() {
  return useQuery({
    queryKey: ["clusters"],
    queryFn: fetchClusters,
    staleTime: STALE_5MIN,
  });
}

/** Notícias de um FII */
export function useNews(ticker: string, limit = 5) {
  return useQuery({
    queryKey: ["news", ticker, limit],
    queryFn: () => fetchNews(ticker, limit),
    staleTime: STALE_1MIN,
    enabled: !!ticker,
  });
}

/** Health check */
export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    staleTime: STALE_1MIN,
  });
}

/** Correlation — mutation pois depende de input do usuário */
export function useCorrelation() {
  return useMutation({
    mutationFn: (params: { tickers: string[]; startDate?: string; endDate?: string }) =>
      fetchCorrelation(params.tickers, params.startDate, params.endDate),
  });
}

/** Stress test */
export function useStressTest() {
  return useMutation({
    mutationFn: (params: { tickers: string[]; quantities?: Record<string, number>; scenarios?: string[] }) =>
      fetchStressTest(params.tickers, params.quantities, params.scenarios),
  });
}

/** FIRE calculator */
export function useFire() {
  return useMutation({
    mutationFn: fetchFire,
  });
}

/** Simulate */
export function useSimulate() {
  return useMutation({
    mutationFn: fetchSimulate,
  });
}

/** Monte Carlo */
export function useMonteCarlo() {
  return useMutation({
    mutationFn: fetchMonteCarlo,
  });
}

/** AI Analysis */
export function useAIAnalysis() {
  return useMutation({
    mutationFn: (params: { ticker: string; apiKey?: string }) =>
      fetchAIAnalysis(params.ticker, params.apiKey),
  });
}
