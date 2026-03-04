"""
data/data_loader.py

Responsável por buscar e cachear dados históricos de preços e dividendos
de FIIs via yfinance. Salva os dados localmente em CSV para evitar
requisições repetidas à API.
"""

import os
import csv
import datetime
from typing import Optional

# Verificação de dependências opcionais
try:
    import yfinance as yf
    import pandas as pd
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

# Diretórios de cache
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRICES_DIR = os.path.join(_BASE_DIR, "historical_prices")
DIVIDENDS_DIR = os.path.join(_BASE_DIR, "historical_dividends")


def _ensure_dirs() -> None:
    """Cria os diretórios de cache se não existirem."""
    os.makedirs(PRICES_DIR, exist_ok=True)
    os.makedirs(DIVIDENDS_DIR, exist_ok=True)


def _cache_path(directory: str, ticker: str, suffix: str = "prices") -> str:
    """Retorna o caminho do arquivo CSV de cache para um ticker."""
    safe_ticker = ticker.replace(".", "_").upper()
    return os.path.join(directory, f"{safe_ticker}_{suffix}.csv")


def _load_csv(path: str) -> list[dict]:
    """Carrega um CSV de cache e retorna lista de dicts."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _save_csv(path: str, data: list[dict], fieldnames: list[str]) -> None:
    """Salva uma lista de dicts em CSV."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)


def fetch_prices(
    ticker: str,
    start_date: str,
    end_date: str,
    frequency: str = "1mo",
    force_refresh: bool = False,
) -> list[dict]:
    """
    Busca preços históricos mensais de um ticker (FII ou índice).

    Adiciona sufixo .SA automaticamente para ativos brasileiros se necessário.
    Resultados são cacheados em CSV em data/historical_prices/.

    Args:
        ticker (str): Código do ativo, ex: 'MXRF11' ou '^IFIX'.
        start_date (str): Data inicial no formato 'YYYY-MM-DD'.
        end_date (str): Data final no formato 'YYYY-MM-DD'.
        frequency (str): Frequência dos dados. Default: '1mo' (mensal).
        force_refresh (bool): Forçar nova busca ignorando cache.

    Returns:
        list[dict]: Lista de dicts com campos 'date', 'open', 'high', 'low',
                    'close', 'volume'. Ordenada por data crescente.

    Raises:
        ImportError: Se yfinance não estiver instalado.
        ValueError: Se o ticker for inválido ou não retornar dados.
    """
    if not HAS_YFINANCE:
        raise ImportError(
            "yfinance não instalado. Execute: pip install yfinance pandas"
        )

    _ensure_dirs()
    cache_file = _cache_path(PRICES_DIR, ticker, "prices")

    if not force_refresh and os.path.exists(cache_file):
        rows = _load_csv(cache_file)
        if rows:
            # Filtra pelo período solicitado
            filtered = [
                r for r in rows
                if start_date <= r["date"] <= end_date
            ]
            if filtered:
                return filtered

    # Adicionar sufixo .SA para FIIs brasileiros (mas não para índices como ^IFIX)
    yf_ticker = ticker if ticker.startswith("^") else (
        ticker if ticker.endswith(".SA") else f"{ticker}.SA"
    )

    try:
        raw = yf.download(
            yf_ticker,
            start=start_date,
            end=end_date,
            interval=frequency,
            auto_adjust=True,
            progress=False,
        )
    except Exception as e:
        raise ValueError(f"Erro ao buscar dados de '{ticker}' via yfinance: {e}")

    if raw is None or raw.empty:
        raise ValueError(
            f"Nenhum dado retornado para '{ticker}'. Verifique o ticker e o período."
        )

    records = []
    for date_idx, row in raw.iterrows():
        date_str = str(date_idx)[:10]
        records.append({
            "date": date_str,
            "open": round(float(row.get("Open", row.get("open", 0))), 4),
            "high": round(float(row.get("High", row.get("high", 0))), 4),
            "low": round(float(row.get("Low", row.get("low", 0))), 4),
            "close": round(float(row.get("Close", row.get("close", 0))), 4),
            "volume": int(row.get("Volume", row.get("volume", 0))),
        })

    if records:
        _save_csv(cache_file, records, ["date", "open", "high", "low", "close", "volume"])

    return [r for r in records if start_date <= r["date"] <= end_date]


def fetch_dividends(
    ticker: str,
    start_date: str,
    end_date: str,
    force_refresh: bool = False,
) -> list[dict]:
    """
    Busca histórico de proventos (dividendos) de um FII via yfinance.

    Args:
        ticker (str): Código do FII, ex: 'MXRF11'.
        start_date (str): Data inicial no formato 'YYYY-MM-DD'.
        end_date (str): Data final no formato 'YYYY-MM-DD'.
        force_refresh (bool): Forçar nova busca ignorando cache.

    Returns:
        list[dict]: Lista de dicts com campos 'date' e 'dividend'.
                    Ordenada por data crescente.

    Raises:
        ImportError: Se yfinance não estiver instalado.
    """
    if not HAS_YFINANCE:
        raise ImportError(
            "yfinance não instalado. Execute: pip install yfinance pandas"
        )

    _ensure_dirs()
    cache_file = _cache_path(DIVIDENDS_DIR, ticker, "dividends")

    if not force_refresh and os.path.exists(cache_file):
        rows = _load_csv(cache_file)
        if rows:
            return [r for r in rows if start_date <= r["date"] <= end_date]

    yf_ticker = ticker if ticker.startswith("^") else (
        ticker if ticker.endswith(".SA") else f"{ticker}.SA"
    )

    try:
        ticker_obj = yf.Ticker(yf_ticker)
        divs = ticker_obj.dividends
    except Exception as e:
        raise ValueError(f"Erro ao buscar dividendos de '{ticker}': {e}")

    records = []
    if divs is not None and not divs.empty:
        for date_idx, value in divs.items():
            date_str = str(date_idx)[:10]
            records.append({
                "date": date_str,
                "dividend": round(float(value), 6),
            })

    if records:
        _save_csv(cache_file, records, ["date", "dividend"])

    return [r for r in records if start_date <= r["date"] <= end_date]


def get_close_prices(prices: list[dict]) -> list[float]:
    """
    Extrai a série de preços de fechamento de uma lista retornada por fetch_prices.

    Args:
        prices (list[dict]): Lista retornada por fetch_prices.

    Returns:
        list[float]: Série de preços de fechamento, ordenada cronologicamente.
    """
    return [float(p["close"]) for p in prices]


def calculate_monthly_returns(close_prices: list[float]) -> list[float]:
    """
    Calcula a série de retornos mensais percentuais a partir de preços de fechamento.

    Args:
        close_prices (list[float]): Série de preços de fechamento mensais.

    Returns:
        list[float]: Série de retornos mensais. Primeiro elemento é 0 (sem retorno anterior).
    """
    if len(close_prices) < 2:
        return [0.0] * len(close_prices)

    returns = [0.0]
    for i in range(1, len(close_prices)):
        prev = close_prices[i - 1]
        curr = close_prices[i]
        ret = (curr / prev - 1.0) if prev > 0 else 0.0
        returns.append(ret)

    return returns


def get_available_cache(directory: str) -> list[str]:
    """
    Lista os tickers com dados cacheados em um diretório.

    Args:
        directory (str): Caminho do diretório (PRICES_DIR ou DIVIDENDS_DIR).

    Returns:
        list[str]: Lista de tickers disponíveis no cache.
    """
    if not os.path.exists(directory):
        return []
    tickers = []
    for fname in os.listdir(directory):
        if fname.endswith(".csv"):
            # Formato: TICKER_prices.csv ou TICKER_dividends.csv
            parts = fname.replace(".csv", "").rsplit("_", 1)
            if parts:
                tickers.append(parts[0])
    return sorted(set(tickers))
