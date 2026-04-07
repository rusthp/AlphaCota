"""
data/mercados_client.py

Wrapper da biblioteca `mercados` (PythonicCafe) para dados oficiais brasileiros:
- B3: carteira IFIX, dividendos, cotações
- CVM: informe diário de fundos
- FundosNet: documentos publicados por FIIs

Fonte: https://github.com/PythonicCafe/mercados
"""

import logging
from typing import Optional
import datetime

logger = logging.getLogger(__name__)

try:
    from mercados.b3 import B3
    from mercados.cvm import CVM
    from mercados.fundosnet import FundosNet

    HAS_MERCADOS = True
except ImportError:
    HAS_MERCADOS = False
    logger.warning("mercados não instalado. Execute: pip install mercados")


def get_ifix_composition() -> list[dict]:
    """
    Retorna a composição atual do IFIX via B3.

    Returns:
        Lista de dicts com ticker e peso na carteira.
    """
    if not HAS_MERCADOS:
        return []
    try:
        b3 = B3()
        carteira = b3.carteira_indice("IFIX")
        result = []
        for item in carteira:
            result.append(
                {
                    "ticker": str(item.get("ticker", item.get("codigo", ""))).upper().replace(".SA", ""),
                    "nome": item.get("nome", ""),
                    "peso": float(item.get("participacao", item.get("peso", 0)) or 0),
                    "tipo": item.get("tipo", "FII"),
                }
            )
        return result
    except Exception as e:
        logger.error("Erro ao buscar composição IFIX: %s", e)
        return []


def get_cvm_daily_report(date: Optional[datetime.date] = None) -> list[dict]:
    """
    Retorna o informe diário de fundos da CVM para uma data.

    Args:
        date: Data do informe (padrão: ontem).

    Returns:
        Lista de dicts com CNPJ, VPL, cotas, captação etc.
    """
    if not HAS_MERCADOS:
        return []
    try:
        if date is None:
            date = datetime.date.today() - datetime.timedelta(days=1)
        cvm = CVM()
        report = cvm.informe_diario_fundo(date)
        if report is None:
            return []
        # Normaliza para lista de dicts
        if hasattr(report, "to_dict"):
            return report.to_dict(orient="records")
        if isinstance(report, list):
            return report
        return []
    except Exception as e:
        logger.error("Erro ao buscar informe CVM %s: %s", date, e)
        return []


def get_fundosnet_documents(
    ticker: Optional[str] = None,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    items_per_page: int = 50,
) -> list[dict]:
    """
    Busca documentos publicados no FundosNet (CVM).

    Args:
        ticker: Filtrar por ticker do FII (opcional).
        start_date: Data inicial (padrão: 30 dias atrás).
        end_date: Data final (padrão: hoje).
        items_per_page: Quantidade máxima de resultados.

    Returns:
        Lista de dicts com metadados dos documentos.
    """
    if not HAS_MERCADOS:
        return []
    try:
        if end_date is None:
            end_date = datetime.date.today()
        if start_date is None:
            start_date = end_date - datetime.timedelta(days=30)

        fn = FundosNet()
        docs = fn.search(start_date=start_date, end_date=end_date, items_per_page=items_per_page)

        result = []
        for doc in docs:
            doc_ticker = str(doc.get("ticker", doc.get("codigo", ""))).upper().replace(".SA", "")
            if ticker and doc_ticker != ticker.upper().replace(".SA", ""):
                continue
            result.append(
                {
                    "ticker": doc_ticker,
                    "tipo": doc.get("categoria", doc.get("tipo", "")),
                    "data": str(doc.get("dataEntrega", doc.get("data", ""))),
                    "descricao": doc.get("descricao", ""),
                    "url": doc.get("url", ""),
                }
            )
        return result
    except Exception as e:
        logger.error("Erro ao buscar documentos FundosNet: %s", e)
        return []


def get_b3_dividends(
    ticker: str,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
) -> list[dict]:
    """
    Busca créditos de proventos (dividendos) via B3 Clearing.

    Args:
        ticker: Código do FII.
        start_date: Data inicial (padrão: 180 dias atrás).
        end_date: Data final (padrão: hoje).

    Returns:
        Lista de dicts com data e valor por cota.
    """
    if not HAS_MERCADOS:
        return []
    try:
        if end_date is None:
            end_date = datetime.date.today()
        if start_date is None:
            start_date = end_date - datetime.timedelta(days=180)

        b3 = B3()
        proventos = b3.clearing_creditos_de_proventos(
            data_inicial=start_date,
            filtro_emissor=ticker.upper().replace(".SA", ""),
        )

        result = []
        for p in proventos:
            data_str = str(p.get("dataPagamento", p.get("data", "")))
            valor = float(p.get("valorBruto", p.get("valor", 0)) or 0)
            if valor > 0:
                result.append({"date": data_str[:10], "value": round(valor, 6), "source": "b3"})

        return sorted(result, key=lambda x: x["date"])
    except Exception as e:
        logger.error("Erro ao buscar dividendos B3 para %s: %s", ticker, e)
        return []
