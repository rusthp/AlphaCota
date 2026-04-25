"""
data/dividend_calendar.py
-------------------------
Coleta e retorna eventos de distribuição de dividendos dos FIIs.

Fontes:
- Histórico local: data/historical_dividends/<TICKER>_dividends.csv
- Estimativas: projeção baseada na média dos últimos 6 meses

Todos os eventos seguem o modelo DividendEvent (dict com campos tipados).
"""

from __future__ import annotations

import calendar
import datetime
from collections import Counter
from pathlib import Path
from typing import Any

from core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_HISTORICAL_DIVIDENDS_DIR = Path(__file__).parent / "historical_dividends"

# B3 standard: ex_date + 14 days ≈ pay_date
_EX_TO_PAY_DAYS = 14

# Type alias for clarity
DividendEvent = dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _get_sector_map() -> dict[str, str]:
    """Retorna mapa ticker → setor via universe.get_sector_map()."""
    try:
        from data.universe import get_sector_map

        return get_sector_map()
    except Exception:
        return {}


def _load_csv(ticker: str) -> "list[tuple[datetime.date, float]]":
    """
    Lê o CSV de dividendos históricos para um ticker.

    Returns:
        Lista de tuplas (date, valor_por_cota) ordenada por data.
        Retorna lista vazia se o arquivo não existir ou estiver corrompido.
    """
    try:
        import pandas as pd

        ticker_clean = ticker.removesuffix(".SA")
        csv_path = _HISTORICAL_DIVIDENDS_DIR / f"{ticker_clean}_dividends.csv"
        df = pd.read_csv(csv_path, parse_dates=["date"])

        if df.empty or "dividend" not in df.columns or "date" not in df.columns:
            return []

        df = df.dropna(subset=["date", "dividend"])
        df = df[df["dividend"] > 0]
        df = df.sort_values("date").reset_index(drop=True)

        return [(row["date"].date(), float(row["dividend"])) for _, row in df.iterrows()]

    except FileNotFoundError:
        logger.debug(f"CSV não encontrado para {ticker}")
        return []
    except Exception as e:
        logger.warning(f"Erro ao ler CSV de {ticker}: {e}")
        return []


def _make_event(
    ticker: str,
    ex_date: datetime.date,
    pay_date: datetime.date,
    valor: float,
    fonte: str,
    confirmado: bool,
    setor: str,
) -> DividendEvent:
    """Constrói um DividendEvent normalizado."""
    return {
        "ticker": ticker,
        "ex_date": ex_date.isoformat(),
        "pay_date": pay_date.isoformat(),
        "valor_por_cota": round(valor, 6),
        "tipo": "rendimento",
        "fonte": fonte,
        "confirmado": confirmado,
        "setor": setor,
    }


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def get_historical_events(ticker: str, months: int = 24) -> list[DividendEvent]:
    """
    Retorna eventos históricos de dividendos para um ticker.

    Lê o CSV local em data/historical_dividends/<TICKER>_dividends.csv.
    Cada linha vira um DividendEvent com pay_date = ex_date + 14 dias (padrão B3).
    Filtra apenas os últimos `months` meses.

    Args:
        ticker: Código do FII sem '.SA' (ex: 'MXRF11').
        months: Quantos meses de histórico retornar (padrão: 24).

    Returns:
        Lista de DividendEvent ordenada por ex_date (crescente).
    """
    ticker = ticker.replace(".SA", "").upper()
    sector_map = _get_sector_map()
    setor = sector_map.get(ticker, "Outros")

    rows = _load_csv(ticker)
    if not rows:
        return []

    cutoff = datetime.date.today() - datetime.timedelta(days=months * 30)
    events: list[DividendEvent] = []

    for ex_date, valor in rows:
        if ex_date < cutoff:
            continue
        pay_date = ex_date + datetime.timedelta(days=_EX_TO_PAY_DAYS)
        events.append(
            _make_event(
                ticker=ticker,
                ex_date=ex_date,
                pay_date=pay_date,
                valor=valor,
                fonte="historico",
                confirmado=True,
                setor=setor,
            )
        )

    return sorted(events, key=lambda e: e["ex_date"])


def estimate_next_events(ticker: str, months_ahead: int = 3) -> list[DividendEvent]:
    """
    Estima eventos futuros de dividendos com base no histórico recente.

    Calcula a média dos últimos 6 meses e o dia-do-mês mais frequente
    (moda do pay_date.day) para projetar `months_ahead` pagamentos futuros.

    Args:
        ticker: Código do FII sem '.SA' (ex: 'MXRF11').
        months_ahead: Quantos meses à frente projetar (padrão: 3).

    Returns:
        Lista de DividendEvent estimados, confirmado=False.
    """
    ticker = ticker.replace(".SA", "").upper()
    sector_map = _get_sector_map()
    setor = sector_map.get(ticker, "Outros")

    rows = _load_csv(ticker)
    if not rows:
        return []

    today = datetime.date.today()
    cutoff_6m = today - datetime.timedelta(days=6 * 30)

    recent_rows = [(d, v) for d, v in rows if d >= cutoff_6m]
    if not recent_rows:
        # Fall back to last 12 months if no data in past 6 months
        cutoff_12m = today - datetime.timedelta(days=12 * 30)
        recent_rows = [(d, v) for d, v in rows if d >= cutoff_12m]

    if not recent_rows:
        return []

    avg_valor = sum(v for _, v in recent_rows) / len(recent_rows)

    # Derive typical payment day from historical pay_dates (ex_date + 14)
    pay_days = [(d + datetime.timedelta(days=_EX_TO_PAY_DAYS)).day for d, _ in recent_rows]
    if pay_days:
        counter = Counter(pay_days)
        typical_pay_day = counter.most_common(1)[0][0]
    else:
        typical_pay_day = 15  # safe default

    events: list[DividendEvent] = []
    for i in range(1, months_ahead + 1):
        # Target month: today + i months
        target = today + datetime.timedelta(days=i * 30)
        year = target.year
        month = target.month

        # Clamp day to valid range for the month
        max_day = calendar.monthrange(year, month)[1]
        pay_day = min(typical_pay_day, max_day)
        pay_date = datetime.date(year, month, pay_day)
        ex_date = pay_date - datetime.timedelta(days=_EX_TO_PAY_DAYS)

        events.append(
            _make_event(
                ticker=ticker,
                ex_date=ex_date,
                pay_date=pay_date,
                valor=avg_valor,
                fonte="estimativa",
                confirmado=False,
                setor=setor,
            )
        )

    return sorted(events, key=lambda e: e["ex_date"])


def get_calendar_month(
    year: int,
    month: int,
    tickers: list[str],
) -> list[DividendEvent]:
    """
    Retorna todos os eventos (históricos + estimativas) para um mês específico.

    Para cada ticker, combina histórico real e eventos estimados, depois filtra
    pelo ano/mês solicitado. Eventos duplicados (mesma data real e estimada) são
    deduplicados mantendo o histórico (confirmado=True) como preferência.

    Args:
        year: Ano (ex: 2026).
        month: Mês 1–12 (ex: 3 para março).
        tickers: Lista de tickers a incluir.

    Returns:
        Lista de DividendEvent ordenada por pay_date.
    """
    all_events: list[DividendEvent] = []

    for ticker in tickers:
        historical = get_historical_events(ticker, months=36)
        estimates = estimate_next_events(ticker, months_ahead=6)

        # Combine, preferring confirmed historical over estimates
        seen_ex_dates: set[str] = set()
        for event in historical + estimates:
            key = f"{event['ticker']}:{event['ex_date']}"
            if key not in seen_ex_dates:
                seen_ex_dates.add(key)
                all_events.append(event)

    # Filter to the requested month using pay_date
    def _in_month(event: DividendEvent) -> bool:
        try:
            pay = datetime.date.fromisoformat(event["pay_date"])
            return pay.year == year and pay.month == month
        except (ValueError, KeyError):
            return False

    filtered = [e for e in all_events if _in_month(e)]
    return sorted(filtered, key=lambda e: e["pay_date"])


def get_calendar_year(
    year: int,
    tickers: list[str],
) -> dict[str, list[DividendEvent]]:
    """
    Retorna eventos agrupados por mês para um ano inteiro.

    Args:
        year: Ano (ex: 2026).
        tickers: Lista de tickers a incluir.

    Returns:
        dict mapeando "YYYY-MM" → lista de DividendEvent.
        Apenas meses com pelo menos um evento são incluídos.
    """
    result: dict[str, list[DividendEvent]] = {}

    for month in range(1, 13):
        month_key = f"{year}-{month:02d}"
        events = get_calendar_month(year, month, tickers)
        if events:
            result[month_key] = events

    return result


def get_portfolio_income(
    tickers_with_qty: dict[str, float],
    months_ahead: int = 12,
) -> list[dict[str, Any]]:
    """
    Projeta renda mensal de uma carteira de FIIs.

    Para cada ticker com quantidade de cotas, combina histórico e estimativas
    para os próximos `months_ahead` meses e multiplica o valor_por_cota pela
    quantidade, retornando a renda mensal agregada.

    Args:
        tickers_with_qty: Mapa ticker → quantidade de cotas (ex: {"MXRF11": 100}).
        months_ahead: Meses à frente a projetar (padrão: 12).

    Returns:
        Lista de dicts mensais com:
            - "month": "YYYY-MM"
            - "total_renda": float (R$ total projetado no mês)
            - "events": lista de DividendEvent com campo extra "renda_total"
    """
    tickers = list(tickers_with_qty.keys())
    today = datetime.date.today()

    # Build full event pool: historical (recent) + estimates
    all_events: list[DividendEvent] = []
    for ticker in tickers:
        historical = get_historical_events(ticker, months=6)  # last 6 for reference
        estimates = estimate_next_events(ticker, months_ahead=months_ahead)

        seen: set[str] = set()
        for event in historical + estimates:
            key = f"{event['ticker']}:{event['ex_date']}"
            if key not in seen:
                seen.add(key)
                all_events.append(event)

    # Group by pay_date month, filter to future months only
    monthly: dict[str, list[dict[str, Any]]] = {}

    for event in all_events:
        try:
            pay = datetime.date.fromisoformat(event["pay_date"])
        except (ValueError, KeyError):
            continue

        if pay <= today:
            continue

        # Only include up to months_ahead months ahead
        delta_months = (pay.year - today.year) * 12 + (pay.month - today.month)
        if delta_months < 1 or delta_months > months_ahead:
            continue

        month_key = f"{pay.year}-{pay.month:02d}"
        ticker = event["ticker"]
        qty = tickers_with_qty.get(ticker, 0.0)
        renda = round(event["valor_por_cota"] * qty, 2)

        enriched_event = {**event, "quantidade": qty, "renda_total": renda}

        if month_key not in monthly:
            monthly[month_key] = []
        monthly[month_key].append(enriched_event)

    # Build sorted output list
    output: list[dict[str, Any]] = []
    for month_key in sorted(monthly.keys()):
        events = monthly[month_key]
        total_renda = round(sum(e["renda_total"] for e in events), 2)
        output.append(
            {
                "month": month_key,
                "total_renda": total_renda,
                "events": sorted(events, key=lambda e: e["pay_date"]),
            }
        )

    return output
