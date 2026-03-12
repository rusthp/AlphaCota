from core.portfolio_engine import calculate_portfolio_allocation
import json

def run_test():
    ativos = [
        {"ticker": "BBSE3", "valor": 5000},
        {"ticker": "MXRF11", "valor": 3000},
        {"ticker": "ITSA4", "valor": 2000},
    ]

    resultado = calculate_portfolio_allocation(ativos)
    
    print("Resultado da Alocação de Portfólio:")
    print(json.dumps(resultado, indent=2))

if __name__ == "__main__":
    run_test()
