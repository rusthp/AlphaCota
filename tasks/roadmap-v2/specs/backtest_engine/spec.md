# Spec: Backtest Engine

## Módulo: `core/backtest_engine.py`

---

## ADDED Requirements

### Requirement: Simulação de Aportes Mensais
O sistema SHALL simular aportes mensais de valor fixo em um período histórico definido.

#### Scenario: Simulação básica
Given um histórico de preços e dividendos
When o usuário executa o backtest com aporte mensal e período definidos
Then o sistema MUST retornar a evolução patrimonial mês a mês

---

### Requirement: Rebalanceamento Periódico
O sistema SHALL aplicar rebalanceamento da carteira conforme frequência configurável (mensal, trimestral, semestral).

#### Scenario: Rebalanceamento trimestral
Given uma carteira com pesos alvo definidos
When ao final de um trimestre os pesos reais divergem dos pesos alvo
Then o sistema MUST recalcular as ordens de compra/venda para restaurar os pesos alvo

---

### Requirement: Métricas de Performance
O sistema MUST calcular e retornar as seguintes métricas ao final do backtest:

| Métrica             | Fórmula / Referência              |
|---------------------|-----------------------------------|
| CAGR                | `(Vf / Vi)^(1/anos) - 1`         |
| Sharpe Ratio        | `(retorno_médio - rf) / std_dev` |
| Sortino Ratio       | `(retorno_médio - rf) / downside_std` |
| Max Drawdown        | `max(peak - trough) / peak`      |
| Volatilidade Anual  | `std_dev_mensal × sqrt(12)`      |

---

### Requirement: Comparação com Benchmark IFIX
O sistema SHALL comparar a performance da carteira simulada contra o IFIX no mesmo período.

#### Scenario: Comparação de CAGR
Given o período de backtest
When o backtest é concluído
Then o sistema MUST retornar o CAGR da carteira e o CAGR do IFIX lado a lado

---

### Requirement: Interface do Módulo
O módulo SHALL expor funções puras com as seguintes assinaturas:

```python
def run_backtest(
    tickers: list[str],
    weights: dict[str, float],
    monthly_contribution: float,
    start_date: str,
    end_date: str,
    rebalance_frequency: str,  # "monthly" | "quarterly" | "semiannual"
) -> BacktestResult:
    ...

def calculate_metrics(returns: list[float], risk_free_rate: float) -> PerformanceMetrics:
    ...
```

---

### Requirement: Dependência de Dados
O módulo SHALL consumir dados da camada `data/historical_prices/` e `data/historical_dividends/`.
O sistema MUST falhar explicitamente (com mensagem legível) se os dados históricos não existirem para um ticker solicitado.

---

## Delta de Arquivos

### ADDED
- `core/backtest_engine.py` — motor principal de backtest
- `data/historical_prices/` — diretório de séries de cotações
- `data/historical_dividends/` — diretório de séries de dividendos
- `tests/test_backtest_engine.py` — testes unitários do motor

### MODIFIED
- `core/score_engine.py` — formalizar pesos como constantes configuráveis
