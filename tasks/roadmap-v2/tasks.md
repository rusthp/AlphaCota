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

## ✅ Fase 2 — Risk & Optimization (CONCLUÍDA)

### ✅ 2.1 Correlation Engine
- [x] 2.1.1 Criar `core/correlation_engine.py`
- [x] 2.1.2 Matriz de correlação entre FIIs (Pearson N×N)
- [x] 2.1.3 Concentração setorial com Índice HHI
- [x] 2.1.4 Risco sistêmico: volatilidade de portfólio com correlações, Diversification Ratio
- [x] 2.1.5 `suggest_rebalance_with_correlation` — rebalanceamento ciente de correlação
- [x] 2.1.6 Aba "Risco & Correlação" no dashboard
- [x] 2.1.7 25/25 testes unitários passando (52 acumulado)

### ✅ 2.2 Markowitz + Fronteira Eficiente
- [x] 2.2.1 Criar `core/markowitz_engine.py` (Python puro, sem deps externas)
- [x] 2.2.2 Retorno/volatilidade esperados e volatilidade matricial com correlações
- [x] 2.2.3 Monte Carlo de N portfólios (simulate_portfolio_frontier)
- [x] 2.2.4 Max Sharpe + Min Volatility + Equal Weight como baseline
- [x] 2.2.5 Aba "Markowitz — Fronteira Eficiente" no dashboard
- [x] 2.2.6 26/26 testes unitários passando (78 acumulado)

### ✅ 2.3 Stress Testing
- [x] 2.3.1 Criar `core/stress_engine.py` com 7 cenários pré-definidos
- [x] 2.3.2 Choque diferenciado por setor
- [x] 2.3.3 apply_stress_scenario: impacto R$ e % por ativo
- [x] 2.3.4 run_stress_suite: múltiplos cenários + summarize_stress_suite
- [x] 2.3.5 Aba "Stress Testing" no dashboard
- [x] 2.3.6 21/21 testes unitários passando (99 acumulado)

### ✅ 2.7 Dados Reais — python-bcb + Macro
- [x] 2.7.1 Integrar `python-bcb` para Selic, CDI e IPCA histórico
- [x] 2.7.2 Usar Selic real como `risk_free_rate` no Markowitz e Sharpe
- [x] 2.7.3 Gráfico Selic vs DY na aba Análise Avançada
- [x] 2.7.4 Calcular "Prêmio de risco" real (DY - CDI) por FII

### ✅ 2.8 ML — Clustering e Momentum
- [x] 2.8.1 Criar `core/momentum_engine.py` com ranking 1/3/6/12m
- [x] 2.8.2 Criar `core/cluster_engine.py` com K-Means
- [x] 2.8.3 Aba "Análise Avançada" no dashboard
- [x] 2.8.4 Sugestão de carteira diversificada entre clusters

---

## ✅ Phase 3: Real Data & Integrated Pipeline (Concluído)

> **Prioridade máxima.** O motor quant funciona, mas roda com dados hipotéticos.
> O objetivo é alimentar o sistema com dados reais de mercado.

### 3.1 Coletor de Dados Fundamentalistas
- [x] 3.1.1 Criar `data/fundamentals_scraper.py`
- [x] 3.1.2 Implementar scraping de DY, P/VP, vacância (ex: Status Invest)
- [x] 3.1.3 Adicionar cache local em SQLite (TTL 24h)
- [x] 3.1.4 Implementar fallback (dados sintéticos em caso de falha)
- [ ] 3.1.5 Fontes: Status Invest / FundsExplorer (scraping) ou CSV curado
- [ ] 3.1.6 Cache local em SQLite para evitar requisições repetidas
- [ ] 3.1.7 Fallback gracioso: se scraping falhar, usar último dado em cache
- [ ] 3.1.8 Testes unitários (mocks de HTTP + validação de parsing)

### 3.2 Universo Dinâmico de FIIs
- [x] 3.2.1 Criar `data/universe.py`
- [x] 3.2.2 Gerenciar lista dinâmica de FIIs (IFIX filter)
- [x] 3.2.3 Implementar filtros por setor e liquidez
- [ ] 3.2.4 Substituir tickers hardcoded do dashboard por universo dinâmico
- [ ] 3.2.5 Filtros de liquidez mínima (ex: R$ 500k/dia) para excluir FIIs illíquidos

### 3.3 Backtest com Dados Reais Automático
- [x] 3.3.1 Dashboard carrega dados reais do `data_bridge` automaticamente na aba Backtest
- [x] 3.3.2 Substituir gerador sintético em `dashboard.py` e `data_bridge.py`
- [x] 3.3.3 Garantir que backtest use histórico real via `yfinance`
- [ ] 3.3.4 Auto-bootstrap: baixar dados na primeira execução se cache vazio
- [ ] 3.3.5 Indicador visual: "dados reais" vs "sintético" em cada aba

### 3.4 Pipeline Integrado no Dashboard
- [x] 3.4.1 Criar aba "Análise Completa" no Streamlit
- [x] 3.4.2 Conectar: Universo -> Scraper -> Score -> Otimização -> Explain
- [x] 3.4.3 Exibir relatórios consolidados no front-end
- [ ] 3.4.4 Salvar snapshot no SQLite a cada execução
- [ ] 3.4.5 Mostrar histórico de snapshots (evolução temporal das recomendações)

### 3.5 Testes de Integração
- [ ] 3.5.1 Teste end-to-end do `allocation_pipeline` com dados mock realistas
- [ ] 3.5.2 Teste do fluxo completo: scraper → score → pipeline → persistência
- [ ] 3.5.3 Validar que resultados persistidos podem ser relidos e comparados

---

## ⬜ Fase 4 — Robustez & Qualidade (seguinte)

> **Objetivo:** tornar o motor robusto e confiável para uso diário.

### 4.1 Tratamento de Erros e Edge Cases
- [ ] 4.1.1 Fallback gracioso para FIIs sem histórico no yfinance (M2 do roadmap)
- [ ] 4.1.2 Validação de inputs em todos os engines (NaN, negativos, divisão por zero)
- [ ] 4.1.3 Logging estruturado: substituir `print()` por logger configurável
- [ ] 4.1.4 Rate limiting no scraper para não ser bloqueado

### 4.2 CLI Completo
- [ ] 4.2.1 Comando `score --ticker MXRF11` para score rápido via terminal (M3)
- [ ] 4.2.2 Comando `universe --list` para ver FIIs do universo
- [ ] 4.2.3 Comando `pipeline --profile moderado` para rodar análise completa
- [ ] 4.2.4 Comando `report --format html` para gerar tearsheet

### 4.3 Cobertura de Testes
- [ ] 4.3.1 Testes do `score_engine` (unitário — hoje não tem)
- [ ] 4.3.2 Testes do `allocation_pipeline` (integração — M4)
- [ ] 4.3.3 Testes do `data_bridge` e `data_loader`
- [ ] 4.3.4 Testes do `report_engine`
- [ ] 4.3.5 Meta: 95%+ de cobertura no `core/`

### 4.4 Dashboard: Performance e UX
- [ ] 4.4.1 Indicador de progresso ao buscar dados de múltiplos tickers
- [ ] 4.4.2 Indicador visual de quais FIIs passaram no screening (M5)
- [ ] 4.4.3 Melhorar responsividade mobile do Streamlit

---

## ⬜ Fase 5 — Diferenciação & Inteligência (futuro)

> **Objetivo:** features que tornam o AlphaCota único.

### 5.1 Otimização Adaptativa de Pesos
- [ ] 5.1.1 Backtest automatizado de diferentes configurações de pesos do score engine
- [ ] 5.1.2 Walk-forward optimization: treinar pesos em janela histórica, validar out-of-sample
- [ ] 5.1.3 Dashboard: comparar performance de diferentes configurações de pesos

### 5.2 Multi-Ativos
- [ ] 5.2.1 Expandir score engine para Ações (métricas: ROE, Margem, P/L)
- [ ] 5.2.2 ETFs (tracking error, TER)
- [ ] 5.2.3 Pipeline multi-classe com alocação integrada

### 5.3 Simulador FIRE Avançado
- [ ] 5.3.1 Comparar FIRE por estratégia (conservador vs agressivo vs ótima Markowitz)
- [ ] 5.3.2 Projeção com inflação real (IPCA do macro engine)
- [ ] 5.3.3 Monte Carlo no FIRE (não apenas determinístico)

### 5.4 Relatórios Profissionais
- [ ] 5.4.1 Integrar `quantstats` para tearsheet completo
- [ ] 5.4.2 PDF export com branding AlphaCota
- [ ] 5.4.3 Relatório comparativo mensal automático

---

## ⬜ Fase 6 — Arquitetura SaaS & Sistema de Usuários (último)

> **Objetivo:** transformar de ferramenta local em produto.
> **Pré-requisito:** Fases 3-5 estáveis e validadas.

### 6.1 Quant Engine como Microserviço
- [ ] 6.1.1 Criar repositório `alphacota-quant` com FastAPI
- [ ] 6.1.2 Expor endpoints: `/score`, `/backtest`, `/simulate`, `/pipeline`
- [ ] 6.1.3 Dockerizar com health checks

### 6.2 API em TypeScript (NestJS)
- [ ] 6.2.1 Criar projeto NestJS
- [ ] 6.2.2 Módulo de autenticação JWT
- [ ] 6.2.3 Módulo de usuários e carteiras
- [ ] 6.2.4 PostgreSQL + migrations

### 6.3 Frontend Moderno
- [ ] 6.3.1 Next.js com charts interativos (Recharts / TradingView Lightweight Charts)
- [ ] 6.3.2 Dashboard responsivo
- [ ] 6.3.3 Sistema de billing (Stripe)

### 6.4 API Pública
- [ ] 6.4.1 Documentação OpenAPI para o quant engine
- [ ] 6.4.2 Rate limiting e autenticação API key
- [ ] 6.4.3 Webhooks para alertas de rebalanceamento

---

## 📊 Resumo de Progresso

| Fase | Status | Tarefas | Testes |
|------|--------|---------|--------|
| 1 — Quant Foundation | ✅ 100% | 13/13 | 27 |
| 2 — Risk & Optimization | ✅ 100% | 24/24 | 72 |
| 3 — Dados Reais & Pipeline | ⬜ 0% | 0/17 | — |
| 4 — Robustez & Qualidade | ⬜ 0% | 0/14 | — |
| 5 — Diferenciação | ⬜ 0% | 0/10 | — |
| 6 — SaaS & Usuários | ⬜ 0% | 0/10 | — |
| **Total** | **~43%** | **37/88** | **99** |
