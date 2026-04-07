/**
 * hooks/use-portfolio.ts
 *
 * Gerencia a carteira do usuário via localStorage.
 * Persiste entre sessões. Fonte única de verdade para:
 * - Favoritos (Scanner)
 * - Minha Carteira (posições)
 * - Simulador (dados reais da carteira)
 * - Perfil de investidor (calculado a partir das posições)
 */

import { useState, useCallback, useEffect } from "react";

const STORAGE_KEY = "alphacota_portfolio";
const FAVORITES_KEY = "alphacota_favorites";

export interface PortfolioAsset {
  ticker: string;
  quantity: number;
  avgPrice: number;
}

export interface Portfolio {
  assets: PortfolioAsset[];
  updatedAt: string;
}

function loadPortfolio(): Portfolio {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  return { assets: [], updatedAt: new Date().toISOString() };
}

function savePortfolio(portfolio: Portfolio) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(portfolio));
}

function loadFavorites(): Set<string> {
  try {
    const raw = localStorage.getItem(FAVORITES_KEY);
    if (raw) return new Set(JSON.parse(raw));
  } catch {}
  return new Set();
}

function saveFavorites(favorites: Set<string>) {
  localStorage.setItem(FAVORITES_KEY, JSON.stringify([...favorites]));
}

/** Hook para gerenciar a carteira do usuário */
export function usePortfolio() {
  const [portfolio, setPortfolio] = useState<Portfolio>(loadPortfolio);

  useEffect(() => {
    savePortfolio(portfolio);
  }, [portfolio]);

  const addAsset = useCallback((ticker: string, quantity: number, avgPrice: number) => {
    setPortfolio((prev) => {
      const existing = prev.assets.findIndex((a) => a.ticker === ticker.toUpperCase());
      const newAssets = [...prev.assets];
      if (existing >= 0) {
        // Merge: recalcular preço médio
        const old = newAssets[existing];
        const totalQty = old.quantity + quantity;
        const totalCost = old.quantity * old.avgPrice + quantity * avgPrice;
        newAssets[existing] = {
          ticker: old.ticker,
          quantity: totalQty,
          avgPrice: totalQty > 0 ? totalCost / totalQty : 0,
        };
      } else {
        newAssets.push({ ticker: ticker.toUpperCase(), quantity, avgPrice });
      }
      return { assets: newAssets, updatedAt: new Date().toISOString() };
    });
  }, []);

  const removeAsset = useCallback((ticker: string) => {
    setPortfolio((prev) => ({
      assets: prev.assets.filter((a) => a.ticker !== ticker.toUpperCase()),
      updatedAt: new Date().toISOString(),
    }));
  }, []);

  const updateAsset = useCallback((ticker: string, quantity: number, avgPrice: number) => {
    setPortfolio((prev) => ({
      assets: prev.assets.map((a) =>
        a.ticker === ticker.toUpperCase() ? { ...a, quantity, avgPrice } : a
      ),
      updatedAt: new Date().toISOString(),
    }));
  }, []);

  const clearPortfolio = useCallback(() => {
    setPortfolio({ assets: [], updatedAt: new Date().toISOString() });
  }, []);

  const tickers = portfolio.assets.map((a) => a.ticker);
  const quantities = Object.fromEntries(portfolio.assets.map((a) => [a.ticker, a.quantity]));

  return {
    portfolio,
    addAsset,
    removeAsset,
    updateAsset,
    clearPortfolio,
    tickers,
    quantities,
    isEmpty: portfolio.assets.length === 0,
  };
}

// ─── Watchlists ───────────────────────────────────────────────────────────────

const WATCHLISTS_KEY = "alphacota_watchlists";

export interface Watchlist {
  id: string;
  name: string;
  tickers: string[];
  createdAt: string;
}

function loadWatchlists(): Watchlist[] {
  try {
    const raw = localStorage.getItem(WATCHLISTS_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  return [
    { id: "candidatos", name: "Candidatos", tickers: [], createdAt: new Date().toISOString() },
    { id: "monitorando", name: "Monitorando", tickers: [], createdAt: new Date().toISOString() },
  ];
}

function saveWatchlists(lists: Watchlist[]) {
  localStorage.setItem(WATCHLISTS_KEY, JSON.stringify(lists));
}

export function useWatchlists() {
  const [watchlists, setWatchlists] = useState<Watchlist[]>(loadWatchlists);

  useEffect(() => {
    saveWatchlists(watchlists);
  }, [watchlists]);

  const createList = useCallback((name: string) => {
    const id = name.toLowerCase().replace(/\s+/g, "-") + "-" + Date.now();
    setWatchlists(prev => [
      ...prev,
      { id, name, tickers: [], createdAt: new Date().toISOString() },
    ]);
    return id;
  }, []);

  const deleteList = useCallback((id: string) => {
    setWatchlists(prev => prev.filter(l => l.id !== id));
  }, []);

  const renameList = useCallback((id: string, name: string) => {
    setWatchlists(prev => prev.map(l => l.id === id ? { ...l, name } : l));
  }, []);

  const addTicker = useCallback((listId: string, ticker: string) => {
    const t = ticker.toUpperCase();
    setWatchlists(prev => prev.map(l =>
      l.id === listId && !l.tickers.includes(t)
        ? { ...l, tickers: [...l.tickers, t] }
        : l
    ));
  }, []);

  const removeTicker = useCallback((listId: string, ticker: string) => {
    const t = ticker.toUpperCase();
    setWatchlists(prev => prev.map(l =>
      l.id === listId ? { ...l, tickers: l.tickers.filter(x => x !== t) } : l
    ));
  }, []);

  const isInList = useCallback((listId: string, ticker: string) => {
    const list = watchlists.find(l => l.id === listId);
    return list?.tickers.includes(ticker.toUpperCase()) ?? false;
  }, [watchlists]);

  const getListsForTicker = useCallback((ticker: string) => {
    const t = ticker.toUpperCase();
    return watchlists.filter(l => l.tickers.includes(t)).map(l => l.name);
  }, [watchlists]);

  return {
    watchlists,
    createList,
    deleteList,
    renameList,
    addTicker,
    removeTicker,
    isInList,
    getListsForTicker,
  };
}

/** Hook para gerenciar favoritos */
export function useFavorites() {
  const [favorites, setFavorites] = useState<Set<string>>(loadFavorites);

  useEffect(() => {
    saveFavorites(favorites);
  }, [favorites]);

  const toggleFavorite = useCallback((ticker: string) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) {
        next.delete(ticker);
      } else {
        next.add(ticker);
      }
      return next;
    });
  }, []);

  const isFavorite = useCallback((ticker: string) => favorites.has(ticker), [favorites]);

  return { favorites, toggleFavorite, isFavorite };
}

/**
 * Calcula o perfil de investidor baseado na composição da carteira.
 * Usa a proporção de segmentos para classificar.
 */
export function calculateInvestorProfile(
  assets: PortfolioAsset[],
  sectorMap: Record<string, string>
): { profile: string; description: string; riskLevel: number } {
  if (assets.length === 0) {
    return { profile: "Sem carteira", description: "Adicione FIIs para identificar seu perfil", riskLevel: 0 };
  }

  const totalValue = assets.reduce((s, a) => s + a.quantity * a.avgPrice, 0);
  if (totalValue === 0) {
    return { profile: "Sem carteira", description: "Adicione FIIs para identificar seu perfil", riskLevel: 0 };
  }

  // Calculate sector weights
  const sectorWeights: Record<string, number> = {};
  for (const a of assets) {
    const sector = sectorMap[a.ticker] || "Outros";
    const value = a.quantity * a.avgPrice;
    sectorWeights[sector] = (sectorWeights[sector] || 0) + value / totalValue;
  }

  // Papel (CRI) = higher risk/yield, Logística/Shopping = moderate, FoF = conservative
  const papelWeight = sectorWeights["Papel (CRI)"] || 0;
  const tijoloPeso = (sectorWeights["Logística"] || 0) + (sectorWeights["Shopping"] || 0) + (sectorWeights["Lajes Corp."] || 0);
  const fofWeight = sectorWeights["Fundo de Fundos"] || 0;
  const numAssets = assets.length;

  let riskLevel = 50; // base

  // More papel = more aggressive
  riskLevel += papelWeight * 30;
  // More tijolo = more conservative
  riskLevel -= tijoloPeso * 10;
  // FoF = very conservative
  riskLevel -= fofWeight * 20;
  // Diversification reduces risk
  if (numAssets >= 8) riskLevel -= 10;
  else if (numAssets <= 3) riskLevel += 15;

  riskLevel = Math.max(0, Math.min(100, riskLevel));

  if (riskLevel >= 70) {
    return {
      profile: "Agressivo",
      description: `Alta concentração em papéis de crédito (${(papelWeight * 100).toFixed(0)}%). Busca yield máximo com maior volatilidade.`,
      riskLevel: Math.round(riskLevel),
    };
  }
  if (riskLevel >= 45) {
    return {
      profile: "Moderado",
      description: `Carteira equilibrada entre tijolo e papel. ${numAssets} ativos em ${Object.keys(sectorWeights).length} segmentos.`,
      riskLevel: Math.round(riskLevel),
    };
  }
  return {
    profile: "Conservador",
    description: `Foco em ativos de tijolo e FoFs. Prioriza estabilidade e previsibilidade de renda.`,
    riskLevel: Math.round(riskLevel),
  };
}
