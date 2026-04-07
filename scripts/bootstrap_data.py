"""
scripts/bootstrap_data.py

Script de bootstrap: baixa e cacheia dados históricos dos principais FIIs
usados no universo padrão do AlphaCota.

Execute uma vez antes de usar o backtest engine:
    python scripts/bootstrap_data.py

Os dados são salvos em:
    data/historical_prices/<TICKER>_prices.csv
    data/historical_dividends/<TICKER>_dividends.csv
"""

import sys
import os

# Projeto raiz no path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.data_loader import fetch_prices, fetch_dividends, PRICES_DIR, DIVIDENDS_DIR

# ---------------------------------------------------------------------------
# Universo padrão de FIIs e benchmark
# ---------------------------------------------------------------------------

FII_UNIVERSE = [
    # FIIs de Papel (CRI)
    "MXRF11",
    "KNCR11",
    "RECR11",
    "MCCI11",
    "VRTA11",
    # FIIs de Tijolo — Logística
    "HGLG11",
    "XPLG11",
    "BRCO11",
    "BTLG11",
    # FIIs de Tijolo — Shoppings
    "XPML11",
    "MALL11",
    "VISC11",
    # FIIs de Tijolo — Lajes Corporativas
    "BRCR11",
    "JSRE11",
    # FIIs Híbridos / Diversificados
    "BCFF11",
    "RBRF11",
    # Fundos de Desenvolvimento
    "HFOF11",
]

BENCHMARK = "^BVSP"  # IBOVESPA como proxy até IFIX estar disponível no yfinance
START_DATE = "2020-01-01"
END_DATE = "2025-12-31"


def bootstrap(
    tickers: list[str],
    start: str,
    end: str,
    force_refresh: bool = False,
) -> None:
    """
    Baixa e cacheia preços e dividendos para uma lista de tickers.

    Args:
        tickers (list[str]): Lista de tickers para processar.
        start (str): Data inicial 'YYYY-MM-DD'.
        end (str): Data final 'YYYY-MM-DD'.
        force_refresh (bool): Forçar novo download mesmo com cache existente.
    """
    print(f"\n{'='*55}")
    print(f"  AlphaCota — Bootstrap de Dados Históricos")
    print(f"{'='*55}")
    print(f"  Período : {start} → {end}")
    print(f"  Tickers : {len(tickers)}")
    print(f"  Cache   : {PRICES_DIR}")
    print(f"{'='*55}\n")

    ok = []
    failed = []

    for ticker in tickers:
        try:
            prices = fetch_prices(ticker, start, end, force_refresh=force_refresh)
            divs = fetch_dividends(ticker, start, end, force_refresh=force_refresh)
            label = f"{ticker:<10} → {len(prices):>3} meses de preços, {len(divs):>3} proventos"
            print(f"  ✅ {label}")
            ok.append(ticker)
        except Exception as e:
            print(f"  ❌ {ticker:<10} → {e}")
            failed.append(ticker)

    print(f"\n{'='*55}")
    print(f"  Concluído: {len(ok)} OK, {len(failed)} falhas")
    if failed:
        print(f"  Falhas   : {', '.join(failed)}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AlphaCota — Bootstrap de Dados Históricos")
    parser.add_argument("--tickers", nargs="*", help="Tickers específicos (padrão: universo completo)", default=None)
    parser.add_argument("--start", default=START_DATE, help=f"Data inicial (padrão: {START_DATE})")
    parser.add_argument("--end", default=END_DATE, help=f"Data final   (padrão: {END_DATE})")
    parser.add_argument("--force", action="store_true", help="Forçar re-download ignorando cache")
    parser.add_argument("--benchmark", action="store_true", help="Incluir benchmark (IBOVESPA)")
    args = parser.parse_args()

    targets = args.tickers if args.tickers else FII_UNIVERSE.copy()
    if args.benchmark:
        targets.append(BENCHMARK)

    bootstrap(targets, args.start, args.end, force_refresh=args.force)
