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

            results.append(
                {
                    "ticker": t,
                    "name": fii.get("nome", t),
                    "segment": sector_map.get(t, "Outros"),
                    "price": round(price, 2),
                    "dy": round(fund.get("dividend_yield", 0.08) * 100, 2),
                    "pvp": round(fund.get("pvp", 1.0), 2),
                    "score": round(score, 0),
                }
            )

        results.sort(key=lambda x: x["score"], reverse=True)
        return {"fiis": results, "total": len(results)}

    @mcp.tool()
    def score_polymarket_market(condition_id: str) -> dict:
        """Score a Polymarket market by condition_id using the composite scoring engine.

        Fetches the market from Gamma API, runs the full scoring pipeline
        (edge, liquidity, time decay, copy signal, news sentiment), and returns
        the MarketScore as a serialisable dict.

        Args:
            condition_id: Polymarket condition ID.

        Returns:
            dict with total, edge, liquidity, time_decay, copy_signal,
            news_sentiment, fair_prob, and weights.
        """
        import httpx
        from core.polymarket_score import score_market

        try:
            resp = httpx.get(
                "https://gamma-api.polymarket.com/markets",
                params={"condition_id": condition_id},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})
        except Exception as exc:
            return {"error": f"Gamma API error: {exc}"}

        from core.polymarket_client import _parse_market
        market = _parse_market(raw)
        if market is None:
            return {"error": f"Could not parse market {condition_id}"}

        ms = score_market(market)
        return {
            "condition_id": ms.condition_id,
            "total": ms.total,
            "edge": ms.edge,
            "liquidity": ms.liquidity,
            "time_decay": ms.time_decay,
            "copy_signal": ms.copy_signal,
            "news_sentiment": ms.news_sentiment,
            "fair_prob": ms.fair_prob,
            "weights": ms.weights,
        }

    @mcp.tool()
    def get_polymarket_trade_decisions(limit: int = 5) -> dict:
        """Run the full Polymarket decision engine on the top discovered markets.

        Discovers markets, scores each, gates through risk rules, sizes positions,
        and returns a ranked list of approved TradeDecisions.

        Args:
            limit: Maximum number of decisions to return (default: 5).

        Returns:
            dict with decisions list and count.
        """
        from core.config import settings
        from core.polymarket_client import discover_markets, get_wallet_health
        from core.polymarket_decision_engine import generate_trade_decisions

        markets = discover_markets(limit=limit * 3)
        wallet_health = get_wallet_health()
        decisions = generate_trade_decisions(
            markets=markets,
            config=settings,
            wallet_health=wallet_health,
        )
        return {
            "decisions": [
                {
                    "condition_id": d.condition_id,
                    "token_id": d.token_id,
                    "direction": d.direction,
                    "size_usd": d.size_usd,
                    "score": d.score,
                    "kelly_fraction": d.kelly_fraction,
                    "reasoning": d.reasoning,
                }
                for d in decisions[:limit]
            ],
            "total": len(decisions),
        }

    @mcp.tool()
    def get_polymarket_alpha_wallets(limit: int = 10) -> dict:
        """Retorna ranking de carteiras alpha no Polymarket por taxa de acerto e recência.

        Lê endereços da variável de ambiente POLYMARKET_WATCH_WALLETS (separados por vírgula).
        Cada carteira é avaliada por win_rate, recência (decay exponencial 30 dias) e diversidade.

        Args:
            limit: Número máximo de carteiras a retornar (padrão: 10).

        Returns:
            dict com lista de wallets ranqueadas e seus scores.
        """
        from core.polymarket_alpha_detector import detect_top_alpha_wallets

        wallets = detect_top_alpha_wallets(limit=limit)
        return {
            "wallets": [
                {
                    "address": w.address,
                    "alpha_score": w.alpha_score,
                    "win_rate": round(w.win_rate * 100, 1),
                    "total_trades": w.total_trades,
                    "recency_weight": w.recency_weight,
                    "diversity_score": w.diversity_score,
                    "preferred_categories": w.preferred_categories,
                }
                for w in wallets
            ],
            "total": len(wallets),
        }
