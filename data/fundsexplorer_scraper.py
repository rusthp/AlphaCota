"""
data/fundsexplorer_scraper.py

Coletor de dados complementares de FIIs via FundsExplorer.
Complementa o StatusInvest com dados adicionais:
- Ranking de FIIs
- Dados de proventos (historico de dividendos)
- Dados patrimoniais
- Numero de cotistas

Usa cache SQLite compartilhado com fundamentals_scraper.
"""

import datetime
import json
import sqlite3
import random
import time
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)

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

HAS_DEPS = _HAS_REQUESTS and _HAS_BS4

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_FUNDS_EXPLORER_RANKING_URL = "https://www.fundsexplorer.com.br/ranking"
_FUNDS_EXPLORER_FII_URL = "https://www.fundsexplorer.com.br/funds/{ticker}"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

_CACHE_DB = "alphacota_fundamentals.db"
_CACHE_TTL_HOURS = 24


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _init_cache(db_path: str = _CACHE_DB) -> sqlite3.Connection:
    """Inicializa tabela de cache para FundsExplorer."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fundsexplorer_cache (
            ticker TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            data_json TEXT NOT NULL,
            PRIMARY KEY (ticker)
        )
    """)
    conn.commit()
    return conn


def _get_cached(conn: sqlite3.Connection, ticker: str, ttl_hours: int = _CACHE_TTL_HOURS) -> Optional[dict]:
    """Retorna dados do cache se validos."""
    row = conn.execute(
        "SELECT data_json, fetched_at FROM fundsexplorer_cache WHERE ticker = ?",
        (ticker,),
    ).fetchone()
    if not row:
        return None
    fetched_at = datetime.datetime.fromisoformat(row["fetched_at"])
    age = datetime.datetime.now() - fetched_at
    if age.total_seconds() > ttl_hours * 3600:
        return None
    data = json.loads(row["data_json"])
    data["_source"] = "fundsexplorer_cache"
    return data


def _save_cache(conn: sqlite3.Connection, ticker: str, data: dict) -> None:
    """Salva dados no cache."""
    now = datetime.datetime.now().isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO fundsexplorer_cache (ticker, fetched_at, data_json) VALUES (?, ?, ?)",
        (ticker, now, json.dumps(data, ensure_ascii=False)),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_br_number(text: str) -> float:
    """Converte numero BR (1.234,56) para float."""
    if not text or text.strip() in ("-", "N/A", "--", ""):
        return 0.0
    cleaned = text.strip().replace("R$", "").replace("%", "").strip()
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Scraping do ranking (bulk — todos os FIIs de uma vez)
# ---------------------------------------------------------------------------


def scrape_ranking(db_path: str = _CACHE_DB) -> list[dict]:
    """
    Faz scraping da pagina de ranking do FundsExplorer.
    Retorna lista com dados basicos de todos os FIIs listados.

    A pagina de ranking tem uma tabela com: ticker, setor, preco,
    DY, P/VP, liquidez, ultimo dividendo, patrimonio, cotistas.
    """
    if not HAS_DEPS:
        logger.warning("requests/bs4 nao instalados")
        return []

    try:
        resp = requests.get(
            _FUNDS_EXPLORER_RANKING_URL,
            headers={"User-Agent": _USER_AGENT},
            timeout=20,
        )
        if resp.status_code != 200:
            logger.warning("FundsExplorer ranking retornou %d", resp.status_code)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # A tabela de ranking pode estar em diferentes formatos
        table = soup.select_one("table#table-ranking, table.table-ranking, table")
        if not table:
            logger.warning("Tabela de ranking nao encontrada")
            return []

        rows = table.select("tbody tr")
        results: list[dict] = []
        conn = _init_cache(db_path)

        try:
            for row in rows:
                cells = row.select("td")
                if len(cells) < 5:
                    continue

                ticker_el = cells[0].select_one("a, span")
                if not ticker_el:
                    continue

                ticker = ticker_el.get_text(strip=True).upper()
                if not ticker or len(ticker) < 4:
                    continue

                data = {
                    "ticker": ticker,
                    "setor": cells[1].get_text(strip=True) if len(cells) > 1 else "",
                    "preco": _parse_br_number(cells[2].get_text(strip=True)) if len(cells) > 2 else 0,
                    "dy_12m": _parse_br_number(cells[3].get_text(strip=True)) if len(cells) > 3 else 0,
                    "pvp": _parse_br_number(cells[4].get_text(strip=True)) if len(cells) > 4 else 0,
                    "liquidez_diaria": _parse_br_number(cells[5].get_text(strip=True)) if len(cells) > 5 else 0,
                    "ultimo_dividendo": _parse_br_number(cells[6].get_text(strip=True)) if len(cells) > 6 else 0,
                    "patrimonio_liquido": _parse_br_number(cells[7].get_text(strip=True)) if len(cells) > 7 else 0,
                    "num_cotistas": _parse_br_number(cells[8].get_text(strip=True)) if len(cells) > 8 else 0,
                    "_source": "fundsexplorer",
                }

                results.append(data)
                _save_cache(conn, ticker, data)
        finally:
            conn.close()

        logger.info("FundsExplorer ranking: %d FIIs coletados", len(results))
        return results

    except Exception as e:
        logger.error("Erro ao scraper ranking FundsExplorer: %s", e)
        return []


# ---------------------------------------------------------------------------
# Scraping individual de FII (dados detalhados)
# ---------------------------------------------------------------------------


def scrape_fii_detail(ticker: str, db_path: str = _CACHE_DB) -> Optional[dict]:
    """
    Faz scraping da pagina individual de um FII no FundsExplorer.
    Retorna dados detalhados: patrimonio, cotistas, historico de dividendos, etc.
    """
    if not HAS_DEPS:
        return None

    ticker = ticker.replace(".SA", "").upper()

    # Check cache first
    conn = _init_cache(db_path)
    try:
        cached = _get_cached(conn, ticker)
        if cached:
            return cached
    finally:
        conn.close()

    try:
        url = _FUNDS_EXPLORER_FII_URL.format(ticker=ticker.lower())
        resp = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning("FundsExplorer retornou %d para %s", resp.status_code, ticker)
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        data: dict = {"ticker": ticker, "_source": "fundsexplorer"}

        # Extract indicators from indicator cards
        for item in soup.select(".indicator-box, .indicators .item, .fund-indicator"):
            title_el = item.select_one(".title, .label, span.name")
            value_el = item.select_one(".value, span.value, strong")
            if title_el and value_el:
                key = title_el.get_text(strip=True).upper()
                val = value_el.get_text(strip=True)

                if "DIVIDEND YIELD" in key or "DY" in key:
                    data["dy_12m"] = _parse_br_number(val)
                elif "P/VP" in key:
                    data["pvp"] = _parse_br_number(val)
                elif "ÚLTIMO RENDIMENTO" in key or "ULTIMO RENDIMENTO" in key:
                    data["ultimo_dividendo"] = _parse_br_number(val)
                elif "PATRIMÔNIO" in key or "PATRIMONIO" in key:
                    data["patrimonio_liquido"] = _parse_br_number(val)
                elif "COTISTA" in key:
                    data["num_cotistas"] = _parse_br_number(val)
                elif "LIQUIDEZ" in key:
                    data["liquidez_diaria"] = _parse_br_number(val)
                elif "VACÂNCIA" in key or "VACANCIA" in key:
                    data["vacancia"] = _parse_br_number(val)

        # Extract dividend history table if available
        div_table = soup.select_one("table.dividends-table, #dividends-table, table")
        if div_table:
            div_rows = div_table.select("tbody tr")
            dividendos: list[dict] = []
            for row in div_rows[:12]:  # Ultimos 12 meses
                cells = row.select("td")
                if len(cells) >= 2:
                    dividendos.append(
                        {
                            "data": cells[0].get_text(strip=True),
                            "valor": _parse_br_number(cells[1].get_text(strip=True)),
                        }
                    )
            if dividendos:
                data["historico_dividendos"] = dividendos

        # Save to cache
        conn = _init_cache(db_path)
        try:
            _save_cache(conn, ticker, data)
        finally:
            conn.close()

        return data

    except Exception as e:
        logger.error("Erro ao scraper FundsExplorer para %s: %s", ticker, e)
        return None


# ---------------------------------------------------------------------------
# API Publica
# ---------------------------------------------------------------------------


def fetch_fundsexplorer_data(
    ticker: str,
    db_path: str = _CACHE_DB,
) -> Optional[dict]:
    """
    Busca dados do FundsExplorer para um FII, com cache.

    Args:
        ticker: Codigo do FII.
        db_path: Caminho do banco de cache.

    Returns:
        dict com dados ou None.
    """
    ticker = ticker.replace(".SA", "").upper()

    # Try cache first
    conn = _init_cache(db_path)
    try:
        cached = _get_cached(conn, ticker)
        if cached:
            return cached
    finally:
        conn.close()

    # Try scraping
    return scrape_fii_detail(ticker, db_path)


def fetch_fundsexplorer_bulk(
    tickers: list[str],
    db_path: str = _CACHE_DB,
) -> dict[str, dict]:
    """
    Busca dados do FundsExplorer para multiplos FIIs.
    Primeiro tenta o ranking (bulk), depois individual para os faltantes.
    """
    results: dict[str, dict] = {}

    # Try cache first for all
    conn = _init_cache(db_path)
    try:
        missing: list[str] = []
        for ticker in tickers:
            cached = _get_cached(conn, ticker.upper())
            if cached:
                results[ticker.upper()] = cached
            else:
                missing.append(ticker.upper())
    finally:
        conn.close()

    if not missing:
        return results

    # Try ranking page (gets all FIIs at once)
    ranking = scrape_ranking(db_path)
    ranking_map = {r["ticker"]: r for r in ranking}

    for ticker in missing:
        if ticker in ranking_map:
            results[ticker] = ranking_map[ticker]

    # Individual scraping for still-missing tickers (with rate limiting)
    still_missing = [t for t in missing if t not in results]
    for ticker in still_missing[:5]:  # Limit to 5 to avoid rate limiting
        data = scrape_fii_detail(ticker, db_path)
        if data:
            results[ticker] = data
        delay = random.uniform(1.5, 3.0)
        time.sleep(delay)

    return results
