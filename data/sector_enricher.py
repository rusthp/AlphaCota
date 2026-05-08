"""
data/sector_enricher.py — Sector classification enrichment for the FII registry.

Sources (in priority order):
  1. StatusInvest JSON-LD InvestmentFund.category  (reliable, single ticker)
  2. Extended _KNOWN_SECTORS map               (covers all B3 IFIX FIIs as of 2026-05)
  3. Keyword heuristic on fund name/ticker     (fallback)

Public API:
    enrich_registry_sectors(conn, force=False) -> int
        Update fii_registry rows where setor='Outros' (or force=True for all).
        Returns number of rows updated.

    classify_sector(ticker, nome) -> str
        Classify a single FII without touching the DB.
"""

from __future__ import annotations

import json
import sqlite3
import time

from core.logger import logger

# ---------------------------------------------------------------------------
# StatusInvest → AlphaCota taxonomy map
# ---------------------------------------------------------------------------

_SI_TO_SECTOR: dict[str, str] = {
    # JSON-LD InvestmentFund.category values observed on StatusInvest
    "Papéis":                  "Papel (CRI)",
    "Papeis":                  "Papel (CRI)",
    "Papel":                   "Papel (CRI)",
    "Recebíveis":              "Papel (CRI)",
    "Recebiveis":              "Papel (CRI)",
    "Logístico":               "Logística",
    "Logistico":               "Logística",
    "Logística":               "Logística",
    "Logistica":               "Logística",
    "Shoppings":               "Shopping",
    "Shopping":                "Shopping",
    "Lajes Corporativas":      "Lajes Corp.",
    "Lajes":                   "Lajes Corp.",
    "Corporativo":             "Lajes Corp.",
    "Fundo de Fundos":         "Fundo de Fundos",
    "FoF":                     "Fundo de Fundos",
    "Híbrido":                 "Híbrido",
    "Hibrido":                 "Híbrido",
    "Agronegócio":             "Agro",
    "Agronegocio":             "Agro",
    "Agro":                    "Agro",
    "Saúde":                   "Saúde",
    "Saude":                   "Saúde",
    "Residencial":             "Residencial",
    "Hotel":                   "Hotel",
    "Hoteleiro":               "Hotel",
    "Educacional":             "Educacional",
    "Desenvolvimento":         "Residencial",
}

# ---------------------------------------------------------------------------
# Extended known-sector map — covers all B3 IFIX FIIs as of 2026-05-08.
# This map is updated whenever a new batch of FIIs enters the IFIX.
# ---------------------------------------------------------------------------

KNOWN_SECTORS: dict[str, str] = {
    # ── Papel (CRI) ──
    "MXRF11": "Papel (CRI)", "KNCR11": "Papel (CRI)", "RECR11": "Papel (CRI)",
    "MCCI11": "Papel (CRI)", "VRTA11": "Papel (CRI)", "HABT11": "Papel (CRI)",
    "RZAK11": "Papel (CRI)", "VGIR11": "Papel (CRI)", "CPTS11": "Papel (CRI)",
    "KNIP11": "Papel (CRI)", "RBRR11": "Papel (CRI)", "IRDM11": "Papel (CRI)",
    "PLCR11": "Papel (CRI)", "CVBI11": "Papel (CRI)", "BCRI11": "Papel (CRI)",
    "RBHY11": "Papel (CRI)", "GCRI11": "Papel (CRI)", "URPR11": "Papel (CRI)",
    "REIT11": "Papel (CRI)", "VSLH11": "Papel (CRI)", "HGCR11": "Papel (CRI)",
    "DEVA11": "Papel (CRI)", "BPFF11": "Papel (CRI)", "VCJR11": "Papel (CRI)",
    "OUJP11": "Papel (CRI)", "TPFT11": "Papel (CRI)", "NCHB11": "Papel (CRI)",
    # Confirmed from SI JSON-LD
    "CACR11": "Papel (CRI)",   # CARTESIA RECEBÍVEIS — "Papéis"
    "ICRI11": "Papel (CRI)",   # CI ÍNDICE DE PREÇOS — CRI
    "IRIM11": "Papel (CRI)",   # IRIDIUM RECEBÍVEIS
    "ITRI11": "Papel (CRI)",   # ITAÚ RI
    "JSAF11": "Papel (CRI)",   # JS ATIVOS FINANCEIROS
    "KCRE11": "Papel (CRI)",   # KINEA CRÉDITO IMOBILIÁRIO
    "KIVO11": "Papel (CRI)",   # KIVO (receivables)
    "KNHF11": "Papel (CRI)",   # KINEA HIGH GRADE
    "KNHY11": "Papel (CRI)",   # KINEA HIGH YIELD CRI
    "MCRE11": "Papel (CRI)",   # MAUÁ CRÉDITO REAL ESTATE
    "PCIP11": "Papel (CRI)",   # PCIP PAX — CRI
    "PSEC11": "Papel (CRI)",   # PSEC PAX — securities CRI
    "RBRY11": "Papel (CRI)",   # RBR HIGH YIELD
    "SPXS11": "Papel (CRI)",   # SPX SYNAPSE
    "TVRI11": "Papel (CRI)",   # TIVIO RI — CRI
    "VGHF11": "Papel (CRI)",   # VALOR HIGH GRADE
    "VGRI11": "Papel (CRI)",   # VALORA GRI — CRI
    "VRTM11": "Papel (CRI)",   # VRTM — receivables
    "CLIN11": "Papel (CRI)",   # CLAVE IN — CRI
    "AZPL11": "Papel (CRI)",   # AZPL — CRI
    "BTHF11": "Papel (CRI)",   # BTH FINANCIAL — CRI
    "FATN11": "Papel (CRI)",   # ATHENA I — CRI
    # ── Logística ──
    "HGLG11": "Logística", "XPLG11": "Logística", "BTLG11": "Logística",
    "VILG11": "Logística", "BRCO11": "Logística", "SDIL11": "Logística",
    "LVBI11": "Logística", "GARE11": "Logística", "BLMR11": "Logística",
    "LGCP11": "Logística", "EURO11": "Logística", "VVPR11": "Logística",
    "BRPL11": "Logística", "PATL11": "Logística", "JRDM11": "Logística",
    # Confirmed / extended
    "BBIG11": "Logística",   # BB INDUSTRIAL GALPÃO
    "HSLG11": "Logística",   # HSI LOGÍSTICA
    "KISU11": "Logística",   # KILIMA (industrial park)
    "KORE11": "Logística",   # KORE INDUSTRIAL
    "MANA11": "Logística",   # MANATÍ LOGÍSTICA
    "RBFM11": "Logística",   # RIO BRAVO MULTI-TENANT
    "RBRL11": "Logística",   # RBR LOGÍSTICA
    "RZAT11": "Logística",   # ARCTIUM (industrial real estate)
    "TRBL11": "Logística",   # SDI LOGÍSTICA (FII SDI LOG)
    "XPIN11": "Logística",   # XP INDUSTRIAL
    "SNEL11": "Logística",   # SUNO ENERGIA LOGÍSTICA
    # ── Shopping ──
    "XPML11": "Shopping", "MALL11": "Shopping", "VISC11": "Shopping",
    "HSML11": "Shopping", "ALMI11": "Shopping", "FIGS11": "Shopping",
    "GSFI11": "Shopping", "ABCP11": "Shopping", "PQDP11": "Shopping",
    # Confirmed / extended
    "BPML11": "Shopping",   # BTG PACTUAL MALLS
    "CPSH11": "Shopping",   # CP SHOPPING
    "GZIT11": "Shopping",   # GAZIT MALLS
    "KNSC11": "Shopping",   # KINEA SHOPPING CENTERS
    "PMLL11": "Shopping",   # PAX MALLS
    "RBVA11": "Shopping",   # RIO BRAVO VAREJO (retail)
    "TOPP11": "Shopping",   # TOPP PAX (premium malls)
    # ── Lajes Corporativas ──
    "BRCR11": "Lajes Corp.", "JSRE11": "Lajes Corp.", "PVBI11": "Lajes Corp.",
    "HGRE11": "Lajes Corp.", "RCRB11": "Lajes Corp.", "BMLC11": "Lajes Corp.",
    "GGRC11": "Lajes Corp.", "TEPP11": "Lajes Corp.", "VINO11": "Lajes Corp.",
    "FVPQ11": "Lajes Corp.", "GTWR11": "Lajes Corp.", "CPFF11": "Lajes Corp.",
    "LIFE11": "Lajes Corp.",
    # Confirmed / extended
    "BROF11": "Lajes Corp.",   # BRESCO OFFICES
    "RPRI11": "Lajes Corp.",   # RBR PRIME REALTY
    "SPXS11": "Lajes Corp.",   # re-check: SPX SYN may be offices
    # ── Fundo de Fundos ──
    "BCFF11": "Fundo de Fundos", "HFOF11": "Fundo de Fundos", "RBFF11": "Fundo de Fundos",
    "MGFF11": "Fundo de Fundos", "KFOF11": "Fundo de Fundos", "BCIA11": "Fundo de Fundos",
    "IBFF11": "Fundo de Fundos", "MORE11": "Fundo de Fundos",
    # Extended
    "SNFF11": "Fundo de Fundos",  # SUNO FOF IMOBILIÁRIO
    "XPSF11": "Fundo de Fundos",  # XP SELEÇÃO (FoF)
    # ── Híbrido ──
    "HGBS11": "Híbrido", "KNRI11": "Híbrido", "RBRF11": "Híbrido",
    "TRXF11": "Híbrido", "RBRP11": "Híbrido", "XPCI11": "Híbrido",
    "QAGR11": "Híbrido",
    # Extended
    "CYCR11": "Residencial",   # CYRELA RENDA IMOBILIÁRIA → Residencial
    "HGRU11": "Híbrido",       # CSHG RENDA URBANA (retail + office mix)
    "KNUQ11": "Híbrido",       # KINEA UNIQUE (multi-asset)
    "RBRX11": "Híbrido",       # RBR X (multi-strategy)
    "WHGR11": "Híbrido",       # WHG REAL ESTATE
    # ── Agro ──
    "RZTR11": "Agro", "RURA11": "Agro", "JURO11": "Agro", "VGIP11": "Agro",
    "PEMA11": "Agro",
    # ── Saúde ──
    "HCTR11": "Saúde", "CARE11": "Saúde", "HSAF11": "Saúde",
    # ── Residencial ──
    "MFII11": "Residencial", "TGAR11": "Residencial", "ALZR11": "Residencial",
    "RBTS11": "Residencial", "URBA11": "Residencial",
    # ── Educacional ──
    "RECT11": "Educacional", "RBED11": "Educacional",
    # ── Hotel ──
    "HGHO11": "Hotel", "HTMX11": "Hotel",
}

# ---------------------------------------------------------------------------
# StatusInvest per-ticker sector scraper (JSON-LD source)
# ---------------------------------------------------------------------------

_SI_BASE = "https://statusinvest.com.br/fundos-imobiliarios/{ticker}"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def _scrape_si_sector(ticker: str) -> str | None:
    """Extract sector from StatusInvest JSON-LD InvestmentFund.category.

    Returns AlphaCota sector string or None if not found / request failed.
    Rate-limit: caller must sleep between calls.
    """
    try:
        import requests
        from bs4 import BeautifulSoup

        url = _SI_BASE.format(ticker=ticker.lower())
        r = requests.get(
            url,
            headers={"User-Agent": _UA, "Accept-Language": "pt-BR,pt;q=0.9"},
            timeout=10,
        )
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                d = json.loads(script.string or "")
                if d.get("@type") == "InvestmentFund":
                    category = d.get("category", "")
                    if category:
                        return _SI_TO_SECTOR.get(category, None)
            except (json.JSONDecodeError, AttributeError):
                pass

        return None
    except Exception as exc:
        logger.debug("_scrape_si_sector(%s): %s", ticker, exc)
        return None


# ---------------------------------------------------------------------------
# Public: classify a single FII (no DB)
# ---------------------------------------------------------------------------

def classify_sector(ticker: str, nome: str) -> str:
    """Classify sector via known map → keyword heuristic → 'Outros'.

    This is a pure function — does not fetch from SI (too slow for bulk use).
    Use enrich_registry_sectors() to apply SI scraping for unknowns.
    """
    ticker_u = ticker.upper()
    if ticker_u in KNOWN_SECTORS:
        return KNOWN_SECTORS[ticker_u]

    nome_u = nome.upper()

    # Ordered from most-specific to least
    if any(k in nome_u for k in ["CRI", "CREDITO IMOB", "RECEBIV", "SECURIT",
                                   "PAPEL", "HIGH GRADE", "HIGH YIELD", "RENDIMENTO"]):
        return "Papel (CRI)"
    if "FUNDO DE FUNDO" in nome_u or "FOF" in ticker_u or "FOF" in nome_u:
        return "Fundo de Fundos"
    if any(k in nome_u for k in ["LOGIST", "ARMAZEN", "GALP", "INDUSTRIAL",
                                   "INDL", "GARE", "LOG "]):
        return "Logística"
    if any(k in nome_u for k in ["SHOPPING", "MALL", "SHOP ", "VAREJO", "MALLS"]):
        return "Shopping"
    if any(k in nome_u for k in ["CORPORATIV", "ESCRITOR", "LAJE", "OFFICE",
                                   "OFFICES", "CORP "]):
        return "Lajes Corp."
    if any(k in nome_u for k in ["AGRO", "RURAL", "TERRA", "FAZENDA",
                                   "AGRONEGOC"]):
        return "Agro"
    if any(k in nome_u for k in ["SAUDE", "HOSPITAL", "MEDIC", "CLINICA", "SAÚDE"]):
        return "Saúde"
    if any(k in nome_u for k in ["RESID", "APART", "HABIT", "HABITAC", "CYRELA"]):
        return "Residencial"
    if "HOTEL" in nome_u or "HOTELEIRO" in nome_u:
        return "Hotel"
    if any(k in nome_u for k in ["EDUCA", "ESCOLA", "UNIVERS"]):
        return "Educacional"
    if any(k in nome_u for k in ["HÍBRIDO", "HIBRIDO", "MULTI", "RENDA URBA"]):
        return "Híbrido"

    return "Outros"


# ---------------------------------------------------------------------------
# Bulk registry enrichment
# ---------------------------------------------------------------------------

def enrich_registry_sectors(
    conn: sqlite3.Connection,
    force: bool = False,
    use_si: bool = True,
) -> int:
    """Update sectors for FIIs in the registry.

    For each FII with setor='Outros' (or all if force=True):
      1. Check KNOWN_SECTORS map
      2. Apply keyword heuristic on nome
      3. Optionally scrape StatusInvest JSON-LD for remaining unknowns

    Args:
        conn:    Open registry connection.
        force:   Re-classify all FIIs, not just 'Outros'.
        use_si:  Scrape StatusInvest for FIIs still 'Outros' after heuristic.

    Returns:
        Number of registry rows updated.
    """
    if force:
        rows = conn.execute("SELECT ticker, nome FROM fii_registry WHERE ativo = 1").fetchall()
    else:
        rows = conn.execute(
            "SELECT ticker, nome FROM fii_registry WHERE setor = 'Outros' AND ativo = 1"
        ).fetchall()

    updated = 0
    still_unknown: list[str] = []

    for row in rows:
        ticker = row["ticker"]
        nome = row["nome"]

        setor = classify_sector(ticker, nome)
        if setor != "Outros":
            conn.execute(
                "UPDATE fii_registry SET setor = ?, updated_at = ? WHERE ticker = ?",
                (setor, time.time(), ticker),
            )
            updated += 1
            logger.debug("sector enricher: %s → %s (map/heuristic)", ticker, setor)
        else:
            still_unknown.append(ticker)

    conn.commit()

    # StatusInvest scraping for remaining unknowns
    if use_si and still_unknown:
        logger.info(
            "sector enricher: %d FIIs still 'Outros' — scraping StatusInvest",
            len(still_unknown),
        )
        for ticker in still_unknown:
            setor = _scrape_si_sector(ticker)
            if setor and setor != "Outros":
                conn.execute(
                    "UPDATE fii_registry SET setor = ?, updated_at = ? WHERE ticker = ?",
                    (setor, time.time(), ticker),
                )
                updated += 1
                logger.info("sector enricher: %s → %s (StatusInvest)", ticker, setor)
            else:
                logger.info("sector enricher: %s remains 'Outros' (SI gave %r)", ticker, setor)
            time.sleep(1.0)  # rate-limit SI requests

        conn.commit()

    logger.info(
        "sector enricher: done — %d updated, %d still 'Outros'",
        updated,
        len([t for t in still_unknown if conn.execute(
            "SELECT setor FROM fii_registry WHERE ticker = ?", (t,)
        ).fetchone()["setor"] == "Outros"]),
    )
    return updated
