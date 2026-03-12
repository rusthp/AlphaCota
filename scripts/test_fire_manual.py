from core.fire_engine import calculate_years_to_fire, calculate_required_capital

anos = calculate_years_to_fire(
    patrimonio_atual=10000,
    aporte_mensal=300,
    taxa_anual=0.10,
    renda_alvo_anual=120000
)

capital = calculate_required_capital(
    renda_alvo_anual=120000,
    taxa_anual=0.10
)

print(f"Patrimônio Necessário: R$ {capital:.2f}")
print(f"Anos estimados para o FIRE: {anos} anos")
