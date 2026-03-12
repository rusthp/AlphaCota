"""
data/data_bridge.py

Ponte entre o data_loader (yfinance + cache) e os engines quant.

Fornece retornos mensais reais, último preço, dividendo mensal médio e
mapeamento setorial completo para uso imediato no dashboard.

Garante fallback transparente para dados sintéticos quando:
- yfinance não está instalado
- Ticker não encontrado na B3
- Cache vazio (roda offline)
"""

import os
import random
from typing import Optional


# Importação defensiva do data_loader
try:
    from data.data_loader import (
        fetch_prices,
        fetch_dividends,
        get_close_prices,
        calculate_monthly_returns,
        PRICES_DIR,
        DIVIDENDS_DIR,
        HAS_YFINANCE,
    )
    _HAS_LOADER = True
except ImportError:
    _HAS_LOADER = False
    HAS_YFINANCE = False
    PRICES_DIR = ""
    DIVIDENDS_DIR = ""


# ---------------------------------------------------------------------------
# Mapeamento setorial — importado do módulo universe (fonte única)
# ---------------------------------------------------------------------------

try:
    from data.universe import get_sector_map as _get_sector_map
    SECTOR_MAP: dict[str, str] = _get_sector_map()
except ImportError:
    # Fallback mínimo caso universe.py não esteja disponível
    SECTOR_MAP: dict[str, str] = {
        "MXRF11": "Papel (CRI)", "KNCR11": "Papel (CRI)", "RECR11": "Papel (CRI)",
        "HGLG11": "Logística", "XPLG11": "Logística", "BTLG11": "Logística",
        "XPML11": "Shopping", "MALL11": "Shopping", "VISC11": "Shopping",
        "BRCR11": "Lajes Corp.", "JSRE11": "Lajes Corp.",
        "BCFF11": "Fundo de Fundos", "HFOF11": "Fundo de Fundos",
    }

# Parâmetros de retorno sintético por setor (mu_mensal, sigma_mensal)
_SECTOR_PARAMS: dict[str, tuple[float, float]] = {
    "Papel (CRI)":     (0.0085, 0.020),
    "Logística":       (0.0090, 0.030),
    "Shopping":        (0.0075, 0.035),
    "Lajes Corp.":     (0.0065, 0.033),
    "Fundo de Fundos": (0.0080, 0.028),
    "Híbrido":         (0.0080, 0.028),
    "Saúde":           (0.0070, 0.032),
    "Agro":            (0.0080, 0.028),
    "Residencial":     (0.0075, 0.028),
    "Educacional":     (0.0070, 0.030),
    "Hotel":           (0.0065, 0.035),
    "Outros":          (0.0075, 0.028),
}

# Último preço aproximado por ticker (fallback offline)
_FALLBACK_PRICES: dict[str, float] = {
    "MXRF11": 10.05, "KNCR11": 97.80, "RECR11": 8.90, "MCCI11": 8.10,
    "HGLG11": 155.00, "XPLG11": 112.00, "BTLG11": 100.00, "VILG11": 98.00,
    "XPML11": 90.00, "MALL11": 97.00, "VISC11": 91.00, "HSML11": 83.00,
    "BRCR11": 60.00, "JSRE11": 75.00,
    "BCFF11": 72.00, "HFOF11": 68.00,
}

# Dividendo mensal aproximado R$/cota (fallback offline)
_FALLBACK_DIVIDENDS: dict[str, float] = {
    "MXRF11": 0.09, "KNCR11": 0.75, "RECR11": 0.07, "MCCI11": 0.07,
    "HGLG11": 1.10, "XPLG11": 0.72, "BTLG11": 0.65,
    "XPML11": 0.65, "MALL11": 0.68, "VISC11": 0.60,
    "BRCR11": 0.35, "JSRE11": 0.45,
    "BCFF11": 0.55, "HFOF11": 0.50,
}


# ---------------------------------------------------------------------------
# Geração de retornos sintéticos reproduzíveis
# ---------------------------------------------------------------------------

def _synthetic_returns(ticker: str, n_months: int = 36) -> list[float]:
    """Gera retornos mensais sintéticos realistas com base no setor do FII."""
    sector = SECTOR_MAP.get(ticker, "Outros")
    mu, sigma = _SECTOR_PARAMS.get(sector, _SECTOR_PARAMS["Outros"])

    rng = random.Random(hash(ticker) % 99991)
    # Componente de mercado (70%) + componente idiossincrático (30%)
    market = [rng.gauss(mu, sigma * 0.5) for _ in range(n_months)]
    idio   = [rng.gauss(0.0, sigma * 0.5) for _ in range(n_months)]
    return [round(m * 0.7 + i * 0.3, 6) for m, i in zip(market, idio)]


# ---------------------------------------------------------------------------
# API pública: obter retornos mensais reais (com fallback)
# ---------------------------------------------------------------------------

def load_returns(
    ticker: str,
    start_date: str,
    end_date: str,
    force_refresh: bool = False,
) -> tuple[list[float], str]:
    """
    Retorna (retornos_mensais, fonte) para um ticker.

    Tenta buscar dados reais via yfinance com cache local.
    Caso falhe (offline, ticker inválido, sem dados), usa dados sintéticos.

    Args:
        ticker (str): Código do FII, ex: 'MXRF11'.
        start_date (str): Data inicial 'YYYY-MM-DD'.
        end_date (str): Data final 'YYYY-MM-DD'.
        force_refresh (bool): Forçar nova busca da API.

    Returns:
        tuple: (lista de retornos mensais, 'real' | 'sintético')
    """
    if _HAS_LOADER and HAS_YFINANCE:
        try:
            prices = fetch_prices(ticker, start_date, end_date,
                                  frequency="1mo", force_refresh=force_refresh)
            if len(prices) >= 3:
                closes = get_close_prices(prices)
                returns = calculate_monthly_returns(closes)
                # Remove o primeiro 0.0 (sem retorno anterior)
                returns = [r for r in returns if r != 0.0] or returns
                return returns, "real"
            else:
                logger.warning(f"Poucos dados para {ticker} ({len(prices)}), usando fallback sintético.")
        except Exception as e:
            logger.warning(f"Erro ao buscar retornos para {ticker}: {e}. Fallback ativado.")

    # Fallback: retornos sintéticos
    import datetime
    try:
        d0 = datetime.date.fromisoformat(start_date)
        d1 = datetime.date.fromisoformat(end_date)
        n_months = max(3, (d1.year - d0.year) * 12 + (d1.month - d0.month))
    except Exception:
        n_months = 36

    return _synthetic_returns(ticker, n_months), "sintético"


def load_returns_bulk(
    tickers: list[str],
    start_date: str,
    end_date: str,
    force_refresh: bool = False,
) -> tuple[dict[str, list[float]], dict[str, str]]:
    """
    Carrega retornos mensais para múltiplos tickers em paralelo.

    Args:
        tickers (list[str]): Lista de tickers.
        start_date (str): Data inicial.
        end_date (str): Data final.
        force_refresh (bool): Forçar nova busca.

    Returns:
        tuple: (dict ticker → retornos, dict ticker → fonte)
    """
    return_series: dict[str, list[float]] = {}
    sources: dict[str, str] = {}

    for ticker in tickers:
        returns, source = load_returns(ticker, start_date, end_date, force_refresh)
        return_series[ticker] = returns
        sources[ticker] = source

    return return_series, sources


def load_last_price(ticker: str) -> tuple[float, str]:
    """
    Retorna (último preço de fechamento, 'real' | 'fallback').

    Args:
        ticker (str): Código do FII.

    Returns:
        tuple: (preço, fonte)
    """
    if _HAS_LOADER and HAS_YFINANCE:
        try:
            import datetime
            end = datetime.date.today().isoformat()
            start = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
            prices = fetch_prices(ticker, start, end, frequency="1d")
            if prices:
                p = float(prices[-1]["close"])
                if p > 0:
                    return round(p, 2), "real"
            logger.warning(f"Preço zero ou ausente para {ticker}, usando fallback.")
        except Exception as e:
            logger.warning(f"Erro ao buscar último preço de {ticker}: {e}. Fallback ativado.")

    return _FALLBACK_PRICES.get(ticker, 10.0), "fallback"


def load_monthly_dividend(ticker: str) -> tuple[float, str]:
    """
    Retorna (dividendo mensal médio dos últimos 12 meses, 'real' | 'fallback').

    Args:
        ticker (str): Código do FII.

    Returns:
        tuple: (dividendo R$/cota, fonte)
    """
    if _HAS_LOADER and HAS_YFINANCE:
        try:
            import datetime
            end = datetime.date.today().isoformat()
            start = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
            divs = fetch_dividends(ticker, start, end)
            if len(divs) >= 6:
                values = [float(d["dividend"]) for d in divs]
                avg = sum(values) / len(values)
                if avg > 0:
                    return float(round(avg, 4)), "real"
            logger.warning(f"Aviso: Sem média de dividendos válida para {ticker}, usando fallback.")
        except Exception as e:
            logger.warning(f"Erro ao buscar dividendos de {ticker}: {e}. Fallback ativado.")

    return _FALLBACK_DIVIDENDS.get(ticker, 0.07), "fallback"


def build_portfolio_from_tickers(
    tickers: list[str],
    quantities: dict[str, int] | None = None,
) -> list[dict]:
    """
    Constrói a estrutura de portfolio padrão para os engines.
    Busca preço atual e dividendo mensal com fallback automático.

    Args:
        tickers (list[str]): Lista de tickers.
        quantities (dict | None): Quantidades por ticker. Default: 100 cotas cada.

    Returns:
        list[dict]: Lista de dicts com ticker, quantidade, preco_atual, dividend_mensal.
    """
    portfolio = []
    for ticker in tickers:
        qty = (quantities or {}).get(ticker, 100)
        price, _ = load_last_price(ticker)
        div, _   = load_monthly_dividend(ticker)
        portfolio.append({
            "ticker":          ticker,
            "quantidade":      qty,
            "preco_atual":     price,
            "dividend_mensal": div,
        })
    return portfolio


def get_data_quality_report(
    tickers: list[str],
    start_date: str,
    end_date: str,
) -> dict:
    """
    Retorna um relatório resumindo quantos tickers usam dados reais vs sintéticos.

    Args:
        tickers (list[str]): Lista de tickers.
        start_date (str): Data inicial.
        end_date (str): Data final.

    Returns:
        dict: Relatório com contagens e lista de tickers por fonte.
    """
    _, sources = load_returns_bulk(tickers, start_date, end_date)

    real_tickers   = [t for t, s in sources.items() if s == "real"]
    synth_tickers  = [t for t, s in sources.items() if s == "sintético"]
    total = len(tickers)

    return {
        "total":           total,
        "real":            len(real_tickers),
        "sintetico":       len(synth_tickers),
        "pct_real":        round(len(real_tickers) / total * 100, 1) if total > 0 else 0.0,
        "tickers_reais":   real_tickers,
        "tickers_sintet":  synth_tickers,
        "yfinance_ativo":  HAS_YFINANCE,
        "data_inicio":     start_date,
        "data_fim":        end_date,
    }
