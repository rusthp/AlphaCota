# services/rebalance_engine.py

def calculate_weight_drift(current_weights: dict[str, float], target_weights: dict[str, float]) -> dict[str, float]:
    """
    Calcula o desvio percentual absoluto de cada ativo entre a carteira atual e o alvo ideal.
    """
    drift = {}
    
    # Verifica ativos atuais
    for ticker, current in current_weights.items():
        target = target_weights.get(ticker, 0.0)
        drift[ticker] = abs(current - target)
        
    # Verifica itens que estão no alvo mas não existem na carteira atual
    for ticker, target in target_weights.items():
        if ticker not in drift:
            drift[ticker] = target # O desvio é o próprio target já que o current é 0
            
    return drift

def should_rebalance(drift: dict[str, float], threshold: float = 0.05) -> bool:
    """
    Decide se o rebalanceamento estrutural é necessário baseado em um teto de desvio (padrão de 5%).
    Se qualquer ativo ultrapassar o limiar de desvio, o rebalanceamento é comutado.
    """
    for ticker, d in drift.items():
        if d > threshold:
            return True
    return False

def detect_universe_change(old_universe: set[str], new_universe: set[str]) -> bool:
    """
    Verifica se houve alguma remoção ou inclusão brusca no 'Universo de Elite'.
    Ex: Uma empresa que faliu (caiu no Altman Z) deve forçar a liquidação imediata, o que dispara rebalanceamento.
    """
    return old_universe != new_universe

def run_rebalance_check(
    current_weights: dict[str, float], 
    target_weights: dict[str, float], 
    old_universe: set[str], 
    new_universe: set[str], 
    threshold: float = 0.05
) -> bool:
    """
    Gatilho final verificando se a anomalia estrutural ou oscilação de mercado
    autoriza uma ordem real de compra/venda na carteira do investidor.
    """
    # 1. Mudanca de Qualidade Extrema (Life-or-Death)
    if detect_universe_change(old_universe, new_universe):
        return True
        
    # 2. Desvio de Risco de Portfólio (Oscilação de Preços Excedida)
    drift = calculate_weight_drift(current_weights, target_weights)
    if should_rebalance(drift, threshold):
        return True
        
    # Nenhuma acao necessaria (Silencia Ruído)
    return False
