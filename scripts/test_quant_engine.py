import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.quant_engine import evaluate_company

def main():
    # Empresa saudavel porem em colapso total no grafico (Armadilha de Valor)
    data_wege = {
        "pl": 6.0,
        "pvp": 1.0,
        "roe": 25.0,
        "roa": 15.0,
        "revenue_growth": 10.0,
        "earnings_growth": 15.0,
        "debt_to_equity": 0.5,
        "current_ratio": 2.5,
        "total_assets": 10000.0,
        "total_liabilities": 4000.0,
        "working_capital": 3000.0,
        "retained_earnings": 5000.0,
        "ebit": 1500.0,
        "market_value_equity": 6000.0,
        "revenue": 8000.0
    }
    
    # 12 meses de queda constante (120 ate 30) - Faca Caindo
    precos_queda = [120.0, 110.0, 100.0, 90.0, 80.0, 70.0, 60.0, 50.0, 45.0, 40.0, 35.0, 30.0]
    
    res = evaluate_company("WEGETRAP", data_wege, historical_prices=precos_queda)
    
    print("\n[RESULTADO QUANTAMENTAL] Faca Caindo (Bons fundamentos, grafico derretendo)")
    print(res)
    print("--------------------------------------------------")

    # 12 meses de alta forte
    precos_alta = [30.0, 35.0, 40.0, 45.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0]
    res_alta = evaluate_company("WEGEBULL", data_wege, historical_prices=precos_alta)
    
    print("\n[RESULTADO QUANTAMENTAL] Tourada (Bons fundamentos, grafico bombando)")
    print(res_alta)

if __name__ == "__main__":
    main()
