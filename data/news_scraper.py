"""
data/news_scraper.py

Scraper de noticias de FIIs via multiplas fontes RSS.
Fontes:
- Google News RSS (busca por ticker)
- InfoMoney RSS (mercado imobiliario)
- Suno Research RSS (FIIs)
- FIIs.com.br RSS (especifico de fundos imobiliarios)
- Valor Economico RSS (investimentos)
- Investing.com BR RSS (REITs/FIIs)

Migrado de cota_ai/news_scraper.py com melhorias:
- Import defensivo (HAS_FEEDPARSER flag)
- Multiplas fontes RSS
- Deduplicacao por titulo
- Parametro max_results configuravel
- Retorno tipado
"""

import re
from datetime import datetime
from core.logger import get_logger

logger = get_logger(__name__)

try:
    import feedparser

    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False


# ---------------------------------------------------------------------------
# Fontes RSS
# ---------------------------------------------------------------------------

# Fontes especificas por ticker (query dinamica)
_TICKER_RSS_SOURCES = [
    {
        "name": "Google News",
        "url_template": "https://news.google.com/rss/search?q={ticker}+FII&hl=pt-BR&gl=BR&ceid=BR:pt-419",
    },
    {
        "name": "Google News Finance",
        "url_template": "https://news.google.com/rss/search?q={ticker}+fundo+imobiliario&hl=pt-BR&gl=BR&ceid=BR:pt-419",
    },
]

# Fontes gerais de noticias de FIIs (sem filtro por ticker)
_GENERAL_RSS_SOURCES = [
    {
        "name": "InfoMoney - FIIs",
        "url": "https://www.infomoney.com.br/feed/",
        "filter_keywords": ["fii", "fundo imobiliário", "fundo imobiliario", "ifix", "dividendo"],
    },
    {
        "name": "Suno Research",
        "url": "https://www.suno.com.br/noticias/fundos-imobiliarios/feed/",
        "filter_keywords": [],  # Ja e filtrado por categoria
    },
    {
        "name": "FIIs.com.br",
        "url": "https://fiis.com.br/feed/",
        "filter_keywords": [],  # Ja e especifico
    },
    {
        "name": "Valor Investe",
        "url": "https://valorinveste.globo.com/rss/valorinveste/",
        "filter_keywords": ["fii", "fundo imobiliário", "fundo imobiliario", "ifix"],
    },
    {
        "name": "Investing.com BR",
        "url": "https://br.investing.com/rss/news.rss",
        "filter_keywords": ["fii", "fundo imobiliário", "fundo imobiliario", "ifix", "reit"],
    },
]


def _parse_date(entry: dict) -> str:
    """Extrai data de um entry RSS, com fallback."""
    for field in ("published", "updated", "created"):
        val = getattr(entry, field, None) or entry.get(field)
        if val:
            return str(val)
    return datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT")


def _entry_matches_ticker(entry: dict, ticker: str) -> bool:
    """Verifica se um entry RSS menciona o ticker."""
    ticker_upper = ticker.upper()
    ticker_pattern = re.compile(re.escape(ticker_upper), re.IGNORECASE)

    title = getattr(entry, "title", "") or entry.get("title", "")
    summary = getattr(entry, "summary", "") or entry.get("summary", "")

    return bool(ticker_pattern.search(title) or ticker_pattern.search(summary))


def _entry_matches_keywords(entry: dict, keywords: list[str]) -> bool:
    """Verifica se um entry RSS contem alguma keyword."""
    if not keywords:
        return True  # Sem filtro = aceita tudo

    title = (getattr(entry, "title", "") or entry.get("title", "")).lower()
    summary = (getattr(entry, "summary", "") or entry.get("summary", "")).lower()
    text = f"{title} {summary}"

    return any(kw in text for kw in keywords)


def _deduplicate_news(news: list[dict]) -> list[dict]:
    """Remove noticias duplicadas baseado no titulo normalizado."""
    seen: set[str] = set()
    unique: list[dict] = []

    for item in news:
        # Normaliza titulo para dedup
        key = re.sub(r"\s+", " ", item["titulo"].lower().strip())
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


# ---------------------------------------------------------------------------
# API Publica
# ---------------------------------------------------------------------------

def fetch_fii_news(ticker: str, max_results: int = 10) -> list[dict]:
    """Busca noticias recentes de um FII via multiplas fontes RSS.

    Args:
        ticker: Codigo do FII (ex: HGLG11)
        max_results: Numero maximo de noticias (default: 10)

    Returns:
        Lista de dicts com keys: titulo, data, link, fonte
    """
    if not HAS_FEEDPARSER:
        return []

    ticker_clean = ticker.replace(".SA", "").upper()
    all_news: list[dict] = []

    # 1. Fontes especificas por ticker
    for source in _TICKER_RSS_SOURCES:
        try:
            url = source["url_template"].format(ticker=ticker_clean)
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                all_news.append({
                    "titulo": entry.title,
                    "data": _parse_date(entry),
                    "link": entry.get("link", ""),
                    "fonte": source["name"],
                })
        except Exception as e:
            logger.debug("Erro ao buscar %s de %s: %s", ticker_clean, source["name"], e)

    # 2. Fontes gerais filtradas por ticker
    for source in _GENERAL_RSS_SOURCES:
        try:
            feed = feedparser.parse(source["url"])
            for entry in feed.entries[:20]:
                if _entry_matches_ticker(entry, ticker_clean):
                    all_news.append({
                        "titulo": entry.title,
                        "data": _parse_date(entry),
                        "link": entry.get("link", ""),
                        "fonte": source["name"],
                    })
        except Exception as e:
            logger.debug("Erro ao buscar feed %s: %s", source["name"], e)

    # 3. Deduplica e limita
    unique = _deduplicate_news(all_news)
    return unique[:max_results]


def fetch_market_news(max_results: int = 20) -> list[dict]:
    """Busca noticias gerais do mercado de FIIs (sem filtro de ticker).

    Args:
        max_results: Numero maximo de noticias.

    Returns:
        Lista de dicts com keys: titulo, data, link, fonte
    """
    if not HAS_FEEDPARSER:
        return []

    all_news: list[dict] = []

    # Google News geral de FIIs
    try:
        url = "https://news.google.com/rss/search?q=fundos+imobiliarios+FII&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        feed = feedparser.parse(url)
        for entry in feed.entries[:10]:
            all_news.append({
                "titulo": entry.title,
                "data": _parse_date(entry),
                "link": entry.get("link", ""),
                "fonte": "Google News",
            })
    except Exception as e:
        logger.debug("Erro ao buscar Google News geral: %s", e)

    # Fontes especializadas
    for source in _GENERAL_RSS_SOURCES:
        try:
            feed = feedparser.parse(source["url"])
            keywords = source.get("filter_keywords", [])
            for entry in feed.entries[:10]:
                if _entry_matches_keywords(entry, keywords):
                    all_news.append({
                        "titulo": entry.title,
                        "data": _parse_date(entry),
                        "link": entry.get("link", ""),
                        "fonte": source["name"],
                    })
        except Exception as e:
            logger.debug("Erro ao buscar feed %s: %s", source["name"], e)

    unique = _deduplicate_news(all_news)
    return unique[:max_results]


def list_sources() -> list[dict]:
    """Retorna a lista de fontes RSS configuradas.

    Returns:
        Lista de dicts com name e type (ticker/general).
    """
    sources = []
    for s in _TICKER_RSS_SOURCES:
        sources.append({"name": s["name"], "type": "ticker"})
    for s in _GENERAL_RSS_SOURCES:
        sources.append({"name": s["name"], "type": "general"})
    return sources
