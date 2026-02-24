import feedparser

def buscar_noticias_fii(ticker):
    print(f"📰 Buscando notícias para {ticker}...")
    # Busca no Google News Brasil pelo Ticker do FII
    url = f"https://news.google.com/rss/search?q={ticker}+FII&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    feed = feedparser.parse(url)
    
    noticias = []
    # Pega as 5 notícias mais recentes
    for entry in feed.entries[:5]:
        noticias.append({
            "titulo": entry.title,
            "data": entry.published,
            "link": entry.link
        })
    
    return noticias
