# AlphaCota v2 — Task List

## Fase 1 — Quant Foundation (0–3 meses)

### 1.1 Backtest Engine
- [ ] 1.1.1 Criar `core/backtest_engine.py`
- [ ] 1.1.2 Implementar loop de aportes mensais simulados
- [ ] 1.1.3 Implementar rebalanceamento periódico na simulação
- [ ] 1.1.4 Adicionar cálculo de CAGR
- [ ] 1.1.5 Adicionar cálculo de Sharpe Ratio
- [ ] 1.1.6 Adicionar cálculo de Sortino Ratio
- [ ] 1.1.7 Adicionar cálculo de Max Drawdown
- [ ] 1.1.8 Adicionar cálculo de Volatilidade Anual
- [ ] 1.1.9 Implementar comparação contra benchmark IFIX
- [ ] 1.1.10 Escrever testes unitários para o backtest engine

### 1.2 Camada de Dados Históricos
- [ ] 1.2.1 Criar estrutura de diretórios `data/`
- [ ] 1.2.2 Criar `data/historical_prices/`
- [ ] 1.2.3 Criar `data/historical_dividends/`
- [ ] 1.2.4 Criar `data/macro/`
- [ ] 1.2.5 Criar script coletor de preços históricos
- [ ] 1.2.6 Criar script coletor de dividendos históricos
- [ ] 1.2.7 Criar script coletor de P/VP histórico
- [ ] 1.2.8 Integrar dados históricos com o backtest engine

### 1.3 Formalização do Score Engine
- [ ] 1.3.1 Auditar o `core/score_engine.py` atual e documentar lógica existente
- [ ] 1.3.2 Definir pesos explícitos: `w_valuation`, `w_income`, `w_risk`
- [ ] 1.3.3 Substituir heurísticas por fórmula matemática documentada
- [ ] 1.3.4 Adicionar função de otimização de pesos
- [ ] 1.3.5 Escrever testes unitários para o novo score engine

---

## Fase 2 — Risk & Optimization (3–6 meses)

### 2.1 Correlação entre FIIs
- [ ] 2.1.1 Criar `core/correlation_engine.py`
- [ ] 2.1.2 Implementar geração de matriz de correlação entre FIIs
- [ ] 2.1.3 Implementar mapa de concentração por setor
- [ ] 2.1.4 Calcular risco sistêmico da carteira
- [ ] 2.1.5 Integrar correlação com `class_rebalancer.py`

### 2.2 Otimização de Carteira (Markowitz)
- [ ] 2.2.1 Adicionar `PyPortfolioOpt` como dependência
- [ ] 2.2.2 Implementar Mean-Variance Optimization
- [ ] 2.2.3 Implementar simulação Monte Carlo de portfólio
- [ ] 2.2.4 Implementar cálculo da fronteira eficiente
- [ ] 2.2.5 Expor Max Sharpe e Min Volatility como estratégias selecionáveis

### 2.3 Stress Testing
- [ ] 2.3.1 Criar `core/stress_engine.py`
- [ ] 2.3.2 Implementar cenário: alta de juros
- [ ] 2.3.3 Implementar cenário: queda abrupta de mercado
- [ ] 2.3.4 Implementar cenário: redução de dividendos
- [ ] 2.3.5 Exibir impacto dos cenários no dashboard

---

## Fase 3 — Arquitetura SaaS (6–12 meses)

### 3.1 Quant Engine como Microserviço
- [ ] 3.1.1 Criar repositório `alphacota-quant`
- [ ] 3.1.2 Expor endpoints FastAPI: score, backtest, simulação
- [ ] 3.1.3 Dockerizar o serviço quant

### 3.2 API Principal em TypeScript
- [ ] 3.2.1 Criar projeto NestJS para a API principal
- [ ] 3.2.2 Implementar módulo de autenticação (JWT)
- [ ] 3.2.3 Implementar módulo de usuários e carteiras
- [ ] 3.2.4 Implementar módulo de histórico de recomendações
- [ ] 3.2.5 Configurar PostgreSQL e migrations

### 3.3 Frontend Moderno
- [ ] 3.3.1 Criar projeto Next.js
- [ ] 3.3.2 Implementar dashboard principal com charts interativos
- [ ] 3.3.3 Implementar simulador FIRE responsivo

---

## Fase 4 — Diferenciação Real (12+ meses)

- [ ] 4.1 Implementar aprendizado adaptativo de pesos
- [ ] 4.2 Suportar multi-ativos (Ações, ETFs, além de FIIs)
- [ ] 4.3 Criar API pública documentada
- [ ] 4.4 Criar simulador FIRE comparativo por estratégia
