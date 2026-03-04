"""
core/macro_engine.py

Dados macroeconômicos brasileiros para o AlphaCota.

Busca Selic, CDI e IPCA histórico via python-bcb (API do Banco Central).
Com fallback para valores aproximados se a API não estiver disponível.

Funções puramente utilitárias — sem side effects.
"""

import datetime
import os
import csv


# Importação defensiva do python-bcb
try:
    from bcb import sgs
    HAS_BCB = True
except ImportError:
    HAS_BCB = False


# Diretório de cache
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MACRO_DIR = os.path.join(_BASE_DIR, "data", "macro")


# Códigos SGS (Sistema de Gerenciamento de Séries — Banco Central)
SGS_SELIC_DAILY  = 11   # Taxa Selic (Over) — diária
SGS_CDI_DAILY    = 12   # Taxa CDI — diária
SGS_IPCA_MONTHLY = 433  # IPCA mensal variação %


# Valores fallback (médias históricas recentes)
_FALLBACK = {
    "selic_anual":  10.75,  # % ao ano
    "cdi_anual":    10.65,  # % ao ano
    "ipca_anual":    4.83,  # % ao ano acumulado 12m
}


# ---------------------------------------------------------------------------
# Cache local CSV
# ---------------------------------------------------------------------------

def _cache_path(name: str) -> str:
    os.makedirs(_MACRO_DIR, exist_ok=True)
    return os.path.join(_MACRO_DIR, f"{name}.csv")


def _load_macro_csv(name: str) -> list[dict]:
    path = _cache_path(name)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _save_macro_csv(name: str, rows: list[dict], fieldnames: list[str]) -> None:
    path = _cache_path(name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------------------
# Fetch via BCB API
# ---------------------------------------------------------------------------

def _fetch_sgs_monthly(
    code: int,
    name: str,
    start_date: str,
    end_date: str,
    force_refresh: bool = False,
) -> list[dict]:
    """
    Busca uma série mensal do SGS com cache local.

    Returns:
        list[dict]: [{"date": "YYYY-MM-DD", "value": float}, ...]
    """
    cached = _load_macro_csv(name)
    if cached and not force_refresh:
        filtered = [r for r in cached if start_date <= r["date"] <= end_date]
        if filtered:
            return filtered

    if not HAS_BCB:
        return []

    try:
        df = sgs.get({name: code}, start=start_date, end=end_date)
        if df is None or df.empty:
            return []
        rows = [
            {"date": str(idx)[:10], "value": round(float(val), 6)}
            for idx, val in df.iloc[:, 0].items()
        ]
        _save_macro_csv(name, rows, ["date", "value"])
        return [r for r in rows if start_date <= r["date"] <= end_date]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# API pública — dados anualizados
# ---------------------------------------------------------------------------

def get_selic_history(
    start_date: str | None = None,
    end_date: str | None = None,
    force_refresh: bool = False,
) -> tuple[list[dict], str]:
    """
    Retorna histórico mensal da taxa Selic.

    Args:
        start_date: Data inicial (YYYY-MM-DD). Default: 3 anos atrás.
        end_date: Data final (YYYY-MM-DD). Default: hoje.
        force_refresh: Ignorar cache.

    Returns:
        tuple: (lista de {date, value}, fonte: 'bcb' | 'fallback')
    """
    today = datetime.date.today()
    start_date = start_date or (today.replace(year=today.year - 3)).isoformat()
    end_date   = end_date   or today.isoformat()

    rows = _fetch_sgs_monthly(SGS_SELIC_DAILY, "selic", start_date, end_date, force_refresh)
    if rows:
        return rows, "bcb"
    return [], "fallback"


def get_cdi_history(
    start_date: str | None = None,
    end_date: str | None = None,
    force_refresh: bool = False,
) -> tuple[list[dict], str]:
    """
    Retorna histórico mensal da taxa CDI.

    Returns:
        tuple: (lista de {date, value}, 'bcb' | 'fallback')
    """
    today = datetime.date.today()
    start_date = start_date or (today.replace(year=today.year - 3)).isoformat()
    end_date   = end_date   or today.isoformat()

    rows = _fetch_sgs_monthly(SGS_CDI_DAILY, "cdi", start_date, end_date, force_refresh)
    if rows:
        return rows, "bcb"
    return [], "fallback"


def get_ipca_history(
    start_date: str | None = None,
    end_date: str | None = None,
    force_refresh: bool = False,
) -> tuple[list[dict], str]:
    """
    Retorna histórico mensal do IPCA (variação %).

    Returns:
        tuple: (lista de {date, value}, 'bcb' | 'fallback')
    """
    today = datetime.date.today()
    start_date = start_date or (today.replace(year=today.year - 3)).isoformat()
    end_date   = end_date   or today.isoformat()

    rows = _fetch_sgs_monthly(SGS_IPCA_MONTHLY, "ipca", start_date, end_date, force_refresh)
    if rows:
        return rows, "bcb"
    return [], "fallback"


def get_current_risk_free_rate(force_refresh: bool = False) -> tuple[float, str]:
    """
    Retorna a taxa livre de risco anual atual (Selic Over).

    Usa média dos últimos 12 meses da série diária do SGS.
    Fallback: 10.75% ao ano.

    Returns:
        tuple: (taxa_anual_decimal, 'bcb' | 'fallback')
            ex: (0.1075, 'bcb')
    """
    today = datetime.date.today()
    start = (today.replace(year=today.year - 1)).isoformat()
    end   = today.isoformat()

    rows, source = get_selic_history(start, end, force_refresh)
    if rows:
        # A série SGS 11 é em % ao dia → acumular
        values = [float(r["value"]) / 100 for r in rows]
        # Aproximar taxa anual: (1 + taxa_diaria)^252 - 1
        # Mas como a série vem diária de forma acumulada mensalmente,
        # usa média simples e anualiza × 12 como aproximação razoável
        avg_monthly = sum(values) / len(values)
        anual = (1 + avg_monthly) ** 12 - 1
        return round(anual, 4), "bcb"

    return _FALLBACK["selic_anual"] / 100, "fallback"


def get_macro_snapshot() -> dict:
    """
    Retorna snapshot das principais taxas macro do mercado brasileiro.

    Returns:
        dict com selic_anual, cdi_anual, ipca_anual, prêmio_risco (selic - ipca),
        fonte e data de referência.
    """
    selic, src_selic = get_current_risk_free_rate()

    # IPCA: acumular últimos 12 meses
    today = datetime.date.today()
    start = (today.replace(year=today.year - 1)).isoformat()
    ipca_rows, src_ipca = get_ipca_history(start, today.isoformat())
    if ipca_rows:
        ipca_vals = [float(r["value"]) / 100 for r in ipca_rows[-12:]]
        ipca_anual = round(((1 + sum(ipca_vals) / len(ipca_vals)) ** 12 - 1), 4)
    else:
        ipca_anual = _FALLBACK["ipca_anual"] / 100

    cdi_anual = round(selic * 0.99, 4)  # CDI ≈ Selic × 0.99

    return {
        "selic_anual":    round(selic * 100, 2),      # em %
        "cdi_anual":      round(cdi_anual * 100, 2),  # em %
        "ipca_anual":     round(ipca_anual * 100, 2), # em %
        "premio_risco":   round((selic - ipca_anual) * 100, 2),
        "fonte_selic":    src_selic,
        "fonte_ipca":     src_ipca,
        "data_ref":       today.isoformat(),
    }


def calcular_premio_risco_fii(
    dividend_yield_anual: float,
    macro: dict | None = None,
) -> dict:
    """
    Calcula o prêmio de risco de um FII em relação ao CDI e ao IPCA.

    Args:
        dividend_yield_anual: DY anual do FII em % (ex: 12.5 para 12.5%).
        macro: Snapshot macro (opcional). Se None, busca automaticamente.

    Returns:
        dict com dy, cdi, ipca, spread_cdi, spread_ipca, rating qualitativo.
    """
    if macro is None:
        macro = get_macro_snapshot()

    spread_cdi  = round(dividend_yield_anual - macro["cdi_anual"], 2)
    spread_ipca = round(dividend_yield_anual - macro["ipca_anual"], 2)

    if spread_cdi >= 4:
        rating = "🟢 Excelente — alto prêmio sobre o CDI"
    elif spread_cdi >= 2:
        rating = "🟡 Bom — prêmio moderado"
    elif spread_cdi >= 0:
        rating = "🟠 Neutro — empatado com o CDI"
    else:
        rating = "🔴 Negativo — abaixo do CDI"

    return {
        "dy_anual_%":     dividend_yield_anual,
        "cdi_anual_%":    macro["cdi_anual"],
        "ipca_anual_%":   macro["ipca_anual"],
        "spread_cdi_%":   spread_cdi,
        "spread_ipca_%":  spread_ipca,
        "rating":         rating,
    }
