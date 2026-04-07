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

### 1.4 Infraestrutura
- [x] 1.4.1 Criar `requirements.txt` com todas as dependências
- [x] 1.4.2 Adicionar comando `backtest` ao `cli.py`
- [x] 1.4.3 Integrar backtest no `frontend/dashboard.py` (nova aba)

---

## ✅ Fase 2 — Risk & Optimization (CONCLUÍDA)

- [x] Correlation Engine (25 testes)
- [x] Markowitz + Fronteira Eficiente (26 testes)
- [x] Stress Testing com 7 cenários (21 testes)
- [x] Dados Reais — python-bcb + Macro (Selic, CDI, IPCA)
- [x] ML — Clustering K-Means + Momentum 1/3/6/12m

---

## ✅ Fase 3 — React + Dados Reais (CONCLUÍDA)

- [x] Frontend React 18 + Vite + TypeScript + Tailwind + shadcn/ui
- [x] 9 páginas: Scanner, Carteira, Simulador, Macro, Momentum, Stress, Correlação, Clusters, AI Insights
- [x] API REST FastAPI com 21 endpoints
- [x] Pipeline de dados reais: StatusInvest + FundsExplorer + yfinance + BCB
- [x] 40 FIIs no universo (IFIX), preços e dividendos reais
- [x] MCP Server com 19 ferramentas + vectorizer indexado (128 arquivos)
- [x] `.env` + Groq API configurados (sentimento de notícias)
- [x] Calendário de Dividendos: `dividend_calendar.py` + página React + endpoint API
- [x] Combobox de busca de FIIs com autocomplete (ticker + nome + setor)
- [x] Histórico de preços e dividendos 24M via yfinance
- [x] Informações do Fundo enriquecidas (patrimônio, cotas emitidas, gestora)
- [x] Seletor de período nos gráficos: 3M / 6M / 1A / 2A

---

## ✅ Fase 4 — Cobertura de Testes (CONCLUÍDA)

- [x] **98.50% cobertura total** — 959 testes passando
- [x] CI passa com `--cov-fail-under=95`
- [x] `alphacota_mcp/` → 97.94% | `cli.py` → 99%

---

## 🔄 Fase 5 — Qualidade de Dados (CRÍTICO — PRÓXIMO)

> **Problema central**: ~35-40% dos inputs do AlphaScore são hardcoded ou sintéticos,
> comprometendo a confiabilidade das recomendações.

### 5.1 Dados Hardcoded a Corrigir
- [x] 5.1.1 **`debt_ratio`**: removido fallback 0.3 — agora retorna `None` (sem dado real); score exclui a dimensão quando `None`
- [x] 5.1.2 **`vacancy_rate`**: removido fallback 0.05 — agora retorna `None`; score exclui a dimensão quando `None`
- [x] 5.1.3 **`last_dividend`**: removido fallback 0.0 — agora retorna `None` quando não encontrado no scraper
- [x] 5.1.4 **`dividend_consistency`**: fallback 0.5 removido — retorna `None` quando histórico CSV indisponível
- [x] 5.1.5 **`revenue_growth_12m`** / **`earnings_growth_12m`**: proxy via crescimento de dividendos (CSV histórico) — validado e ativo

### 5.2 Badge de Confiança no Score ✅ CONCLUÍDO
- [x] 5.2.1 Calcular `data_confidence` (0-100) por FII (5 dimensões × 20pts)
- [x] 5.2.2 Badge no FIIDetailPage: Alta (≥80) / Média (50-79) / Baixa (<50) com cores
- [x] 5.2.3 Coluna CONF no Scanner com ícones ShieldCheck/Shield/ShieldAlert + tooltip

### 5.3 Filtros de Qualidade Mínima no Scanner ✅ CONCLUÍDO
- [x] 5.3.1 FIIs com liquidez < R$ 500k/dia movidos para o fim do ranking (`low_liquidity: true`)
- [x] 5.3.2 Flag `dividend_trap: true` quando DY > 20% — badge ⚠ no ticker
- [x] 5.3.3 Flag `pvp_outlier: true` quando PVP > 2.0 ou < 0.5 — valor destacado em amarelo no Scanner

---

## 🔄 Fase 6 — Features de Usuário (ALTA PRIORIDADE)

### 6.1 Comparador de FIIs ⭐ ✅ CONCLUÍDO

- [x] 6.1.1 Nova página `ComparePage.tsx` acessível pelo menu
- [x] 6.1.2 Selecionar 2-5 FIIs via combobox
- [x] 6.1.3 Tabela comparativa: Score, DY, PVP, Vacância, Liquidez, Patrimônio, Cap Rate, Volatilidade — destaque automático melhor valor
- [x] 6.1.4 Gráfico radar (spider chart) com 6 dimensões por FII
- [x] 6.1.5 Gráfico de linhas sobrepostas: histórico de preços 12M
- [x] 6.1.6 Botão "Adicionar à Carteira" direto da comparação
- [x] 6.1.7 Endpoint `GET /api/fiis/compare?tickers=MXRF11,HGLG11,XPML11`

### 6.2 Watchlist & Alertas
- [x] 6.2.1 Watchlist: listas personalizadas além de "Favoritos" (ex: "Candidatos", "Monitorando")
- [x] 6.2.2 Persistência local (localStorage) das listas + sync backend opcional
- [x] 6.2.3 Alerta de queda de score: notificação quando score cai > 10pts
- [x] 6.2.4 Badge ex-dividendo no Scanner (CalendarClock + dias até pagamento)
- [x] 6.2.5 Banner na PortfolioPage com próximos pagamentos (30 dias)

### 6.3 Assistente de Rebalanceamento ✅ CONCLUÍDO
- [x] 6.3.1 Card expansível "Sugerir Rebalanceamento" na PortfolioPage
- [x] 6.3.2 Inputs de alocação-alvo por setor com validação de soma = 100%
- [x] 6.3.3 Cálculo de desvios atual vs alvo com sugestões de compra
- [x] 6.3.4 Avisos de setores com sobrepeso (overweight)
- [x] 6.3.5 Campo de aporte: distribui capital proporcionalmente entre setores deficitários
- [x] 6.3.6 Botão "Adicionar à carteira" pré-preenche o formulário e faz scroll

### 6.4 Simulador FIRE Melhorado
- [x] 6.4.1 Slider de inflação IPCA + linhas de patrimônio nominal vs real no gráfico
- [x] 6.4.2 Modelar imposto: FIIs são isentos de IR para PF em fundos com > 50 cotistas (Adicionado explicativo no simulador)
- [x] 6.4.3 Cenários: Conservador (7%) / Moderado (9.5%) / Agressivo (12%) com presets rápidos
- [x] 6.4.4 Modo FIRE: entrada = renda desejada → saída = capital necessário + anos até FIRE
- [x] 6.4.5 Monte Carlo no FIRE (usar `core/markowitz_engine.py` para variância)

---

## 🔄 Fase 7 — Calendário de Distribuição (PARCIALMENTE FEITO)

### ✅ Feito
- [x] `data/dividend_calendar.py` — histórico + estimativas futuras
- [x] `GET /api/dividends/calendar` — eventos por mês
- [x] `GET /api/dividends/portfolio-income` — projeção de renda com quantidade de cotas
- [x] `DividendCalendarPage.tsx` — grade mensal com chips por setor + legenda + sidebar

### ⬜ Pendente
- [x] 7.1 Timeline anual: gráfico de barras mensais de renda projetada (12M) na sidebar do calendário
- [x] 7.2 Botão "Minha Carteira" no calendário: filtra eventos pelos FIIs do usuário
- [x] 7.3 Export CSV e .ICS (Google Calendar) com os eventos do mês
- [x] 7.4 Banner "Próximos pagamentos" na PortfolioPage (próximos 30 dias) — já existia

---

## ⬜ Fase 8 — UX & Polish (MÉDIO PRAZO)

### 8.1 StressPage — Cenários Configuráveis
- [x] 8.1.1 Checkboxes para selecionar quais cenários testar (hoje é fixo)
- [x] 8.1.2 Sliders para intensidade: "Choque de preço: -10% / -20% / -30%"
- [x] 8.1.3 Exportar resultado do stress test como PDF/CSV

### 8.2 AIInsights — Análise em Massa
- [x] 8.2.1 Botão "Analisar toda carteira": roda sentimento para todos os FIIs da carteira
- [x] 8.2.2 Dashboard de sentimento: semáforo por FII (POSITIVO / NEUTRO / NEGATIVO)
- [x] 8.2.3 Cache Redis ou SQLite de sentimentos (TTL 6h) para não gastar API a cada carregamento
- [x] 8.2.4 Tendência de sentimento: POSITIVO esta semana mas NEGATIVO mês passado = sinal de reversão

### 8.3 Scanner — Melhorias
- [x] 8.3.1 Colunas configuráveis (mostrar/ocultar colunas via dropdown)
- [x] 8.3.2 Filtro de score mínimo com input numérico
- [x] 8.3.3 Filtro de DY mínimo e máximo com inputs numéricos
- [x] 8.3.4 Highlight dos FIIs da carteira no Scanner (fundo azul + badge "carteira")
- [x] 8.3.5 Exportar Scanner como CSV (botão no header)

### 8.4 FIIDetailPage — Melhorias
- [x] 8.4.1 Adicionar aba "Análise IA" com botão de análise Groq in-page
- [x] 8.4.2 Botão "Comparar" no header da FIIDetailPage → abre ComparePage com o FII pré-selecionado
- [x] 8.4.3 Histórico do score ao longo do tempo (requer SQLite de snapshots)
- [x] 8.4.4 Banner de próximo ex-dividendo na FIIDetailPage (ex-date, pay-date, valor/cota)

### 8.5 Temas & Acessibilidade
- [x] 8.5.1 Modo claro / escuro (toggle)
- [x] 8.5.2 Fonte escalável (configuração de densidade)
- [x] 8.5.3 Atalhos de teclado: `S` → Scanner, `C` → Carteira, `?` → Help

---

## ✅ Fase 9 — Exportação & Relatórios (CONCLUÍDA)

- [x] 9.1 Relatório mensal PDF da carteira (patrimônio, dividendos, performance vs IFIX)
- [x] 9.2 Export CSV da carteira: ticker, segmento, qtd, PM, preço atual, custo, valor, retorno%, DY%, div/mês
- [x] 9.3 Resumo IRPF anual: dividendos recebidos por FII (isentos para PF)
- [x] 9.4 Relatório de rebalanceamento: o que comprar/vender para atingir alocação-alvo
- [x] 9.5 Integrar `quantstats` para tearsheet de portfolio completo (Sharpe, drawdown, etc.)

---

## ⬜ Fase 10 — SaaS & Escala (FUTURO DISTANTE)

- [ ] 10.1 Autenticação social (Google OAuth)
- [ ] 10.2 Persistência server-side de carteiras (PostgreSQL)
- [ ] 10.3 Múltiplos portfólios por usuário
- [ ] 10.4 Link compartilhável: "Ver minha carteira (somente leitura)"
- [ ] 10.5 Push notifications (ex-dividendo, score caiu)
- [ ] 10.6 Next.js + TradingView Lightweight Charts
- [ ] 10.7 Billing (Stripe) para tier premium

---

## 📊 Resumo de Progresso

| Fase | Status | Descrição | Testes |
|------|--------|-----------|--------|
| 1 — Quant Foundation | ✅ 100% | Backtest, Score, Data Loader | 27 |
| 2 — Risk & Optimization | ✅ 100% | Correlation, Markowitz, Stress, ML | 72 |
| 3 — React + Dados Reais | ✅ 98% | Frontend, FastAPI, Pipeline, Calendário, Combobox, Gráficos 24M | ~400 |
| 4 — Cobertura de Testes | ✅ 100% | **98.50%, 959 testes** | 959 |
| 5 — Qualidade de Dados | 🔄 85% | Badge ✅, flags ✅, None em vez de fallbacks ✅, debt_ratio CVM real pendente | — |
| 6 — Features de Usuário | 🔄 75% | Comparador ✅, FIRE ✅, Rebalanceamento ✅, Watchlist pendente | — |
| 7 — Calendário | ✅ 100% | Timeline ✅, filtro carteira ✅, export CSV/ICS ✅, banner PortfolioPage ✅ | — |
| 8 — UX & Polish | 🔄 40% | Scanner ✅, FIIDetail ✅, highlight carteira ✅, próx.dividendo ✅, Stress/AI/dark mode pendente | — |
| 9 — Exportação | 🔄 20% | Export CSV carteira ✅, PDF/IRPF/quantstats pendente | — |
| 10 — SaaS | ⬜ 0% | Multi-usuário, billing, Next.js | — |
| **Total** | **~62%** | | **959** |

---

## 🎯 Próximo Sprint Recomendado

**Sprint C — Comparador (1-2 dias):** ⭐ maior impacto de UX
1. `ComparePage.tsx` com tabela + radar chart
2. Endpoint `/api/fiis/compare`
3. Gráfico de preços sobrepostos

**Sprint D — Qualidade de Dados (2-3 dias):** maior impacto na confiabilidade
1. Buscar `debt_ratio` real via CVM
2. Badge de confiança no FIIDetailPage e Scanner
3. Aceitar `null` em vez de fallbacks hardcoded

**Sprint E — Alertas de Dividendo (1 dia):**
1. Badge "Ex-div em X dias" no Scanner
2. Banner na PortfolioPage com próximos pagamentos
