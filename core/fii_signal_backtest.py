"""
core/fii_signal_backtest.py — Signal-based backtesting of score thresholds.

Simulates a buy/sell strategy driven by alpha_score crossings and compares
returns against an IFIX benchmark over the same period.

Strategy rules:
    - Start with CASH (no position).
    - BUY:  score >= buy_threshold  AND  not holding shares.
    - SELL: score <  sell_threshold AND  holding shares.
    - Prices come from fii_daily_snapshot.price.
    - Benchmark: IFIX11.SA via yfinance (ETF proxy, not the index directly).

Run:
    python -m core.fii_signal_backtest --ticker HGLG11
    python -m core.fii_signal_backtest --all --days 180

Public API:
    backtest_ticker(conn, ticker, buy_threshold, sell_threshold, initial_capital, days)
    backtest_universe(conn, tickers, buy_threshold, sell_threshold, initial_capital, days)
    format_backtest_report(results) -> str
"""

from __future__ import annotations

import argparse
import datetime
import math
import sqlite3
import statistics
from dataclasses import dataclass, field

from core.logger import logger


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class SignalBacktestResult:
    ticker: str
    start_date: str
    end_date: str
    num_days: int
    initial_capital: float
    final_value: float
    total_return: float       # e.g. 0.15 = +15%
    cagr: float
    max_drawdown: float
    sharpe_ratio: float
    num_trades: int           # number of BUY entries
    win_rate: float           # fraction of closed trades with positive PnL
    buy_threshold: float
    sell_threshold: float
    ifix_return: float | None         # buy-and-hold IFIX11.SA over same period
    alpha_vs_ifix: float | None       # total_return - ifix_return
    trades: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# IFIX benchmark
# ---------------------------------------------------------------------------

def _fetch_ifix_prices(start_date: str, end_date: str) -> dict[str, float]:
    """Return {date_iso: close_price} for IFIX11.SA over the period."""
    try:
        import yfinance as yf
        hist = yf.Ticker("IFIX11.SA").history(
            start=start_date,
            end=end_date,
            auto_adjust=True,
        )
        if hist.empty:
            return {}
        result = {}
        for ts, row in hist.iterrows():
            d = ts.date().isoformat() if hasattr(ts, "date") else str(ts)[:10]
            result[d] = float(row["Close"])
        return result
    except Exception as exc:
        logger.warning("fii_signal_backtest: IFIX11.SA fetch failed: %s", exc)
        return {}


def _ifix_total_return(start_date: str, end_date: str) -> float | None:
    """Simple price return of IFIX11.SA from start to end date."""
    prices = _fetch_ifix_prices(start_date, end_date)
    if len(prices) < 2:
        return None
    dates = sorted(prices)
    p0, p1 = prices[dates[0]], prices[dates[-1]]
    return round((p1 / p0) - 1.0, 6) if p0 > 0 else None


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _cagr(initial: float, final: float, num_days: int) -> float:
    if initial <= 0 or final <= 0 or num_days <= 0:
        return 0.0
    years = num_days / 365.25
    return round((final / initial) ** (1.0 / years) - 1.0, 6)


def _max_drawdown(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (v - peak) / peak
            if dd < max_dd:
                max_dd = dd
    return round(max_dd, 6)


def _sharpe(daily_returns: list[float], annual_rf: float = 0.1075) -> float:
    if len(daily_returns) < 5:
        return 0.0
    daily_rf = (1 + annual_rf) ** (1 / 252) - 1
    excess = [r - daily_rf for r in daily_returns]
    mean_e = sum(excess) / len(excess)
    try:
        std_e = statistics.stdev(excess)
    except statistics.StatisticsError:
        return 0.0
    if std_e == 0:
        return 0.0
    return round(mean_e / std_e * math.sqrt(252), 4)


# ---------------------------------------------------------------------------
# Core simulation (pure function)
# ---------------------------------------------------------------------------

def _simulate(
    series: list[tuple[str, float, float]],  # (date, price, alpha_score) ASC
    buy_threshold: float,
    sell_threshold: float,
    initial_capital: float,
) -> dict:
    """Simulate buy/sell signal strategy on a time series.

    Returns dict with:
        portfolio_values  list[float]  — portfolio value at each snapshot
        trades            list[dict]   — buy/sell records
        final_cash        float
        final_shares      float
        open_buy_price    float | None — price of open position (not yet sold)
    """
    cash = initial_capital
    shares = 0.0
    open_buy_price: float | None = None
    portfolio_values: list[float] = []
    trades: list[dict] = []

    for date, price, score in series:
        if price <= 0:
            portfolio_values.append(cash + shares * price)
            continue

        # BUY signal: enter position
        if score >= buy_threshold and shares == 0 and cash > 0:
            shares = cash / price
            open_buy_price = price
            cash = 0.0
            trades.append({
                "type": "buy",
                "date": date,
                "price": price,
                "score": score,
                "shares": round(shares, 6),
            })

        # SELL signal: exit position
        elif score < sell_threshold and shares > 0:
            proceeds = shares * price
            pnl = proceeds - (open_buy_price or price) * shares
            ret = price / open_buy_price - 1.0 if open_buy_price and open_buy_price > 0 else 0.0
            trades.append({
                "type": "sell",
                "date": date,
                "price": price,
                "score": score,
                "shares": round(shares, 6),
                "pnl": round(pnl, 2),
                "return": round(ret, 4),
            })
            cash = proceeds
            shares = 0.0
            open_buy_price = None

        portfolio_values.append(cash + shares * price)

    return {
        "portfolio_values": portfolio_values,
        "trades": trades,
        "final_cash": cash,
        "final_shares": shares,
        "open_buy_price": open_buy_price,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def backtest_ticker(
    conn: sqlite3.Connection,
    ticker: str,
    buy_threshold: float = 80.0,
    sell_threshold: float = 45.0,
    initial_capital: float = 10_000.0,
    days: int = 365,
) -> SignalBacktestResult | None:
    """Backtest score-signal strategy for one ticker.

    Returns None when fewer than 10 price snapshots exist.
    """
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    try:
        rows = conn.execute(
            """
            SELECT date, price, alpha_score
              FROM fii_daily_snapshot
             WHERE ticker = ?
               AND date >= ?
               AND price > 0
             ORDER BY date ASC
            """,
            (ticker.upper(), cutoff),
        ).fetchall()
    except sqlite3.Error as exc:
        logger.warning("backtest_ticker(%s): %s", ticker, exc)
        return None

    if len(rows) < 10:
        logger.debug("backtest_ticker(%s): %d snapshots — insufficient", ticker, len(rows))
        return None

    series: list[tuple[str, float, float]] = [
        (r["date"], float(r["price"]), float(r["alpha_score"])) for r in rows
    ]
    start_date = series[0][0]
    end_date   = series[-1][0]
    num_days   = _days_between(start_date, end_date) or 1

    sim = _simulate(series, buy_threshold, sell_threshold, initial_capital)
    pv  = sim["portfolio_values"]

    # Mark open position at last price
    if sim["final_shares"] > 0:
        final_value = sim["final_cash"] + sim["final_shares"] * series[-1][1]
    else:
        final_value = sim["final_cash"]

    total_return = (final_value / initial_capital - 1.0) if initial_capital > 0 else 0.0

    # Daily returns for Sharpe
    daily_rets = []
    for i in range(1, len(pv)):
        if pv[i - 1] > 0:
            daily_rets.append(pv[i] / pv[i - 1] - 1.0)

    # Win rate from closed sell trades only
    closed_sells = [t for t in sim["trades"] if t["type"] == "sell"]
    win_rate = 0.0
    if closed_sells:
        winners = sum(1 for t in closed_sells if t.get("pnl", 0) > 0)
        win_rate = round(winners / len(closed_sells), 4)

    num_trades = sum(1 for t in sim["trades"] if t["type"] == "buy")
    ifix_ret   = _ifix_total_return(start_date, end_date)
    alpha      = round(total_return - ifix_ret, 6) if ifix_ret is not None else None

    return SignalBacktestResult(
        ticker=ticker.upper(),
        start_date=start_date,
        end_date=end_date,
        num_days=num_days,
        initial_capital=initial_capital,
        final_value=round(final_value, 2),
        total_return=round(total_return, 6),
        cagr=_cagr(initial_capital, final_value, num_days),
        max_drawdown=_max_drawdown(pv),
        sharpe_ratio=_sharpe(daily_rets),
        num_trades=num_trades,
        win_rate=win_rate,
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
        ifix_return=ifix_ret,
        alpha_vs_ifix=alpha,
        trades=sim["trades"],
    )


def backtest_universe(
    conn: sqlite3.Connection,
    tickers: list[str],
    buy_threshold: float = 80.0,
    sell_threshold: float = 45.0,
    initial_capital: float = 10_000.0,
    days: int = 365,
) -> list[SignalBacktestResult]:
    """Backtest all tickers and return results sorted by CAGR descending."""
    results = []
    for ticker in tickers:
        r = backtest_ticker(
            conn, ticker, buy_threshold, sell_threshold, initial_capital, days
        )
        if r is not None:
            results.append(r)
    results.sort(key=lambda x: x.cagr, reverse=True)
    return results


def format_backtest_report(results: list[SignalBacktestResult]) -> str:
    """Return a compact tabular text report of all backtest results."""
    if not results:
        return "Sem resultados (histórico insuficiente — mínimo 10 snapshots por ticker)."

    r0 = results[0]
    lines = [
        "=" * 65,
        "  ALPHACOTA — BACKTEST DE SINAIS DE SCORE",
        "=" * 65,
        f"  Período : {r0.start_date} → {r0.end_date}  ({r0.num_days}d)",
        f"  Capital : R$ {r0.initial_capital:,.2f}",
        f"  Entrada : score ≥ {r0.buy_threshold:.0f}  |  Saída: score < {r0.sell_threshold:.0f}",
        "-" * 65,
        f"  {'Ticker':<8} {'CAGR':>7} {'Retorno':>8} {'Sharpe':>7} "
        f"{'MaxDD':>7} {'Ops':>4} {'Win%':>6} {'α IFIX':>8}",
        "-" * 65,
    ]
    for r in results:
        alpha_str = f"{r.alpha_vs_ifix * 100:+.1f}%" if r.alpha_vs_ifix is not None else "     —"
        lines.append(
            f"  {r.ticker:<8} {r.cagr * 100:>6.1f}% "
            f"{r.total_return * 100:>7.1f}% "
            f"{r.sharpe_ratio:>7.2f} "
            f"{r.max_drawdown * 100:>6.1f}% "
            f"{r.num_trades:>4} "
            f"{r.win_rate * 100:>5.0f}% "
            f"{alpha_str:>8}"
        )
    if results[0].ifix_return is not None:
        lines.append(
            f"  {'IFIX11.SA':<8} {'':>7} "
            f"{results[0].ifix_return * 100:>7.1f}%  (benchmark)"
        )
    lines.append("=" * 65)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _days_between(d1: str, d2: str) -> int:
    a = datetime.date.fromisoformat(d1)
    b = datetime.date.fromisoformat(d2)
    return abs((b - a).days)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="AlphaCota FII signal backtest")
    parser.add_argument("--ticker", help="Ticker to backtest (e.g. HGLG11)")
    parser.add_argument("--days", type=int, default=365, help="Look-back days (default 365)")
    parser.add_argument("--buy",  type=float, default=80.0, help="Buy threshold (default 80)")
    parser.add_argument("--sell", type=float, default=45.0, help="Sell threshold (default 45)")
    parser.add_argument("--capital", type=float, default=10_000.0, help="Initial capital R$ (default 10000)")
    parser.add_argument("--all", action="store_true", help="Backtest entire IFIX universe")
    parser.add_argument("--trades", action="store_true", help="Print individual trades")
    args = parser.parse_args()

    from core.fii_ledger import connect_fii_db

    conn = connect_fii_db()

    if args.ticker:
        r = backtest_ticker(conn, args.ticker.upper(), args.buy, args.sell, args.capital, args.days)
        if r is None:
            print(f"Histórico insuficiente para {args.ticker.upper()} (< 10 snapshots).")
        else:
            print(format_backtest_report([r]))
            if args.trades and r.trades:
                print(f"\n  Operações ({len(r.trades)}):")
                for t in r.trades:
                    pnl = f"  PnL: R$ {t.get('pnl', 0):.2f}" if t["type"] == "sell" else ""
                    print(
                        f"    {t['type'].upper():4} {t['date']}  "
                        f"R$ {t['price']:.2f}  score={t['score']:.1f}{pnl}"
                    )

    elif args.all:
        from data.universe import get_universe
        universe = get_universe(ifix_only=True)
        tickers = [f["ticker"] for f in universe]
        print(f"Backtesting {len(tickers)} FIIs…")
        results = backtest_universe(
            conn, tickers, args.buy, args.sell, args.capital, args.days
        )
        print(format_backtest_report(results))
        if not results:
            print("Nenhum ticker com histórico suficiente. Execute o fii_loop por mais alguns dias.")

    else:
        parser.print_help()

    conn.close()


if __name__ == "__main__":
    main()
