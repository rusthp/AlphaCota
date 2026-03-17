"""
Analysis tools — correlation, momentum, stress test, clustering.
Reusa: core.correlation_engine, core.momentum_engine, core.stress_engine, core.cluster_engine
"""

from typing import Any


def register_analysis_tools(mcp: Any) -> None:

    @mcp.tool()
    def run_correlation(tickers: list[str], start_date: str = "2023-01-01", end_date: str = "2025-12-31") -> dict:
        """Calcula matriz de correlacao entre FIIs.

        Mostra quais FIIs se movem juntos (correlacao alta) ou em direcoes
        opostas (correlacao negativa). Util para diversificacao.

        Args:
            tickers: Lista de tickers (ex: ["HGLG11", "MXRF11", "XPML11"])
            start_date: Data inicio (YYYY-MM-DD)
            end_date: Data fim (YYYY-MM-DD)

        Returns:
            dict com matrix de correlacao, tickers validos, e insights
        """
        from data.data_bridge import load_returns_bulk
        from core.correlation_engine import build_correlation_matrix

        return_series, sources = load_returns_bulk(tickers, start_date, end_date)
        valid = [t for t in tickers if len(return_series.get(t, [])) >= 3]

        if len(valid) < 2:
            return {"error": "Dados insuficientes. Necessario pelo menos 2 FIIs com dados."}

        matrix = build_correlation_matrix(valid, return_series)

        # Generate insights
        pairs = []
        for i, a in enumerate(valid):
            for j, b in enumerate(valid):
                if i < j:
                    val = matrix.get(a, {}).get(b, 0)
                    pairs.append({"a": a, "b": b, "correlation": round(val, 3)})

        pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)
        good_diversification = [p for p in pairs if p["correlation"] < 0.3]

        return {
            "tickers": valid,
            "matrix": matrix,
            "top_correlations": pairs[:5],
            "good_diversification_pairs": good_diversification[:5],
            "total_pairs": len(pairs),
        }

    @mcp.tool()
    def run_momentum(top_n: int = 10, start_date: str = "2024-01-01", end_date: str = "2025-12-31") -> dict:
        """Ranking de momentum dos FIIs — quais estao com melhor tendencia.

        Analisa retornos de 3, 6 e 12 meses para identificar FIIs
        com momentum positivo consistente.

        Args:
            top_n: Quantos FIIs retornar no ranking (default 10)
            start_date: Data inicio
            end_date: Data fim

        Returns:
            dict com ranking de momentum e total analisado
        """
        from data.universe import get_tickers
        from data.data_bridge import load_returns_bulk
        from core.momentum_engine import rank_by_momentum

        tickers = get_tickers()
        return_series, _ = load_returns_bulk(tickers, start_date, end_date)
        valid = {t: r for t, r in return_series.items() if len(r) >= 6}
        ranking = rank_by_momentum(valid)

        return {
            "ranking": ranking[:top_n],
            "total_analyzed": len(valid),
        }

    @mcp.tool()
    def run_stress(tickers: list[str], quantities: dict[str, int] | None = None) -> dict:
        """Executa cenarios de estresse na carteira.

        Simula cenarios adversos como: crash imobiliario, alta da Selic,
        aumento de vacancia, crise economica.

        Args:
            tickers: Lista de tickers da carteira
            quantities: Quantidade de cotas por ticker (opcional)

        Returns:
            dict com cenarios e impacto no patrimonio/dividendos
        """
        from data.data_bridge import build_portfolio_from_tickers
        from data.universe import get_sector_map
        from core.stress_engine import run_stress_suite

        portfolio = build_portfolio_from_tickers(tickers, quantities)
        sector_map = get_sector_map()
        results = run_stress_suite(portfolio, sector_map)

        return {"scenarios": results, "portfolio_size": len(tickers)}

    @mcp.tool()
    def run_clusters(start_date: str = "2024-01-01", end_date: str = "2025-12-31") -> dict:
        """Agrupa FIIs por comportamento via K-Means clustering.

        Identifica grupos de FIIs que se comportam de forma similar,
        util para diversificacao e entendimento do mercado.

        Args:
            start_date: Data inicio
            end_date: Data fim

        Returns:
            dict com clusters (grupos de tickers) e estatisticas
        """
        from data.universe import get_tickers
        from data.data_bridge import load_returns_bulk
        from core.cluster_engine import cluster_portfolio

        tickers = get_tickers()
        return_series, _ = load_returns_bulk(tickers, start_date, end_date)
        valid = {t: r for t, r in return_series.items() if len(r) >= 6}

        if len(valid) < 4:
            return {"error": "Dados insuficientes para clustering (minimo 4 FIIs)"}

        return cluster_portfolio(valid)
