# AlphaCota v2 — Task List

## ✅ Fase 1 — Quant Foundation (CONCLUÍDA)

### 1.1 Backtest Engine
- [x] 1.1.1 Criar `core/backtest_engine.py` com funções puras
- [x] 1.1.2 Loop de aportes mensais simulados
- [x] 1.1.3 Rebalanceamento periódico na simulação
- [x] 1.1.4 Cálculo de CAGR, Sharpe, Sortino, Max Drawdown, Volatilidade Anual
- [x] 1.1.5 Comparação contra benchmark
- [x] 1.1.6 27/27 testes unitários passando

### 1.2 Camada de Dados Históricos
- [x] 1.2.1 Criar estrutura `data/` com subdiretórios
- [x] 1.2.2 Criar `data/data_loader.py` — coletor de preços e dividendos via yfinance
- [x] 1.2.3 IFIX/Benchmark via `fetch_prices('^BVSP', ...)` no `data_loader.py`
- [x] 1.2.4 Criar `scripts/bootstrap_data.py` para pré-carregamento em lote

### 1.3 Formalização do Score Engine
- [x] 1.3.1 Auditar `core/score_engine.py` atual
- [x] 1.3.2 Substituir heurísticas por fórmula matemática explícita com pesos configuráveis
- [x] 1.3.3 Integrar novo score_engine no `services/allocation_pipeline.py`

### 1.4 Infraestrutura (descoberto na auditoria)
- [x] 1.4.1 Criar `requirements.txt` com todas as dependências
- [x] 1.4.2 Adicionar comando `backtest` ao `cli.py`
- [x] 1.4.3 Integrar backtest no `frontend/dashboard.py` (nova aba)

---

## ⬜ Fase 2 — Risk & Optimization (próximo)

### ✅ FASE 2.1 — Correlation Engine (CONCLUÍDA)
- [x] 2.1.1 Criar `core/correlation_engine.py`
- [x] 2.1.2 Matriz de correlação entre FIIs (Pearson N×N)
- [x] 2.1.3 Concentração setorial com Índice HHI
- [x] 2.1.4 Risco sistêmico: volatilidade de portfólio com correlações, Diversification Ratio
- [x] 2.1.5 `suggest_rebalance_with_correlation` — rebalanceamento ciente de correlação
- [x] 2.1.6 Aba "Risco & Correlação" no dashboard: heatmap, pizza setorial, alertas automáticos
- [x] 2.1.7 25/25 testes unitários passando (52 acumulado)

### ✅ FASE 2.2 — Markowitz + Fronteira Eficiente (CONCLUÍDA)
- [x] 2.2.1 Criar `core/markowitz_engine.py` (Python puro, sem deps externas)
- [x] 2.2.2 Retorno/volatilidade esperados e volatilidade matricial com correlações
- [x] 2.2.3 Monte Carlo de N portfólios (simulate_portfolio_frontier)
- [x] 2.2.4 Max Sharpe + Min Volatility + Equal Weight como baseline
- [x] 2.2.5 Aba "Markowitz — Fronteira Eficiente" no dashboard: scatter RdYlGn, pizzas, tabela
- [x] 2.2.6 26/26 testes unitários passando (78 acumulado)

### ✅ FASE 2.3 — Stress Testing (CONCLUÍDA)
- [x] 2.3.1 Criar `core/stress_engine.py` com 7 cenários pré-definidos
- [x] 2.3.2 Choque diferenciado por setor (Papel, Logística, Shopping, Lajes, FoF)
- [x] 2.3.3 apply_stress_scenario: impacto R$ e % por ativo, patrimônio e dividendos
- [x] 2.3.4 run_stress_suite: múltiplos cenários ordenados + summarize_stress_suite
- [x] 2.3.5 Aba "Stress Testing" no dashboard: seletor, barra por ativo, suite completa
- [x] 2.3.6 21/21 testes unitários passando (99 acumulado)

---

## ⬜ Fase 3 — Arquitetura SaaS (futuro)

### 3.1 Quant Engine como Microserviço
- [ ] 3.1.1 Criar repositório `alphacota-quant` com FastAPI
- [ ] 3.1.2 Expor endpoints: `/score`, `/backtest`, `/simulate`
- [ ] 3.1.3 Dockerizar

### 3.2 API em TypeScript (NestJS)
- [ ] 3.2.1 Criar projeto NestJS
- [ ] 3.2.2 Módulo de autenticação JWT
- [ ] 3.2.3 Módulo de usuários e carteiras
- [ ] 3.2.4 PostgreSQL + migrations

### 3.3 Frontend Moderno
- [ ] 3.3.1 Next.js com charts interativos
- [ ] 3.3.2 Dashboard responsivo

---

## ⬜ Fase 4 — Diferenciação Real (futuro)
- [ ] 4.1 Aprendizado adaptativo de pesos do score engine
- [ ] 4.2 Multi-ativos (Ações, ETFs, FIPs)
- [ ] 4.3 API pública documentada
- [ ] 4.4 Simulador FIRE comparativo por estratégia

---

## 🔍 Melhorias Identificadas na Auditoria

- [ ] M1 — Score engine persistência: salvar alpha_score no SQLite (substituir scores do quant antigo)
- [ ] M2 — Data loader: fallback gracioso para FIIs sem histórico no yfinance
- [ ] M3 — CLI: command `score --ticker MXRF11` para score rápido via terminal
- [ ] M4 — Testes de integração: `allocation_pipeline` com novo score_engine
- [ ] M5 — Dashboard: indicador visual de quais FIIs do universo passaram no screening
