"""
Macro tools — Selic, CDI, IPCA do Banco Central do Brasil.
Reusa: core.macro_engine
"""

from typing import Any


def register_macro_tools(mcp: Any) -> None:

    @mcp.tool()
    def get_macro_snapshot() -> dict:
        """Retorna snapshot macroeconomico atual: Selic, CDI, IPCA.

        Dados obtidos via API do Banco Central do Brasil (SGS).
        Inclui metricas derivadas: juro real, spread FII vs Selic.

        Returns:
            dict com selic, cdi, ipca, juro_real, spread_fii_selic
        """
        from core.macro_engine import get_macro_snapshot as _get_macro

        data = _get_macro()

        # Enrich with derived metrics
        selic = data.get("selic", 0)
        ipca = data.get("ipca", 0)
        avg_fii_dy = 9.0  # Media historica de DY de FIIs

        juro_real = ((1 + selic / 100) / (1 + ipca / 100) - 1) * 100 if ipca else selic
        spread = avg_fii_dy - selic

        data["juro_real"] = round(juro_real, 2)
        data["spread_fii_vs_selic"] = round(spread, 2)
        data["atratividade_fiis"] = (
            "Alta" if spread > 0 else "Moderada" if spread > -2 else "Baixa"
        )

        return data

    @mcp.tool()
    def get_selic() -> dict:
        """Retorna a taxa Selic atual.

        Returns:
            dict com valor e fonte
        """
        from core.macro_engine import get_macro_snapshot as _get_macro

        data = _get_macro()
        return {
            "selic": data.get("selic", 0),
            "source": data.get("selic_source", "unknown"),
        }

    @mcp.tool()
    def get_ipca() -> dict:
        """Retorna o IPCA acumulado 12 meses.

        Returns:
            dict com valor e fonte
        """
        from core.macro_engine import get_macro_snapshot as _get_macro

        data = _get_macro()
        return {
            "ipca_12m": data.get("ipca", 0),
            "source": data.get("ipca_source", "unknown"),
        }
