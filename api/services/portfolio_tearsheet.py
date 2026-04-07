import os
import tempfile
import pandas as pd
import yfinance as yf
import quantstats as qs
from typing import Dict
from datetime import datetime, timedelta

# Ensure quantstats extends pandas natively
qs.extend_pandas()

def generate_tearsheet(portfolio_alloc: Dict[str, float], benchmark: str = "^BVSP", period_days: int = 730) -> str:
    """
    Gera um relatório HTML completo da carteira usando o Quantstats.
    
    :param portfolio_alloc: Dicionário das alocações { "MXRF11": 0.40, "HGLG11": 0.60 }
    :param benchmark: Ticker yfinance do benchmark ('^BVSP', ou um FII como 'BTLG11.SA' simulando IFIX)
    :param period_days: Histórico de tempo para baixar (padrão: 2 anos)
    :return: Caminho do arquivo HTML temporário onde o report foi salvo.
    """
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=period_days)
    
    # 1. Download de Preços de Fechamento Ajustados da Carteira
    tickers_yf = [f"{t}.SA" if not t.endswith(".SA") else t for t in portfolio_alloc.keys()]
    
    # Validação rápida de peso (se não vier normalizado, a gente normaliza)
    total_weight = sum(portfolio_alloc.values())
    if total_weight == 0:
        raise ValueError("Pesos da carteira inválidos (soma zero).")
        
    weights = [portfolio_alloc[t] / total_weight for t in portfolio_alloc.keys()]
    
    try:
        data = yf.download(tickers_yf, start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
        
        if "Adj Close" in data:
            prices = data["Adj Close"]
        elif "Close" in data:
            prices = data["Close"]
        else:
            raise ValueError("Não foi possível encontrar dados de preço (Adj Close/Close).")
            
        # Caso só 1 FII na carteira, o Pandas retorna Serie em vez de DF, então forçamos DF
        if isinstance(prices, pd.Series):
            prices = prices.to_frame(tickers_yf[0])
            
        # Alinha os nomes das colunas com nossa lista weights
        prices = prices[tickers_yf]
        
    except Exception as e:
        raise ValueError(f"Falha ao baixar dados do yfinance: {str(e)}")
        
    # 2. Computa de retornos diários (%)
    # preenche NaN com método bfill ou drop para não quebrar a soma
    returns_df = prices.pct_change().dropna()
    
    # 3. Retorno do Portfólio = Soma(Retorno Diário * Peso)
    portfolio_daily_returns = (returns_df * weights).sum(axis=1)
    # Define como series e formata indíce datetime
    portfolio_daily_returns.index = pd.to_datetime(portfolio_daily_returns.index)
    
    # 4. Tenta fazer Download de Benchmark
    # Se IFX não existe de forma perfeita no Yahoo, aceita ^BVSP ou BOVA11
    benchmark_returns = None
    if benchmark:
        try:
            bm_data = yf.download(benchmark, start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
            bm_prices = bm_data["Adj Close"] if "Adj Close" in bm_data else bm_data["Close"]
            benchmark_returns = bm_prices.pct_change().dropna()
            benchmark_returns.index = pd.to_datetime(benchmark_returns.index)
        except Exception:
            benchmark_returns = None # Ignora benchmark se falhar
            
    # 5. Criar arquivo temporário para o HTML Final
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".html")
    os.close(tmp_fd) 
    
    # 6. Gerar o HTML Report
    try:
        qs.reports.html(
            portfolio_daily_returns,
            benchmark=benchmark_returns,
            output=tmp_path,
            title="AlphaCota - Relatório Quantitativo Institucional",
            download_filename="alphacota_tearsheet.html"
        )
    except Exception as e:
        raise RuntimeError(f"Erro ao compilar o Tearsheet no QuantStats: {str(e)}")
        
    return tmp_path
