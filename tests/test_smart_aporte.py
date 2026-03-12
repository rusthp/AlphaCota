import pytest
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.smart_aporte import generateAporteSuggestion

@pytest.fixture
def base_universe():
    return [
        {'ticker': 'IVVB11', 'classe': 'ETF', 'ativo': True, 'preco_atual': 250.0},
        {'ticker': 'BNDX11', 'classe': 'ETF', 'ativo': True, 'preco_atual': 100.0},
        {'ticker': 'BBSE3', 'classe': 'ACAO', 'ativo': True, 'preco_atual': 30.0},
        {'ticker': 'WEGE3', 'classe': 'ACAO', 'ativo': True, 'preco_atual': 40.0},
        {'ticker': 'MXRF11', 'classe': 'FII', 'ativo': True, 'preco_atual': 10.0},
    ]

def test_rejects_insufficient_funds_for_new_asset(base_universe):
    portfolio = []
    # ETF IVVB11 custa 250, aporte de 200 dever dar erro
    sugestao = generateAporteSuggestion('ETF', portfolio, base_universe, 200.0)
    assert "erro" in sugestao
    assert sugestao["erro"] == "Valor insuficiente para comprar 1 unidade"

def test_returns_integer_quantity_and_correct_change(base_universe):
    portfolio = []
    # FII MXRF11 custa 10, aporte de 55 deve comprar 5 e sobrar 5
    sugestao = generateAporteSuggestion('FII', portfolio, base_universe, 55.0)
    assert sugestao.get("tipo_operacao") == "novo_ativo"
    assert sugestao.get("ticker") == "MXRF11"
    assert sugestao.get("quantidade") == 5
    assert sugestao.get("valor_utilizado") == 50.0
    assert sugestao.get("valor_restante") == 5.0
    assert type(sugestao.get("quantidade")) is int

def test_reinforce_asset_with_insufficient_funds(base_universe):
    portfolio = [
         {'ticker': 'BBSE3', 'classe': 'ACAO', 'quantidade': 100, 'preco_atual': 30.0},
         {'ticker': 'WEGE3', 'classe': 'ACAO', 'quantidade': 20, 'preco_atual': 40.0}
    ]
    # Aporte 30 (nem WEGE nem BBSE vai conseguir se for pra ajudar a WEGE que custa 40)
    sugestao = generateAporteSuggestion('ACAO', portfolio, base_universe, 30.0)
    assert "erro" in sugestao
    assert sugestao["erro"] == "Valor insuficiente para reforço"

def test_never_uses_default_price():
    universe_without_price = [
         {'ticker': 'MXRF11', 'classe': 'FII', 'ativo': True}, # Sem preco_atual
    ]
    sugestao = generateAporteSuggestion('FII', [], universe_without_price, 100.0)
    assert "erro" in sugestao
    assert sugestao["erro"] == "Preço do ativo selecionado é inválido"
    
def test_valid_reinforcement_change_calculation(base_universe):
    portfolio = [
         {'ticker': 'BBSE3', 'classe': 'ACAO', 'quantidade': 100, 'preco_atual': 30.0},
         {'ticker': 'WEGE3', 'classe': 'ACAO', 'quantidade': 20, 'preco_atual': 40.0}
    ]
    # WEGE3 é a menor posicao. Custa 40. Aporte 100 compra 2, usa 80, resta 20.
    sugestao = generateAporteSuggestion('ACAO', portfolio, base_universe, 100.0)
    assert sugestao.get("tipo_operacao") == "reforco"
    assert sugestao.get("ticker") == "WEGE3"
    assert sugestao.get("quantidade") == 2
    assert sugestao.get("valor_utilizado") == 80.0
    assert sugestao.get("valor_restante") == 20.0
