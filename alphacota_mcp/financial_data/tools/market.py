"""
Market tools — preco, detalhe e scanner de FIIs.
Reusa: data.data_bridge, data.fundamentals_scraper, data.universe, core.quant_engine
"""

from typing import Any


def register_market_tools(mcp: Any) -> None:

    @mcp.tool()
    def get_fii_price(ticker: str) -> dict:
        """Retorna preco atual, DY e P/VP de um FII.

        Args:
            ticker: Codigo do FII (ex: HGLG11)

        Returns:
            dict com price, dy, pvp, dividend_monthly, source
        """
        from data.data_bridge import load_last_price, load_monthly_dividend
        from data.fundamentals_scraper import fetch_fundamentals

        ticker = ticker.replace(".SA", "").upper()
        fund = fetch_fundamentals(ticker)

        try:
            price, price_src = load_last_price(ticker)
        except Exception:
            price, price_src = 0, "unavailable"

        try:
            dividend, div_src = load_monthly_dividend(ticker)
        except Exception:
            dividend, div_src = 0, "unavailable"

        return {
            "ticker": ticker,
            "price": round(price, 2),
            "price_source": price_src,
            "dy_12m": round(fund.get("dividend_yield", 0) * 100, 2),
            "pvp": round(fund.get("pvp", 0), 2),
            "dividend_monthly": round(dividend, 4),
            "dividend_source": div_src,
            "liquidity": fund.get("daily_liquidity", 0),
            "data_source": fund.get("_source", "unknown"),
        }

    @mcp.tool()
    def get_fii_detail(ticker: str) -> dict:
        """Retorna dados completos de um FII: fundamentals, preco, score, setor.

        Args:
            ticker: Codigo do FII (ex: MXRF11)

        Returns:
            dict com todos os dados disponiveis do FII
        """
        from data.data_bridge import load_last_price, load_monthly_dividend
        from data.fundamentals_scraper import fetch_fundamentals
        from data.universe import get_sector_map
        from core.quant_engine import evaluate_company

        ticker = ticker.replace(".SA", "").upper()
        fund = fetch_fundamentals(ticker)
        sector_map = get_sector_map()

        try:
            price, _ = load_last_price(ticker)
        except Exception:
            price = 0

        try:
            dividend, _ = load_monthly_dividend(ticker)
        except Exception:
            dividend = 0

        eval_data = {
            "dividend_yield": fund.get("dividend_yield", 0.08),
            "pvp": fund.get("pvp", 1.0),
            "vacancia": fund.get("vacancia", 0.05),
            "liquidez_diaria": fund.get("liquidez_diaria", 5000000),
        }
        try:
            evaluation = evaluate_company(ticker, eval_data)
        except Exception:
            evaluation = {}

        return {
            "ticker": ticker,
            "segment": sector_map.get(ticker, "Outros"),
            "price": round(price, 2),
            "dividend_monthly": round(dividend, 4),
            "dy_12m": round(fund.get("dividend_yield", 0) * 100, 2),
            "pvp": round(fund.get("pvp", 0), 2),
            "vacancy_rate": round(fund.get("vacancy_rate", 0) * 100, 2),
            "liquidity": fund.get("daily_liquidity", 0),
            "net_asset_value": fund.get("net_asset_value", 0),
            "score": evaluation.get("score_final", 0),
            "evaluation": evaluation,
            "data_source": fund.get("_source", "unknown"),
        }

    @mcp.tool()
    def get_scanner(sectors: str = "") -> dict:
        """Lista todos os FIIs do universo com score quantitativo.

        Args:
            sectors: Filtro de setores separados por virgula (opcional).
                     Ex: "Logistica,Shopping" ou vazio para todos.

        Returns:
            dict com fiis (lista) e total
        """
        from data.universe import get_universe, get_sector_map
        from data.fundamentals_scraper import fetch_fundamentals_bulk
        from data.data_bridge import load_last_price
        from core.quant_engine import evaluate_company

        sector_filter = [s.strip() for s in sectors.split(",") if s.strip()] or None
        universe = get_universe(sectors=sector_filter)
        tickers = [f["ticker"] for f in universe]
        fundamentals = fetch_fundamentals_bulk(tickers)
        sector_map = get_sector_map()

        results = []
        for fii in universe:
            t = fii["ticker"]
            fund = fundamentals.get(t, {})
            eval_data = {
                "dividend_yield": fund.get("dividend_yield", 0.08),
                "pvp": fund.get("pvp", 1.0),
                "vacancia": fund.get("vacancia", 0.05),
                "liquidez_diaria": fund.get("liquidez_diaria", 5000000),
            }
            try:
                score = evaluate_company(t, eval_data).get("score_final", 0)
            except Exception:
                score = 0
            try:
                price, _ = load_last_price(t)
            except Exception:
                price = 0

            results.append({
                "ticker": t,
                "name": fii.get("nome", t),
                "segment": sector_map.get(t, "Outros"),
                "price": round(price, 2),
                "dy": round(fund.get("dividend_yield", 0.08) * 100, 2),
                "pvp": round(fund.get("pvp", 1.0), 2),
                "score": round(score, 0),
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return {"fiis": results, "total": len(results)}
