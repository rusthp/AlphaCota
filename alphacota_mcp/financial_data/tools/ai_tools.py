"""
AI tools — analise de sentimento e relatorios via Groq/Llama + Vectorizer RAG.
Reusa: core.ai_engine, data.news_scraper, data.vectorizer_client
"""

from typing import Any


def register_ai_tools(mcp: Any) -> None:

    @mcp.tool()
    def analyze_fii_sentiment(ticker: str, api_key: str = "") -> dict:
        """Analisa sentimento de um FII usando IA (Groq/Llama3).

        Busca noticias recentes, consulta o Vectorizer para contexto
        semantico, e usa Llama3 via Groq para gerar analise de sentimento.

        Args:
            ticker: Codigo do FII (ex: HGLG11)
            api_key: Chave Groq API (opcional, usa env var GROQ_API_KEY se vazio)

        Returns:
            dict com analise de sentimento, noticias usadas, e raw response
        """
        from data.news_scraper import fetch_fii_news
        from core.ai_engine import analyze_fii_news

        ticker = ticker.replace(".SA", "").upper()
        news = fetch_fii_news(ticker, max_results=5)

        if not news:
            return {
                "success": False,
                "error": "Nenhuma noticia encontrada para " + ticker,
                "ticker": ticker,
            }

        key = api_key if api_key else None
        result = analyze_fii_news(ticker, news, api_key=key)
        result["news_count"] = len(news)
        result["news_sources"] = list({n.get("fonte", "unknown") for n in news})
        return result

    @mcp.tool()
    def generate_fii_report(ticker: str) -> dict:
        """Gera relatorio completo de um FII com dados + AI.

        Combina: preco atual, fundamentals, score quant, noticias,
        macro (Selic/CDI), e analise de sentimento em um unico relatorio.

        Args:
            ticker: Codigo do FII (ex: MXRF11)

        Returns:
            dict com relatorio completo estruturado
        """
        from data.data_bridge import load_last_price, load_monthly_dividend
        from data.fundamentals_scraper import fetch_fundamentals
        from data.universe import get_sector_map
        from data.news_scraper import fetch_fii_news
        from core.quant_engine import evaluate_company
        from core.macro_engine import get_macro_snapshot

        ticker = ticker.replace(".SA", "").upper()

        # Dados basicos
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

        # Score
        eval_data = {
            "dividend_yield": fund.get("dividend_yield", 0.08),
            "pvp": fund.get("pvp", 1.0),
            "vacancia": fund.get("vacancia", 0.05),
            "liquidez_diaria": fund.get("liquidez_diaria", 5000000),
        }
        try:
            evaluation = evaluate_company(ticker, eval_data)
            score = evaluation.get("score_final", 0)
        except Exception:
            evaluation = {}
            score = 0

        # Macro
        macro = get_macro_snapshot()
        selic = macro.get("selic", 0)

        # News
        news = fetch_fii_news(ticker, max_results=5)

        # DY
        dy = fund.get("dividend_yield", 0) * 100
        pvp = fund.get("pvp", 0)

        # Build report
        report = {
            "ticker": ticker,
            "segment": sector_map.get(ticker, "Outros"),
            "summary": {
                "price": round(price, 2),
                "dividend_monthly": round(dividend, 4),
                "dy_12m": round(dy, 2),
                "pvp": round(pvp, 2),
                "score": round(score, 0),
            },
            "fundamentals": {
                "dy_vs_selic": f"DY {dy:.1f}% vs Selic {selic:.1f}% = spread {dy - selic:+.1f}%",
                "pvp_status": "Desconto" if pvp < 1 else "Premio" if pvp > 1 else "Justo",
                "pvp_desconto": round((1 - pvp) * 100, 1) if pvp < 1 else 0,
            },
            "macro_context": {
                "selic": selic,
                "ipca": macro.get("ipca", 0),
                "atratividade": "Alta" if dy - selic > 0 else "Moderada" if dy - selic > -2 else "Baixa",
            },
            "news": news[:3],
            "evaluation": evaluation,
        }

        # Generate text verdict
        if score >= 85 and pvp < 1 and dy > selic:
            report["verdict"] = "FORTE COMPRA — Score alto, desconto e DY acima da Selic"
        elif score >= 75 and dy > selic:
            report["verdict"] = "COMPRA — Bom score e DY atrativo"
        elif score >= 60:
            report["verdict"] = "NEUTRO — Fundamentos adequados, sem grande destaque"
        else:
            report["verdict"] = "CAUTELA — Score baixo, avaliar riscos"

        return report

    @mcp.tool()
    def generate_daily_market_report() -> dict:
        """Gera relatorio diario do mercado de FIIs.

        Inclui: snapshot macro, top oportunidades, alertas de risco,
        noticias relevantes.

        Returns:
            dict com relatorio diario estruturado
        """
        from core.macro_engine import get_macro_snapshot
        from data.universe import get_universe, get_sector_map
        from data.fundamentals_scraper import fetch_fundamentals_bulk
        from data.news_scraper import fetch_market_news
        from core.quant_engine import evaluate_company

        # Macro
        macro = get_macro_snapshot()
        selic = macro.get("selic", 0)

        # Universe scan
        universe = get_universe()
        tickers = [f["ticker"] for f in universe]
        fundamentals = fetch_fundamentals_bulk(tickers)
        sector_map = get_sector_map()

        # Find top opportunities
        scored = []
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

            dy = fund.get("dividend_yield", 0) * 100
            pvp = fund.get("pvp", 999)

            scored.append({
                "ticker": t,
                "segment": sector_map.get(t, "Outros"),
                "score": round(score, 0),
                "dy": round(dy, 2),
                "pvp": round(pvp, 2),
            })

        scored.sort(key=lambda x: x["score"], reverse=True)

        # News
        news = fetch_market_news(max_results=10)

        # Stats
        avg_dy = sum(s["dy"] for s in scored) / len(scored) if scored else 0
        avg_pvp = sum(s["pvp"] for s in scored) / len(scored) if scored else 0
        undervalued = [s for s in scored if s["pvp"] < 0.95 and s["dy"] > selic]

        return {
            "date": "hoje",
            "macro": {
                "selic": selic,
                "ipca": macro.get("ipca", 0),
                "cdi": macro.get("cdi", 0),
            },
            "market_stats": {
                "total_fiis": len(scored),
                "avg_dy": round(avg_dy, 2),
                "avg_pvp": round(avg_pvp, 2),
                "undervalued_count": len(undervalued),
            },
            "top_opportunities": scored[:5],
            "undervalued": undervalued[:5],
            "news": news[:5],
        }
