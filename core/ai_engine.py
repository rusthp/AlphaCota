"""
core/ai_engine.py

Motor de analise de sentimento via Groq/Llama para FIIs.
Migrado de cota_ai/ai_service.py com melhorias:
- Import defensivo (HAS_GROQ flag)
- Sem side effects (load_dotenv removido, key via parametro)
- Funcao pura com retorno estruturado
- RAG via Vectorizer para contexto enriquecido
"""

import os
from core.logger import logger

try:
    from groq import Groq

    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False

try:
    from data.vectorizer_client import VectorizerClient

    _vectorizer = VectorizerClient()
except ImportError:
    _vectorizer = None


def get_vectorizer_context(query: str, limit: int = 3) -> str:
    """Busca contexto relevante no vectorizer para enriquecer prompts (RAG).

    Args:
        query: Texto de busca.
        limit: Máximo de trechos retornados.

    Returns:
        String com trechos relevantes do codebase ou vazio se indisponível.
    """
    if _vectorizer is None:
        return ""
    try:
        return _vectorizer.get_context_for_query(query, limit=limit)
    except Exception as e:
        logger.debug("Vectorizer context unavailable: %s", e)
        return ""


def analyze_fii_news(ticker: str, news_list: list[dict], api_key: str | None = None) -> dict:
    """Analisa noticias de um FII usando Groq/Llama e retorna sentimento estruturado.

    Args:
        ticker: Codigo do FII (ex: HGLG11)
        news_list: Lista de dicts com keys 'titulo', 'data', 'link'
        api_key: Groq API key. Se None, usa env var GROQ_API_KEY.

    Returns:
        Dict com keys: success, sentiment, summary, dividend_impact, raw_response
    """
    key = api_key or os.getenv("GROQ_API_KEY")

    if not key:
        return {"success": False, "error": "GROQ_API_KEY nao configurada"}

    if not HAS_GROQ:
        return {"success": False, "error": "Biblioteca groq nao instalada (pip install groq)"}

    if not news_list:
        return {"success": False, "error": "Nenhuma noticia fornecida para analise"}

    texto_noticias = "\n".join([f"- {n['titulo']} ({n.get('data', 'sem data')})" for n in news_list])

    # RAG: buscar contexto relevante no vectorizer
    rag_context = get_vectorizer_context(f"{ticker} FII análise dividendos", limit=3)
    rag_section = ""
    if rag_context:
        rag_section = f"""

    Contexto adicional da base de conhecimento:
    {rag_context}
    """

    prompt = f"""
    Voce e um analista senior de Fundos Imobiliarios (FIIs) do Brasil.
    Leia as seguintes manchetes recentes sobre o fundo {ticker}:

    {texto_noticias}
    {rag_section}
    Com base nessas noticias, forneca:
    1. Sentimento do Mercado: (Responda apenas POSITIVO, NEGATIVO ou NEUTRO)
    2. Resumo Executivo: Um paragrafo de ate 3 linhas resumindo o que esta acontecendo com o fundo.
    3. Impacto nos Dividendos: Ha algum risco ou chance de aumento de dividendos citado?

    Responda em Portugues do Brasil.
    """

    try:
        client = Groq(api_key=key)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Voce e um analista financeiro especializado em FIIs."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=1024,
        )
        raw = completion.choices[0].message.content
        return {"success": True, "raw_response": raw, "ticker": ticker, "news_count": len(news_list)}
    except Exception as e:
        return {"success": False, "error": f"Erro ao acionar Groq: {str(e)}"}
