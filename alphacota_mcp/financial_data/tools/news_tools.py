"""
News tools — noticias de FIIs via multiplas fontes RSS.
Reusa: data.news_scraper
"""

from typing import Any


def register_news_tools(mcp: Any) -> None:

    @mcp.tool()
    def get_fii_news(ticker: str, limit: int = 10) -> dict:
        """Busca noticias recentes de um FII via multiplas fontes RSS.

        Fontes: Google News, InfoMoney, Suno Research, FIIs.com.br,
        Valor Investe, Investing.com BR.

        Args:
            ticker: Codigo do FII (ex: HGLG11)
            limit: Numero maximo de noticias (default 10)

        Returns:
            dict com noticias (titulo, data, link, fonte)
        """
        from data.news_scraper import fetch_fii_news

        ticker = ticker.replace(".SA", "").upper()
        news = fetch_fii_news(ticker, max_results=limit)
        return {
            "ticker": ticker,
            "news": news,
            "count": len(news),
        }

    @mcp.tool()
    def get_market_news(limit: int = 20) -> dict:
        """Busca noticias gerais do mercado de FIIs (sem filtro de ticker).

        Agrega noticias de multiplas fontes sobre fundos imobiliarios,
        IFIX, dividendos e mercado imobiliario.

        Args:
            limit: Numero maximo de noticias (default 20)

        Returns:
            dict com noticias agregadas de multiplas fontes
        """
        from data.news_scraper import fetch_market_news

        news = fetch_market_news(max_results=limit)
        return {
            "news": news,
            "count": len(news),
        }

    @mcp.tool()
    def list_news_sources() -> dict:
        """Lista todas as fontes RSS configuradas no scraper de noticias.

        Returns:
            dict com fontes por tipo (ticker-specific e general)
        """
        from data.news_scraper import list_sources

        sources = list_sources()
        ticker_sources = [s for s in sources if s["type"] == "ticker"]
        general_sources = [s for s in sources if s["type"] == "general"]

        return {
            "ticker_sources": ticker_sources,
            "general_sources": general_sources,
            "total": len(sources),
        }
