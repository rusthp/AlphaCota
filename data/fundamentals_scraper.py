"""
data/fundamentals_scraper.py

Coletor de dados fundamentalistas de FIIs brasileiros.

Busca indicadores como DY, P/VP, vacância, dívida/PL e liquidez diária
via scraping do Status Invest, com cache local em SQLite.

Fallback: retorna dados estimados do cache anterior ou valores padrão.
"""

import sqlite3
import datetime
import json
import random
import time
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Importação defensiva de requests + bs4
# ---------------------------------------------------------------------------

try:
    import requests

    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

try:
    from bs4 import BeautifulSoup

    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

HAS_SCRAPER_DEPS = _HAS_REQUESTS and _HAS_BS4


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_STATUS_INVEST_URL = "https://statusinvest.com.br/fundos-imobiliarios/{ticker}"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_CACHE_DB = "alphacota_fundamentals.db"
_CACHE_TTL_HOURS = 24

# Valores padrão para fallback total — None indica "sem dados reais disponíveis"
_DEFAULT_FUNDAMENTALS: dict = {
    "dividend_yield": 0.08,
    "dividend_consistency": None,  # calculado via histórico CSV; None se indisponível
    "pvp": 1.0,
    "debt_ratio": None,  # hardcoded 0.3 foi removido — None = sem dado real
    "vacancy_rate": None,  # hardcoded 0.05 foi removido — None = sem dado real
    "revenue_growth_12m": 0.0,
    "earnings_growth_12m": 0.0,
    "daily_liquidity": 500_000.0,
    "net_asset_value": 0.0,
    "last_dividend": None,  # 0.0 hardcoded foi removido
}


# ---------------------------------------------------------------------------
# Cache SQLite
# ---------------------------------------------------------------------------


def _init_cache_db(db_path: str = _CACHE_DB) -> sqlite3.Connection:
    """Inicializa o banco de cache de fundamentalistas."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fundamentals_cache (
            ticker TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            data_json TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'scraper',
            PRIMARY KEY (ticker)
        )
    """)
    conn.commit()
    return conn


def _get_cached(
    conn: sqlite3.Connection,
    ticker: str,
    ttl_hours: int = _CACHE_TTL_HOURS,
) -> Optional[dict]:
    """
    Retorna dados do cache se ainda válidos (dentro do TTL).

    Args:
        conn: Conexão SQLite.
        ticker: Código do FII.
        ttl_hours: Tempo de vida do cache em horas.

    Returns:
        dict ou None se cache expirado ou inexistente.
    """
    row = conn.execute(
        "SELECT data_json, fetched_at FROM fundamentals_cache WHERE ticker = ?",
        (ticker,),
    ).fetchone()

    if not row:
        return None

    fetched_at = datetime.datetime.fromisoformat(row["fetched_at"])
    age = datetime.datetime.now() - fetched_at

    if age.total_seconds() > ttl_hours * 3600:
        return None  # Cache expirado

    data = json.loads(row["data_json"])
    data["_cache_age_hours"] = round(age.total_seconds() / 3600, 1)
    data["_source"] = "cache"
    return data


def _save_cache(
    conn: sqlite3.Connection,
    ticker: str,
    data: dict,
    source: str = "scraper",
) -> None:
    """Salva ou atualiza dados no cache."""
    now = datetime.datetime.now().isoformat()
    data_json = json.dumps(data, ensure_ascii=False)
    conn.execute(
        """
        INSERT OR REPLACE INTO fundamentals_cache (ticker, fetched_at, data_json, source)
        VALUES (?, ?, ?, ?)
        """,
        (ticker, now, data_json, source),
    )
    conn.commit()


def _get_stale_cache(conn: sqlite3.Connection, ticker: str) -> Optional[dict]:
    """
    Retorna dados do cache mesmo que expirados (fallback gracioso).

    Returns:
        dict ou None se não existe no cache.
    """
    row = conn.execute(
        "SELECT data_json, fetched_at FROM fundamentals_cache WHERE ticker = ?",
        (ticker,),
    ).fetchone()

    if not row:
        return None

    data = json.loads(row["data_json"])
    data["_source"] = "stale_cache"
    fetched_at = datetime.datetime.fromisoformat(row["fetched_at"])
    age = datetime.datetime.now() - fetched_at
    data["_cache_age_hours"] = round(age.total_seconds() / 3600, 1)
    return data


# ---------------------------------------------------------------------------
# Enriquecimento com histórico local de dividendos
# ---------------------------------------------------------------------------

_HISTORICAL_DIVIDENDS_DIR = Path(__file__).parent / "historical_dividends"


def _enrich_with_history(result: dict, ticker: str) -> dict:
    """
    Enriquece o resultado do scraper com métricas calculadas a partir do
    histórico local de dividendos (CSV em data/historical_dividends/).

    Campos enriquecidos:
    - dividend_consistency: fração de meses com dividendo > 0 nos últimos 24 meses (0.0–1.0).
    - revenue_growth_12m: crescimento do dividendo médio (últimos 6 meses vs meses 7–18).
    - earnings_growth_12m: idêntico a revenue_growth_12m (proxy para FIIs).

    Args:
        result: Dicionário de indicadores já preenchido pelo scraper.
        ticker: Código do FII sem '.SA' (ex: 'MXRF11').

    Returns:
        dict atualizado com os campos enriquecidos.
    """
    try:
        import pandas as pd

        csv_path = _HISTORICAL_DIVIDENDS_DIR / f"{ticker}_dividends.csv"
        df = pd.read_csv(csv_path, parse_dates=["date"])

        if df.empty or "dividend" not in df.columns or "date" not in df.columns:
            return result

        df = df.sort_values("date").reset_index(drop=True)

        now = pd.Timestamp.now()
        cutoff_24m = now - pd.DateOffset(months=24)

        # --- dividend_consistency: months with non-zero dividend in last 24 months ---
        df_24m = df[df["date"] >= cutoff_24m].copy()
        if df_24m.empty:
            result["dividend_consistency"] = None
        else:
            non_zero = (df_24m["dividend"] > 0).sum()
            result["dividend_consistency"] = round(non_zero / 24, 4)

        # --- revenue_growth_12m / earnings_growth_12m ---
        cutoff_6m = now - pd.DateOffset(months=6)
        cutoff_18m = now - pd.DateOffset(months=18)

        recent = df[(df["date"] >= cutoff_6m) & (df["date"] < now)]["dividend"]
        older = df[(df["date"] >= cutoff_18m) & (df["date"] < cutoff_6m)]["dividend"]

        if len(recent) < 1 or len(older) < 1:
            result["revenue_growth_12m"] = 0.0
            result["earnings_growth_12m"] = 0.0
            return result

        avg_recent = recent.mean()
        avg_older = older.mean()

        if avg_older == 0:
            growth = 0.0
        else:
            growth = (avg_recent - avg_older) / avg_older

        # Clamp to -1.0 .. +1.0
        growth = max(-1.0, min(1.0, growth))
        growth = round(growth, 4)

        result["revenue_growth_12m"] = growth
        result["earnings_growth_12m"] = growth

    except FileNotFoundError:
        logger.debug(f"Histórico de dividendos não encontrado para {ticker}")
    except Exception as e:
        logger.warning(f"Erro ao enriquecer histórico de {ticker}: {e}")

    return result


# ---------------------------------------------------------------------------
# Scraping do Status Invest
# ---------------------------------------------------------------------------


def _parse_indicator(text: str) -> float:
    """
    Converte texto numérico BR para float.
    Ex: '10,50%' → 0.105, '1,02' → 1.02, 'R$ 0,09' → 0.09
    """
    if not text or text.strip() in ("-", "N/A", "--", ""):
        return 0.0
    cleaned = text.strip().replace("R$", "").replace("%", "").strip()
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _scrape_status_invest(ticker: str) -> Optional[dict]:
    """
    Faz scraping de indicadores fundamentalistas do Status Invest.

    Args:
        ticker: Código do FII sem '.SA' (ex: 'MXRF11').

    Returns:
        dict com indicadores ou None se falhar.
    """
    if not HAS_SCRAPER_DEPS:
        logger.warning("requests/bs4 não instalados. Instale: pip install requests beautifulsoup4")
        return None

    ticker_clean = ticker.replace(".SA", "").upper()
    url = _STATUS_INVEST_URL.format(ticker=ticker_clean.lower())

    try:
        response = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=15,
        )
        if response.status_code != 200:
            logger.warning(f"Status Invest retornou {response.status_code} para {ticker_clean}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Buscar indicadores nas divs com classe 'info'
        indicators: dict[str, str] = {}

        # Os indicadores ficam em containers com title e valor
        for item in soup.select("div.info"):
            title_el = item.select_one("h3.title, span.sub-value, .info-title")
            value_el = item.select_one("strong.value, .info-value, .value")
            if title_el and value_el:
                key = title_el.get_text(strip=True).upper()
                val = value_el.get_text(strip=True)
                indicators[key] = val

        # Buscar nos cards de indicadores (layout alternativo)
        for card in soup.select("[title]"):
            title = card.get("title", "").strip().upper()
            value_el = card.select_one("strong, .value")
            if title and value_el:
                val = value_el.get_text(strip=True)
                if val and val not in ("-", "--"):
                    indicators[title] = val

        if not indicators:
            logger.warning(f"Nenhum indicador encontrado para {ticker_clean}")
            return None

        # Extrair com mapeamento flexível
        dy_raw = 0.0
        pvp_raw = 0.0
        vacancy_raw = 0.0
        liquidity_raw = 0.0
        last_div_raw = 0.0
        patrimonio_raw = 0.0

        for key, val in indicators.items():
            k = key.upper()
            if "DIVIDEND YIELD" in k or "DY" == k or "DIV. YIELD" in k:
                dy_raw = _parse_indicator(val)
            elif "P/VP" in k or "P / VP" in k:
                pvp_raw = _parse_indicator(val)
            elif "VACÂNCIA" in k or "VACANCIA" in k:
                vacancy_raw = _parse_indicator(val)
            elif "LIQUIDEZ" in k and "DI" in k:
                liquidity_raw = _parse_indicator(val)
            elif "ÚLTIMO DIVIDENDO" in k or "ULTIMO DIVIDENDO" in k or "ÚLT. RENDIMENTO" in k:
                last_div_raw = _parse_indicator(val)
            elif "PATRIMÔNIO" in k or "PATRIMONIO" in k or "VAL. PATRIMONIAL" in k:
                patrimonio_raw = _parse_indicator(val)

        result = {
            "ticker": ticker_clean,
            "dividend_yield": round(dy_raw / 100, 4) if dy_raw > 1 else (dy_raw if dy_raw > 0 else None),
            "dividend_consistency": None,  # enriched below from historical CSV
            "pvp": pvp_raw if pvp_raw > 0 else None,
            "debt_ratio": None,  # não disponível no StatusInvest — requer CVM
            "vacancy_rate": (round(vacancy_raw / 100, 4) if vacancy_raw > 1 else vacancy_raw) if vacancy_raw > 0 else None,
            "revenue_growth_12m": 0.0,  # enriched below from historical CSV
            "earnings_growth_12m": 0.0,  # enriched below from historical CSV
            "daily_liquidity": liquidity_raw if liquidity_raw > 0 else None,
            "net_asset_value": patrimonio_raw if patrimonio_raw > 0 else None,
            "last_dividend": last_div_raw if last_div_raw > 0 else None,
            "_source": "scraper",
        }

        result = _enrich_with_history(result, ticker_clean)
        return result

    except requests.exceptions.Timeout:
        logger.warning(f"Timeout ao buscar {ticker_clean} no Status Invest")
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"Erro de rede ao buscar {ticker_clean}: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado ao scraper {ticker_clean}: {e}")
        return None


# ---------------------------------------------------------------------------
# API Pública
# ---------------------------------------------------------------------------


def fetch_fundamentals(
    ticker: str,
    db_path: str = _CACHE_DB,
    force_refresh: bool = False,
) -> dict:
    """
    Busca dados fundamentalistas de um FII com cache inteligente.

    Prioridade:
    1. Cache válido (< TTL) → retorna imediatamente
    2. Scraping do Status Invest → salva no cache
    3. Cache expirado (stale) → retorna com aviso
    4. Valores padrão conservadores → fallback total

    Args:
        ticker (str): Código do FII (ex: 'MXRF11').
        db_path (str): Caminho do banco de cache.
        force_refresh (bool): Ignorar cache e buscar dados novos.

    Returns:
        dict: Indicadores fundamentalistas com campo '_source' indicando a origem.
    """
    ticker = ticker.replace(".SA", "").upper()
    conn = _init_cache_db(db_path)

    try:
        # 1. Verificar cache válido
        if not force_refresh:
            cached = _get_cached(conn, ticker)
            if cached:
                return cached

        # 2. Tentar scraping
        scraped = _scrape_status_invest(ticker)
        if scraped:
            _save_cache(conn, ticker, scraped, source="scraper")
            return scraped

        # 3. Fallback: cache expirado
        stale = _get_stale_cache(conn, ticker)
        if stale:
            logger.info(f"Usando cache expirado para {ticker} (idade: {stale.get('_cache_age_hours', '?')}h)")
            return stale

        # 4. Fallback total: valores padrão
        default = {**_DEFAULT_FUNDAMENTALS, "ticker": ticker, "_source": "default"}
        return default

    finally:
        conn.close()


def fetch_fundamentals_bulk(
    tickers: list[str],
    db_path: str = _CACHE_DB,
    force_refresh: bool = False,
) -> dict[str, dict]:
    """
    Busca dados fundamentalistas para múltiplos FIIs.

    Args:
        tickers: Lista de tickers.
        db_path: Caminho do banco de cache.
        force_refresh: Forçar nova busca.

    Returns:
        dict[str, dict]: Mapa ticker → dados fundamentalistas.
    """
    results: dict[str, dict] = {}
    for ticker in tickers:
        f = fetch_fundamentals(ticker, db_path, force_refresh)
        results[ticker] = f

        # Rate limiting: aguarda 1.0 a 2.5 seg apenas se bateu no scraper (para evitar block)
        if f.get("_source") == "scraper":
            delay = random.uniform(1.0, 2.5)
            logger.debug(f"Rate limit: dormindo {delay:.2f}s após scraper de {ticker}")
            time.sleep(delay)

    return results


def save_manual_fundamentals(
    ticker: str,
    data: dict,
    db_path: str = _CACHE_DB,
) -> None:
    """
    Salva dados fundamentalistas inseridos manualmente.
    Útil para curadoria manual ou CSV importado.

    Args:
        ticker: Código do FII.
        data: Dicionário com indicadores.
        db_path: Caminho do banco de cache.
    """
    ticker = ticker.replace(".SA", "").upper()
    conn = _init_cache_db(db_path)
    try:
        enriched = {**_DEFAULT_FUNDAMENTALS, **data, "ticker": ticker, "_source": "manual"}
        _save_cache(conn, ticker, enriched, source="manual")
    finally:
        conn.close()


def import_csv_fundamentals(
    csv_path: str,
    db_path: str = _CACHE_DB,
) -> int:
    """
    Importa dados fundamentalistas de um CSV curado.

    Formato esperado: ticker, dividend_yield, pvp, debt_ratio, vacancy_rate, ...

    Args:
        csv_path: Caminho do arquivo CSV.
        db_path: Caminho do banco de cache.

    Returns:
        int: Número de FIIs importados.
    """
    import csv as csv_module

    conn = _init_cache_db(db_path)
    count = 0

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv_module.DictReader(f)
            for row in reader:
                ticker = row.get("ticker", "").strip().upper()
                if not ticker:
                    continue

                data = {"ticker": ticker, "_source": "csv_import"}
                for key in _DEFAULT_FUNDAMENTALS:
                    if key in row:
                        try:
                            data[key] = float(row[key])
                        except (ValueError, TypeError):
                            pass

                _save_cache(conn, ticker, {**_DEFAULT_FUNDAMENTALS, **data}, source="csv")
                count += 1
    finally:
        conn.close()

    return count


def get_cache_status(
    tickers: list[str],
    db_path: str = _CACHE_DB,
) -> dict:
    """
    Retorna o status do cache para uma lista de tickers.

    Returns:
        dict com contagens e detalhes por ticker.
    """
    conn = _init_cache_db(db_path)
    try:
        status = {"total": len(tickers), "cached": 0, "stale": 0, "missing": 0, "details": {}}

        for ticker in tickers:
            cached = _get_cached(conn, ticker)
            if cached:
                status["cached"] += 1
                status["details"][ticker] = "valid"
            else:
                stale = _get_stale_cache(conn, ticker)
                if stale:
                    status["stale"] += 1
                    status["details"][ticker] = f"stale ({stale.get('_cache_age_hours', '?')}h)"
                else:
                    status["missing"] += 1
                    status["details"][ticker] = "missing"

        return status
    finally:
        conn.close()
