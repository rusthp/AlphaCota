"""
Screening tools — filtros inteligentes para encontrar oportunidades em FIIs.
Reusa: data.universe, data.fundamentals_scraper, core.quant_engine
"""

from typing import Any


def register_screening_tools(mcp: Any) -> None:

    @mcp.tool()
    def find_undervalued_fiis(max_pvp: float = 0.95, min_dy: float = 8.0, limit: int = 10) -> dict:
        """Encontra FIIs subvalorizados (P/VP baixo + DY alto).

        Args:
            max_pvp: P/VP maximo (default 0.95 = desconto de 5% sobre patrimonio)
            min_dy: Dividend Yield minimo em % (default 8.0%)
            limit: Numero maximo de resultados

        Returns:
            dict com lista de FIIs filtrados e criterios usados
        """
        from data.universe import get_universe, get_sector_map
        from data.fundamentals_scraper import fetch_fundamentals_bulk

        universe = get_universe()
        tickers = [f["ticker"] for f in universe]
        fundamentals = fetch_fundamentals_bulk(tickers)
        sector_map = get_sector_map()

        matches = []
        for fii in universe:
            t = fii["ticker"]
            fund = fundamentals.get(t, {})
            dy = fund.get("dividend_yield", 0) * 100
            pvp = fund.get("pvp", 999)

            if pvp <= max_pvp and dy >= min_dy:
                matches.append({
                    "ticker": t,
                    "name": fii.get("nome", t),
                    "segment": sector_map.get(t, "Outros"),
                    "dy": round(dy, 2),
                    "pvp": round(pvp, 2),
                    "desconto": round((1 - pvp) * 100, 1),
                })

        matches.sort(key=lambda x: x["dy"], reverse=True)
        return {
            "fiis": matches[:limit],
            "total_found": len(matches),
            "criteria": {"max_pvp": max_pvp, "min_dy": min_dy},
        }

    @mcp.tool()
    def find_high_dividend_fiis(min_dy: float = 10.0, min_liquidity: float = 100000, limit: int = 10) -> dict:
        """Encontra FIIs com dividend yield elevado e boa liquidez.

        Args:
            min_dy: Dividend Yield minimo em % (default 10.0%)
            min_liquidity: Liquidez diaria minima em R$ (default 100k)
            limit: Numero maximo de resultados

        Returns:
            dict com lista de FIIs de alto dividendo
        """
        from data.universe import get_universe, get_sector_map
        from data.fundamentals_scraper import fetch_fundamentals_bulk

        universe = get_universe()
        tickers = [f["ticker"] for f in universe]
        fundamentals = fetch_fundamentals_bulk(tickers)
        sector_map = get_sector_map()

        matches = []
        for fii in universe:
            t = fii["ticker"]
            fund = fundamentals.get(t, {})
            dy = fund.get("dividend_yield", 0) * 100
            liq = fund.get("daily_liquidity", 0)

            if dy >= min_dy and liq >= min_liquidity:
                matches.append({
                    "ticker": t,
                    "name": fii.get("nome", t),
                    "segment": sector_map.get(t, "Outros"),
                    "dy": round(dy, 2),
                    "pvp": round(fund.get("pvp", 0), 2),
                    "liquidity": round(liq, 0),
                })

        matches.sort(key=lambda x: x["dy"], reverse=True)
        return {
            "fiis": matches[:limit],
            "total_found": len(matches),
            "criteria": {"min_dy": min_dy, "min_liquidity": min_liquidity},
        }

    @mcp.tool()
    def scan_opportunities(
        min_score: float = 75,
        max_pvp: float = 1.1,
        min_dy: float = 7.0,
        limit: int = 15,
    ) -> dict:
        """Scanner completo de oportunidades — combina score quant, P/VP e DY.

        Encontra FIIs que atendem todos os criterios simultaneamente.

        Args:
            min_score: Score quantitativo minimo (0-100, default 75)
            max_pvp: P/VP maximo (default 1.1)
            min_dy: DY minimo em % (default 7.0)
            limit: Numero maximo de resultados

        Returns:
            dict com oportunidades ranqueadas por score
        """
        from data.universe import get_universe, get_sector_map
        from data.fundamentals_scraper import fetch_fundamentals_bulk
        from core.quant_engine import evaluate_company

        universe = get_universe()
        tickers = [f["ticker"] for f in universe]
        fundamentals = fetch_fundamentals_bulk(tickers)
        sector_map = get_sector_map()

        opportunities = []
        for fii in universe:
            t = fii["ticker"]
            fund = fundamentals.get(t, {})
            dy = fund.get("dividend_yield", 0) * 100
            pvp = fund.get("pvp", 999)

            if dy < min_dy or pvp > max_pvp:
                continue

            eval_data = {
                "dividend_yield": fund.get("dividend_yield", 0.08),
                "pvp": fund.get("pvp", 1.0),
                "vacancia": fund.get("vacancia", 0.05),
                "liquidez_diaria": fund.get("liquidez_diaria", 5000000),
            }
            try:
                evaluation = evaluate_company(t, eval_data)
                score = evaluation.get("score_final", 0)
            except Exception:
                score = 0

            if score >= min_score:
                opportunities.append({
                    "ticker": t,
                    "name": fii.get("nome", t),
                    "segment": sector_map.get(t, "Outros"),
                    "score": round(score, 0),
                    "dy": round(dy, 2),
                    "pvp": round(pvp, 2),
                    "desconto": round((1 - pvp) * 100, 1) if pvp < 1 else 0,
                })

        opportunities.sort(key=lambda x: x["score"], reverse=True)
        return {
            "opportunities": opportunities[:limit],
            "total_found": len(opportunities),
            "criteria": {
                "min_score": min_score,
                "max_pvp": max_pvp,
                "min_dy": min_dy,
            },
        }
