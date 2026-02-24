import pandas as pd

def calcular_score_iniciante(row):
    """
    Foco: Estabilidade e Segurança.
    - P/VP ideal: 0.9 - 1.05 (não quer pegar pepino muito descontado, nem pagar caro).
    - DY: Consistente (valorizamos o fato de existir).
    """
    score = 0
    pvp = row['p_vp']
    dy = row['dividend_yield']
    
    # P/VP entre 0.9 e 1.05 é o sweet spot
    if 0.9 <= pvp <= 1.05:
        score += 50
    elif pvp < 0.9:
        score += 20 # Aceitável mas iniciante tem medo de 'value trap'
    
    # DY consistente (acima de 8% ao ano)
    if dy >= 8.0:
        score += 30
        if dy > 12.0: score += 10 # Bônus
        
    return score

def calcular_score_agressivo(row):
    """
    Foco: Oportunidade e Upside.
    - P/VP: Quanto mais baixo melhor (desconto).
    - DY: Quanto maior melhor.
    """
    score = 0
    pvp = row['p_vp']
    dy = row['dividend_yield']
    
    # Prestigia desconto agressivo
    if pvp < 0.8:
        score += 60
    elif pvp < 0.95:
        score += 40
        
    # Prestigia DY alto
    if dy > 11.0:
        score += 40
    elif dy > 9.0:
        score += 20
        
    return score

def calcular_score_inteligente(row):
    """
    Foco: Filtro Graham (Valor com Filtro de Qualidade).
    - Rígido: P/VP < 0.95 obrigatório.
    - DY: Estável.
    """
    pvp = row['p_vp']
    dy = row['dividend_yield']
    
    # Se não houver margem de segurança (desconto), score 0
    if pvp > 0.95 or pvp < 0.3: # Filtra lixo/erros de dados
        return 0
        
    score = 50 # Base pelo desconto
    if pvp < 0.85: score += 20
    
    if 9.0 <= dy <= 14.0: # Faixa de 'sustentabilidade'
        score += 30
    
    return score

def get_top_picks(df, profile, top_n=3):
    """Retorna os Top N ativos baseados no perfil e a justificativa."""
    if df.empty:
        return []
    
    temp_df = df.copy()
    
    if profile == "Iniciante":
        temp_df['score'] = temp_df.apply(calcular_score_iniciante, axis=1)
        justificativa = "Estabilidade e previsibilidade de renda."
    elif profile == "Agressivo":
        temp_df['score'] = temp_df.apply(calcular_score_agressivo, axis=1)
        justificativa = "Alto potencial de valorização e dividendos agressivos."
    elif profile == "Inteligente (Graham)":
        temp_df['score'] = temp_df.apply(calcular_score_inteligente, axis=1)
        justificativa = "Filtro rígido de valor: Margem de segurança + DY sustentável."
    else: # Mediano / Padrão
        temp_df['score'] = temp_df['dividend_yield'] * (1 / temp_df['p_vp']) # Fórmula básica
        justificativa = "Equilíbrio entre preço e rendimento."
        
    top_picks = temp_df.sort_values('score', ascending=False).head(top_n)
    
    results = []
    for _, row in top_picks.iterrows():
        if row['score'] > 0:
            results.append({
                "ticker": row['ticker'],
                "score": row['score'],
                "pvp": row['p_vp'],
                "dy": row['dividend_yield'],
                "justificativa": justificativa
            })
    return results
