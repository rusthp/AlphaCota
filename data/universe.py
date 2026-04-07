"""
data/universe.py

Universo dinâmico de FIIs brasileiros.

Mantém a lista dos principais FIIs negociados na B3, classificados por setor,
com metadados de liquidez mínima e status no IFIX.

Funções puras, sem dependências externas.
"""

# ---------------------------------------------------------------------------
# Classificação setorial oficial
# ---------------------------------------------------------------------------

SETORES = [
    "Papel (CRI)",
    "Logística",
    "Shopping",
    "Lajes Corp.",
    "Fundo de Fundos",
    "Híbrido",
    "Agro",
    "Saúde",
    "Residencial",
    "Hotel",
    "Educacional",
    "Outros",
]


# ---------------------------------------------------------------------------
# Universo de FIIs — dados base
# ---------------------------------------------------------------------------

# Cada entrada: ticker, setor, nome_curto, ifix (True se componente do IFIX)
_UNIVERSE_RAW: list[tuple[str, str, str, bool]] = [
    # ── Papel (CRI/CRA) ──
    ("MXRF11", "Papel (CRI)", "Maxi Renda", True),
    ("KNCR11", "Papel (CRI)", "Kinea Rendimentos", True),
    ("RECR11", "Papel (CRI)", "REC Recebíveis", True),
    ("MCCI11", "Papel (CRI)", "Mauá Capital", True),
    ("VRTA11", "Papel (CRI)", "Fator Veritá", True),
    ("HABT11", "Papel (CRI)", "Habitat II", True),
    ("RZAK11", "Papel (CRI)", "Riza Akin", True),
    ("VGIR11", "Papel (CRI)", "Valora RE", True),
    ("CPTS11", "Papel (CRI)", "Capitânia Securities", True),
    ("KNIP11", "Papel (CRI)", "Kinea Índices de Preços", True),
    ("RBRR11", "Papel (CRI)", "RBR Rendimento High Grade", True),
    # IRDM11 — delistado (sem dados yfinance desde 2026-03)
    # PLCR11 — delistado (sem dados de preço desde 2026-03)
    # CVBI11 — delistado (sem dados de preço desde 2026-03)
    # ── Logística ──
    ("HGLG11", "Logística", "CSHG Logística", True),
    ("XPLG11", "Logística", "XP Log", True),
    ("BTLG11", "Logística", "BTG Logístico", True),
    ("VILG11", "Logística", "Vinci Logística", True),
    ("BRCO11", "Logística", "Bresco Logística", True),
    # SDIL11 — delistado (sem dados de preço desde 2026-03)
    ("LVBI11", "Logística", "VBI Logístico", True),
    ("GARE11", "Logística", "Guardian RE", True),
    # ── Shopping ──
    ("XPML11", "Shopping", "XP Malls", True),
    # MALL11 — sem dados yfinance (no timezone found, 2026-03)
    ("VISC11", "Shopping", "Vinci Shopping Centers", True),
    ("HSML11", "Shopping", "HSI Malls", True),
    # ── Lajes Corporativas ──
    ("BRCR11", "Lajes Corp.", "BTG Corp. Office", True),
    ("JSRE11", "Lajes Corp.", "JS Real Estate", True),
    ("PVBI11", "Lajes Corp.", "VBI Prime Properties", True),
    ("HGRE11", "Lajes Corp.", "CSHG Real Estate", True),
    ("RCRB11", "Lajes Corp.", "Rio Bravo Renda Corp.", True),
    # ── Fundo de Fundos ──
    # BCFF11 — sem dados yfinance (no timezone found, 2026-03)
    ("HFOF11", "Fundo de Fundos", "Hedge TOP FOFII", True),
    # RBFF11 — delistado (sem dados yfinance desde 2026-03)
    # MGFF11 — sem dados yfinance (no timezone found, 2026-03)
    ("KFOF11", "Fundo de Fundos", "Kinea FoF", True),
    # ── Híbrido ──
    ("HGBS11", "Híbrido", "CSHG Brasil Shopping", True),
    ("KNRI11", "Híbrido", "Kinea Renda Imobiliária", True),
    ("RBRF11", "Híbrido", "RBR Alpha", True),
    ("TRXF11", "Híbrido", "TRX Real Estate", True),
    ("RBRP11", "Híbrido", "RBR Properties", True),
    # ── Agro ──
    ("RZTR11", "Agro", "Riza Terrax", True),
    # RURA11 — sem indicadores no StatusInvest (2026-03)
    # ── Saúde ──
    ("HCTR11", "Saúde", "Hectare CE", True),
    ("CARE11", "Saúde", "Brazilian Graveyard", False),
    # ── Residencial ──
    ("MFII11", "Residencial", "Mérito Desenvolvimento", True),
    ("TGAR11", "Residencial", "TG Ativo Real", True),
    # ── Educacional ──
    ("RECT11", "Educacional", "REC Renda Imobiliária", True),
]


# ---------------------------------------------------------------------------
# API Pública
# ---------------------------------------------------------------------------


def get_universe(
    ifix_only: bool = True,
    sectors: list[str] | None = None,
) -> list[dict]:
    """
    Retorna a lista de FIIs do universo.

    Args:
        ifix_only (bool): Se True, retorna apenas componentes do IFIX.
        sectors (list[str] | None): Filtrar por setores específicos.

    Returns:
        list[dict]: Lista de FIIs com ticker, setor, nome e status IFIX.
    """
    results = []
    for ticker, setor, nome, ifix in _UNIVERSE_RAW:
        if ifix_only and not ifix:
            continue
        if sectors and setor not in sectors:
            continue
        results.append(
            {
                "ticker": ticker,
                "setor": setor,
                "nome": nome,
                "ifix": ifix,
            }
        )
    return results


def get_tickers(
    ifix_only: bool = True,
    sectors: list[str] | None = None,
) -> list[str]:
    """
    Retorna apenas os tickers do universo filtrado.

    Args:
        ifix_only (bool): Se True, apenas componentes do IFIX.
        sectors (list[str] | None): Filtrar por setores específicos.

    Returns:
        list[str]: Lista de tickers.
    """
    return [fii["ticker"] for fii in get_universe(ifix_only, sectors)]


def get_sector_map() -> dict[str, str]:
    """
    Retorna mapeamento ticker → setor completo (todos os FIIs, não apenas IFIX).

    Returns:
        dict[str, str]: Mapa de ticker para setor.
    """
    return {ticker: setor for ticker, setor, _, _ in _UNIVERSE_RAW}


def get_sectors_summary(ifix_only: bool = True) -> dict[str, int]:
    """
    Retorna contagem de FIIs por setor.

    Returns:
        dict[str, int]: Mapa setor → quantidade de FIIs.
    """
    fiis = get_universe(ifix_only)
    summary: dict[str, int] = {}
    for fii in fiis:
        s = fii["setor"]
        summary[s] = summary.get(s, 0) + 1
    return summary


def get_universe_size(ifix_only: bool = True) -> int:
    """Retorna o número total de FIIs no universo."""
    return len(get_universe(ifix_only))
