import sqlite3
import json

def conectar_banco():
    # Cria um arquivo de banco de dados local na sua pasta
    conn = sqlite3.connect('meus_investimentos.db')
    cursor = conn.cursor()
    
    # Tabela escalável (Note o asset_type e a coluna JSON para métricas)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assets (
            ticker TEXT PRIMARY KEY,
            asset_type TEXT,
            metrics_data JSON,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabela de Portfolio (Meus Ativos)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio (
            ticker TEXT PRIMARY KEY,
            quantidade INTEGER DEFAULT 0
        )
    ''')
    
    # Tabela de Cache de IA (Insights)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_insights (
            ticker TEXT PRIMARY KEY,
            insight TEXT,
            created_at DATE DEFAULT (DATE('now'))
        )
    ''')
    
    conn.commit()
    return conn, cursor

def salvar_ativo(ticker, asset_type, metricas):
    conn, cursor = conectar_banco()
    # Converte o dicionário de métricas do Python para texto JSON
    json_metricas = json.dumps(metricas)
    
    # Salva ou atualiza o ativo
    cursor.execute('''
        INSERT INTO assets (ticker, asset_type, metrics_data, last_updated)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(ticker) DO UPDATE SET 
            metrics_data=excluded.metrics_data,
            last_updated=CURRENT_TIMESTAMP
    ''', (ticker, asset_type, json_metricas))
    
    conn.commit()
    conn.close()
    print(f"✅ {ticker} salvo no banco de dados!")

def salvar_posicao(ticker, quantidade):
    conn, cursor = conectar_banco()
    # UPSERT: Insere ou atualiza a quantidade para o ticker
    cursor.execute('''
        INSERT INTO portfolio (ticker, quantidade)
        VALUES (?, ?)
        ON CONFLICT(ticker) DO UPDATE SET quantidade=excluded.quantidade
    ''', (ticker, quantidade))
    conn.commit()
    conn.close()
    print(f"💼 Posição de {ticker} atualizada: {quantidade} cotas.")

def buscar_portfolio():
    conn, cursor = conectar_banco()
    cursor.execute("SELECT ticker, quantidade FROM portfolio")
    linhas = cursor.fetchall()
    conn.close()
    # Retorna um dicionário {ticker: quantidade}
    return {linha[0]: linha[1] for linha in linhas}

def salvar_insight(ticker, insight):
    conn, cursor = conectar_banco()
    cursor.execute('''
        INSERT INTO ai_insights (ticker, insight, created_at)
        VALUES (?, ?, DATE('now'))
        ON CONFLICT(ticker) DO UPDATE SET 
            insight=excluded.insight,
            created_at=excluded.created_at
    ''', (ticker, insight))
    conn.commit()
    conn.close()
    print(f"🧠 Insight de {ticker} salvo em cache.")

def buscar_insight_recente(ticker):
    conn, cursor = conectar_banco()
    # Verifica se existe um insight gerado hoje
    cursor.execute('''
        SELECT insight FROM ai_insights 
        WHERE ticker = ? AND created_at = DATE('now')
    ''', (ticker,))
    resultado = cursor.fetchone()
    conn.close()
    return resultado[0] if resultado else None

def buscar_todos_tickers():
    conn, cursor = conectar_banco()
    cursor.execute('SELECT ticker FROM assets')
    linhas = cursor.fetchall()
    conn.close()
    return [linha[0] for linha in linhas]

def deletar_ativo(ticker):
    conn, cursor = conectar_banco()
    # Remove de todas as tabelas relacionadas
    cursor.execute('DELETE FROM assets WHERE ticker = ?', (ticker,))
    cursor.execute('DELETE FROM portfolio WHERE ticker = ?', (ticker,))
    cursor.execute('DELETE FROM ai_insights WHERE ticker = ?', (ticker,))
    conn.commit()
    conn.close()
    print(f"🗑️ Ativo {ticker} removido do sistema.")
