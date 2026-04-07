#!/usr/bin/env python3
import sys
from pathlib import Path
import random
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Adiciona o diretório raiz ao path para conseguir importar 'api.db_sqlite'
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from api.db_sqlite import save_score_snapshot, save_sentiment_snapshot

def main():
    print("⏳ Populando banco SQLite de histórico artificial...")

    tickers_comuns = [
        "MXRF11", "HGLG11", "XPML11", "BTLG11", "VISC11", "KNCR11", 
        "CPTS11", "VGHF11", "XPLG11", "KNIP11", "RBVA11", "HGRU11",
        "TRXF11", "MCCI11", "ALZR11", "BCFF11"
    ]

    sentiments = ["POSITIVO", "NEUTRO", "NEGATIVO"]
    hoje = datetime.now()

    count_score = 0
    count_sent = 0

    for ticker in tickers_comuns:
        # Ponto de partida
        base_score = random.uniform(50.0, 85.0)

        # 12 meses para trás do Score
        for i in range(12, -1, -1):
            date_ref = hoje - relativedelta(months=i)
            # adiciona variação orgânica/fake
            variation = random.uniform(-4.0, 4.0)
            score = max(10, min(100, base_score + variation))
            base_score = score # random walk
            
            # Formata a data YYYY-MM
            date_str = date_ref.strftime("%Y-%m")
            
            detalhes = {
                "dy": round(random.uniform(7.0, 15.0), 2),
                "pvp": round(random.uniform(0.7, 1.3), 2),
                "vacancia": round(random.uniform(0.0, 15.0), 2)
            }
            save_score_snapshot(ticker, round(score, 1), detalhes, date_str)
            count_score += 1

        # 3 semanas para trás de Sentimento Artificial
        for i in range(3, -1, -1):
            date_ref = hoje - relativedelta(weeks=i)
            date_str = date_ref.strftime("%Y-%m-%d")
            
            # Tendemos a repetir o sentimento com 70% de chance, 30% pivot
            sent = random.choices(sentiments, weights=[40, 40, 20])[0]
            if i == 0:
                # O de hoje é fixado caso precisemos testar a virada visualmente
                pass
            
            save_sentiment_snapshot(ticker, sent, f"Análise simulada de {i} semanas atrás.", date_str)
            count_sent += 1

    print(f"✅ Sucesso. Inseridos {count_score} registros de score e {count_sent} registros de sentimento de IA retroativos.")

if __name__ == "__main__":
    main()
