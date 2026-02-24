import os
from groq import Groq
from dotenv import load_dotenv

def analisar_com_groq(ticker, news_list):
    load_dotenv()
    CHAVE_API = os.getenv("GROQ_API_KEY")
    
    if not CHAVE_API or "gsk_" not in CHAVE_API:
        return "❌ Chave Groq API não configurada corretamente no arquivo .env"

    if not news_list:
        return "Nenhuma notícia recente encontrada para analisar."

    print(f"🧠 Acionando Groq para analisar {ticker}...")
    
    # Prepara o texto para a IA ler
    texto_noticias = "\n".join([f"- {n['titulo']} ({n['data']})" for n in news_list])
    
    # O PROMPT (As instruções para o Cérebro)
    prompt = f"""
    Você é um analista sênior de Fundos Imobiliários (FIIs) do Brasil.
    Leia as seguintes manchetes recentes sobre o fundo {ticker}:
    
    {texto_noticias}
    
    Com base nessas notícias, forneça:
    1. Sentimento do Mercado: (Responda apenas POSITIVO, NEGATIVO ou NEUTRO)
    2. Resumo Executivo: Um parágrafo de até 3 linhas resumindo o que está acontecendo com o fundo.
    3. Impacto nos Dividendos: Há algum risco ou chance de aumento de dividendos citado?
    
    Responda em Português do Brasil.
    """
    
    try:
        client = Groq(api_key=CHAVE_API)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Você é um analista financeiro especializado em FIIs."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=1024,
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"❌ Erro ao acionar a Groq: {str(e)}"
