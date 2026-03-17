"""
data/cvm_b3_client.py

Cliente para dados oficiais da CVM e B3.
Fontes:
- CVM Dados Abertos: proventos de FIIs (distribuicoes oficiais)
- B3 API publica: cotacoes, volumes, composicao IFIX

A CVM disponibiliza dados de FIIs via portal de dados abertos:
https://dados.cvm.gov.br/dados/FII/

A B3 tem endpoints publicos para composicao de indices e cotacoes.
"""

import csv
import datetime
import io
import json
import sqlite3
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)

try:
    import requests

    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

HAS_DEPS = _HAS_REQUESTS

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# CVM Dados Abertos — portal oficial
_CVM_FII_INFO_URL = "https://dados.cvm.gov.br/dados/FII/CAD/DADOS/inf_cadastral_fi.csv"
_CVM_FII_MONTHLY_URL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_{year}{month:02d}.csv"
_CVM_FII_PROVENTO_URL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_complemento_{year}{month:02d}.csv"

# B3 endpoints publicos
_B3_IFIX_URL = "https://sistemaswebb3-listados.b3.com.br/indexPage/day/IFIX?language=pt-br"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

_CACHE_DB = "alphacota_fundamentals.db"
_CACHE_TTL_HOURS = 48  # CVM data is monthly, can cache longer


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _init_cache(db_path: str = _CACHE_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cvm_cache (
            key TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            data_json TEXT NOT NULL,
            PRIMARY KEY (key)
        )
    """)
    conn.commit()
    return conn


def _get_cached(conn: sqlite3.Connection, key: str, ttl_hours: int = _CACHE_TTL_HOURS) -> Optional[str]:
    row = conn.execute(
        "SELECT data_json, fetched_at FROM cvm_cache WHERE key = ?",
        (key,),
    ).fetchone()
    if not row:
        return None
    fetched_at = datetime.datetime.fromisoformat(row["fetched_at"])
    age = datetime.datetime.now() - fetched_at
    if age.total_seconds() > ttl_hours * 3600:
        return None
    return row["data_json"]


def _save_cache(conn: sqlite3.Connection, key: str, data_json: str) -> None:
    now = datetime.datetime.now().isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO cvm_cache (key, fetched_at, data_json) VALUES (?, ?, ?)",
        (key, now, data_json),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# CVM — Cadastro de FIIs
# ---------------------------------------------------------------------------

def fetch_cvm_fii_registry(db_path: str = _CACHE_DB) -> list[dict]:
    """
    Busca cadastro oficial de FIIs na CVM.
    Retorna lista com: CNPJ, nome, ticker, administrador, gestor, tipo.

    Fonte: https://dados.cvm.gov.br/dados/FII/CAD/DADOS/
    """
    if not HAS_DEPS:
        return []

    conn = _init_cache(db_path)
    try:
        cached = _get_cached(conn, "cvm_registry", ttl_hours=168)  # 1 week
        if cached:
            return json.loads(cached)

        resp = requests.get(
            _CVM_FII_INFO_URL,
            headers={"User-Agent": _USER_AGENT},
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning("CVM registry retornou %d", resp.status_code)
            return []

        # CVM CSV uses latin-1 encoding
        content = resp.content.decode("latin-1")
        reader = csv.DictReader(io.StringIO(content), delimiter=";")

        results: list[dict] = []
        for row in reader:
            # Filter only FIIs with active tickers
            sit = row.get("SIT", "").strip()
            if sit != "EM FUNCIONAMENTO NORMAL":
                continue

            ticker = row.get("CD_CVM_TICKER", row.get("TP_FUNDO", "")).strip()
            results.append({
                "cnpj": row.get("CNPJ_FUNDO", "").strip(),
                "nome": row.get("DENOM_SOCIAL", "").strip(),
                "administrador": row.get("ADMIN", "").strip(),
                "gestor": row.get("GESTOR", "").strip(),
                "tipo": row.get("TP_FUNDO", "").strip(),
                "situacao": sit,
                "inicio": row.get("DT_INI_ATIV", "").strip(),
            })

        _save_cache(conn, "cvm_registry", json.dumps(results, ensure_ascii=False))
        logger.info("CVM registry: %d FIIs carregados", len(results))
        return results

    except Exception as e:
        logger.error("Erro ao buscar cadastro CVM: %s", e)
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CVM — Proventos mensais
# ---------------------------------------------------------------------------

def fetch_cvm_proventos(
    year: Optional[int] = None,
    month: Optional[int] = None,
    db_path: str = _CACHE_DB,
) -> list[dict]:
    """
    Busca proventos (dividendos) oficiais de FIIs na CVM.
    Dados mensais com valor distribuido por cota.

    Args:
        year: Ano (default: ano atual ou anterior).
        month: Mes (default: mes atual - 1).
        db_path: Caminho do cache.

    Returns:
        Lista de dicts com: ticker, cnpj, data_pagamento, valor_provento.
    """
    if not HAS_DEPS:
        return []

    now = datetime.datetime.now()
    if year is None:
        year = now.year
    if month is None:
        month = now.month - 1
        if month < 1:
            month = 12
            year -= 1

    cache_key = f"cvm_proventos_{year}_{month:02d}"
    conn = _init_cache(db_path)

    try:
        cached = _get_cached(conn, cache_key, ttl_hours=168)
        if cached:
            return json.loads(cached)

        url = _CVM_FII_PROVENTO_URL.format(year=year, month=month)
        resp = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=30,
        )

        if resp.status_code == 404:
            # Try the monthly info file instead
            url = _CVM_FII_MONTHLY_URL.format(year=year, month=month)
            resp = requests.get(
                url,
                headers={"User-Agent": _USER_AGENT},
                timeout=30,
            )

        if resp.status_code != 200:
            logger.warning("CVM proventos retornou %d para %d/%02d", resp.status_code, year, month)
            return []

        content = resp.content.decode("latin-1")
        reader = csv.DictReader(io.StringIO(content), delimiter=";")

        results: list[dict] = []
        for row in reader:
            # Try to extract provento-related fields
            valor = row.get("VL_PROVENTO", row.get("VL_RENDIMENTO", "0"))
            try:
                valor_f = float(valor.replace(",", ".")) if valor else 0
            except (ValueError, TypeError):
                valor_f = 0

            if valor_f <= 0:
                continue

            results.append({
                "cnpj": row.get("CNPJ_FUNDO", "").strip(),
                "nome": row.get("DENOM_SOCIAL", row.get("NM_FUNDO_COTA", "")).strip(),
                "data_referencia": row.get("DT_COMPTC", row.get("DT_REF", "")).strip(),
                "data_pagamento": row.get("DT_PAGTO", "").strip(),
                "valor_provento": valor_f,
                "tipo": row.get("TP_PROVENTO", row.get("TP_EVENTO", "")).strip(),
            })

        _save_cache(conn, cache_key, json.dumps(results, ensure_ascii=False))
        logger.info("CVM proventos %d/%02d: %d registros", year, month, len(results))
        return results

    except Exception as e:
        logger.error("Erro ao buscar proventos CVM %d/%02d: %s", year, month, e)
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# B3 — Composicao IFIX
# ---------------------------------------------------------------------------

def fetch_ifix_composition(db_path: str = _CACHE_DB) -> list[dict]:
    """
    Busca composicao atual do indice IFIX da B3.
    Retorna: ticker, participacao (%), quantidade teorica.
    """
    if not HAS_DEPS:
        return []

    conn = _init_cache(db_path)
    try:
        cached = _get_cached(conn, "b3_ifix", ttl_hours=24)
        if cached:
            return json.loads(cached)

        resp = requests.get(
            _B3_IFIX_URL,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "application/json",
            },
            timeout=15,
        )

        if resp.status_code != 200:
            logger.warning("B3 IFIX retornou %d", resp.status_code)
            return []

        data = resp.json()
        results: list[dict] = []

        # B3 response format varies, try common patterns
        items = data if isinstance(data, list) else data.get("results", data.get("data", []))

        for item in items:
            ticker = item.get("cod", item.get("ticker", item.get("code", ""))).strip()
            if not ticker:
                continue

            results.append({
                "ticker": ticker,
                "nome": item.get("asset", item.get("name", "")).strip(),
                "participacao": float(item.get("part", item.get("participation", 0))),
                "quantidade_teorica": float(item.get("theoricalQty", item.get("qty", 0))),
            })

        if results:
            _save_cache(conn, "b3_ifix", json.dumps(results, ensure_ascii=False))
            logger.info("B3 IFIX: %d FIIs na composicao", len(results))

        return results

    except Exception as e:
        logger.error("Erro ao buscar composicao IFIX: %s", e)
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Funcoes de enriquecimento
# ---------------------------------------------------------------------------

def enrich_with_cvm_data(
    ticker: str,
    existing_data: dict,
    db_path: str = _CACHE_DB,
) -> dict:
    """
    Enriquece dados de um FII com informacoes oficiais da CVM e B3.
    Nao sobrescreve dados existentes, apenas complementa campos vazios.
    """
    enriched = dict(existing_data)

    # Try IFIX composition for participation weight
    ifix = fetch_ifix_composition(db_path)
    for item in ifix:
        if item["ticker"].upper() == ticker.upper():
            enriched.setdefault("ifix_participacao", item["participacao"])
            enriched.setdefault("ifix_quantidade_teorica", item["quantidade_teorica"])
            enriched["_in_ifix"] = True
            break
    else:
        enriched.setdefault("_in_ifix", False)

    return enriched
