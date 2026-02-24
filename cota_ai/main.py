import requests
from bs4 import BeautifulSoup
import db # Importa o arquivo que criamos acima

# --- CONFIGURAÇÕES DE FONTES ---
# Cada fonte tem sua URL e seletores CSS específicos
SOURCES = [
    {
        "name": "Investidor 10",
        "url": "https://investidor10.com.br/fiis/{ticker}/",
        "selectors": {
            "cotacao": "div._card.cotacao ._card-body span",
            "dy": "div._card.dy ._card-body span",
            "p_vp": "div._card.vp ._card-body span"
        }
    },
    {
        "name": "Funds Explorer",
        "url": "https://www.fundsexplorer.com.br/funds/{ticker}",
        "selectors": {
            "cotacao": ".headerTicker__content__price b",
            "dy": ".indicators .indicators__box:nth-child(3) p:nth-child(2)",
            "p_vp": ".indicators .indicators__box:nth-child(7) p:nth-child(2)"
        }
    },
    {
        "name": "StatusInvest",
        "url": "https://statusinvest.com.br/fundos-imobiliarios/{ticker}",
        "selectors": {
            "legacy": True # Usa a lógica anterior de busca por tag 'strong'
        }
    }
]

def limpar_valor(texto):
    """Limpa strings de valores financeiros para float."""
    if not texto: return 0.0
    # Remove R$, %, espaços e troca vírgula por ponto
    limpo = texto.replace('R$', '').replace('%', '').replace('.', '').replace(',', '.').strip()
    try:
        return float(limpo)
    except:
        return 0.0

def analisar_fii(ticker):
    print(f"\n🔍 Buscando dados de {ticker}...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    for source in SOURCES:
        try:
            print(f"   ∟ Tentando fonte: {source['name']}...")
            url = source['url'].format(ticker=ticker.lower())
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                print(f"   ⚠️ {source['name']} retornou status {response.status_code}")
                continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            if source.get("legacy"):
                # Lógica antiga do StatusInvest
                valores = soup.find_all('strong', class_='value')
                cotacao = limpar_valor(valores[0].text)
                dy = limpar_valor(valores[3].text)
                p_vp = limpar_valor(valores[6].text)
            else:
                # Lógica baseada em seletores identificados
                sel = source['selectors']
                cotacao = limpar_valor(soup.select_one(sel['cotacao']).text)
                dy = limpar_valor(soup.select_one(sel['dy']).text)
                p_vp = limpar_valor(soup.select_one(sel['p_vp']).text)
            
            # Validação básica: se os valores forem zero, algo falhou no parse
            if cotacao > 0:
                print(f"   ✅ Dados obtidos via {source['name']}!")
                return {
                    "cotacao_atual": cotacao,
                    "dividend_yield": dy,
                    "p_vp": p_vp,
                    "fonte": source['name']
                }
                
        except Exception as e:
            print(f"   ❌ Erro na fonte {source['name']}: {str(e)[:50]}...")
            continue
            
    print(f"❌ Não foi possível obter dados de {ticker} em nenhuma fonte.")
    return None

# 2. O MENTOR (Regras de Negócio)
def dar_veredito(ticker, metricas):
    p_vp = metricas['p_vp']
    dy = metricas['dividend_yield']
    fonte = metricas.get('fonte', 'Desconhecida')
    
    print(f"📊 --- RELATÓRIO: {ticker} (via {fonte}) ---")
    print(f"Preço: R$ {metricas['cotacao_atual']} | P/VP: {p_vp} | DY: {dy}% a.a.")
    
    # A Lógica de Investimento
    if p_vp <= 0.95:
        print("🟢 OPORTUNIDADE: Fundo sendo negociado com forte desconto!")
    elif 0.96 <= p_vp <= 1.04:
        print("🟡 PREÇO JUSTO: Fundo está no seu valor patrimonial.")
    else:
        print("🔴 CUIDADO: Fundo está CARO (Ágio). Risco de queda.")
        
    if dy < 8.0:
        print("⚠️ ALERTA: Dividend Yield abaixo da taxa Selic atual. Verifique os motivos.")

def escanear_mercado_statusinvest():
    """Usa a 'API oculta' do StatusInvest para pegar todos os FIIs de uma vez."""
    print("📡 Acessando scanner de mercado do StatusInvest...")
    url = "https://statusinvest.com.br/category/advancedsearchresult?search=%7B%22Sector%22%3A%22%22%2C%22SubSector%22%3A%22%22%2C%22Segment%22%3A%22%22%2C%22my_range%22%3A%220%3B20%22%2C%22dy%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_vp%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%7D&CategoryType=2"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            dados_brutos = response.json()
            print(f"✅ Encontrados {len(dados_brutos)} FIIs no mercado!")
            
            fiis_catalogados = []
            for item in dados_brutos:
                ticker = item['ticker']
                fiis_catalogados.append({
                    "ticker": ticker,
                    "metrics": {
                        "cotacao_atual": float(item.get('price', 0)),
                        "dividend_yield": float(item.get('dy', 0)),
                        "p_vp": float(item.get('p_vp', 0)),
                        "fonte": "StatusInvest (Mass Scan)"
                    }
                })
            return fiis_catalogados
    except Exception as e:
        print(f"❌ Erro no scanner: {e}")
    
    return []

def rodar_atualizacao_completa():
    # Garante que as tabelas existem
    db.conectar_banco()
    
    # Agora busca os tickers do banco em vez de uma lista fixa!
    meus_fiis = db.buscar_todos_tickers()
    
    if not meus_fiis:
        print("ℹ️ Nenhum FII cadastrado no banco ainda. Adicione pelo Dashboard!")
        return

    print(f"🚀 Iniciando atualização de {len(meus_fiis)} ativos...")
    for fii in meus_fiis:
        dados = analisar_fii(fii)
        if dados:
            dar_veredito(fii, dados)
            db.salvar_ativo(ticker=fii, asset_type="FII", metricas=dados)
            print("-" * 40)

# 3. O MOTOR PRINCIPAL (Onde a mágica acontece)
if __name__ == "__main__":
    rodar_atualizacao_completa()
