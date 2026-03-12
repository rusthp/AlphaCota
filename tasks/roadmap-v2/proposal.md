# Proposal: AlphaCota v2 — Roadmap Estratégico Atualizado

## Por quê

O AlphaCota já possui um motor quantitativo sólido: score engine com fórmula matemática explícita, backtest engine, correlação, Markowitz, stress testing, momentum, clustering e macro engine. São **99 testes unitários passando** e 6 abas no dashboard.

Porém, o motor roda com **dados hipotéticos**. Os engines funcionam perfeitamente como matemática, mas ninguém alimenta dados fundamentalistas reais (P/VP, vacância, dívida/PL). O dashboard usa tickers hardcoded e séries sintéticas no backtest. Isso significa que as análises são demonstrações, não recomendações reais.

**O próximo passo não é mais código quant — é dados reais.**

## O que Muda

O roadmap agora tem 6 fases priorizadas pelo impacto:

1. ~~Quant Foundation~~ ✅ FEITO
2. ~~Risk & Optimization~~ ✅ FEITO
3. **Dados Reais & Pipeline Integrado** ← PRÓXIMO
4. Robustez & Qualidade
5. Diferenciação & Inteligência
6. SaaS & Sistema de Usuários ← POR ÚLTIMO

---

## Fase 3 — Dados Reais & Pipeline Integrado (PRIORIDADE MÁXIMA)

### Problema
- `score_engine` recebe `dividend_yield`, `pvp`, `debt_ratio`, `vacancy_rate` mas nenhum módulo busca esses dados automaticamente
- `data_bridge.py` só busca preços/retornos via yfinance, não dados fundamentalistas
- Dashboard usa tickers hardcoded e `random.gauss()` no backtest
- `run_allocation_pipeline()` existe e funciona mas o dashboard não o chama

### Solução

**3.1 — Coletor de Dados Fundamentalistas** (`data/fundamentals_scraper.py`)
- Scraper para Status Invest ou FundsExplorer
- Coleta: DY real, P/VP, vacância, dívida/PL, liquidez diária
- Cache em SQLite com TTL de 24h
- Fallback: último dado em cache se scraping falhar

**3.2 — Universo Dinâmico** (`data/universe.py`)
- Lista dos ~100 FIIs do IFIX com classificação setorial automática
- Substituir tickers hardcoded do dashboard
- Filtro de liquidez mínima (R$ 500k/dia)

**3.3 — Backtest Real**
- Eliminar dados sintéticos do dashboard
- Auto-bootstrap de dados na primeira execução
- Badge visual "dados reais" vs "sintético"

**3.4 — Pipeline no Dashboard**
- Nova aba "🤖 Análise Completa" usando `run_allocation_pipeline()`
- Alimentar com dados do scraper + data_bridge
- Histórico de snapshots com evolução temporal

---

## Fase 4 — Robustez & Qualidade

- Fallback gracioso para FIIs sem histórico
- Validação de inputs em todos os engines
- Logging estruturado
- CLI completo (`score`, `universe`, `pipeline`, `report`)
- Cobertura de testes 95%+ no `core/`

---

## Fase 5 — Diferenciação & Inteligência

- Walk-forward optimization de pesos do score engine
- Multi-ativos (Ações, ETFs)
- Simulador FIRE com Monte Carlo e inflação real
- Relatórios profissionais com quantstats + PDF

---

## Fase 6 — Arquitetura SaaS & Usuários (POR ÚLTIMO)

- FastAPI microserviço para o quant engine
- NestJS + PostgreSQL + JWT Auth
- Next.js com charts interativos
- Sistema de billing (Stripe)
- API pública documentada

---

## Referências Técnicas

| Categoria | Repositório | Uso |
|-----------|-------------|-----|
| Scraping | [Status Invest](https://statusinvest.com.br) | Dados fundamentalistas de FIIs |
| Scraping | [FundsExplorer](https://www.fundsexplorer.com.br) | Alternativa p/ dados de FIIs |
| Backtest | [Backtrader](https://github.com/mementum/backtrader) | Referência de arquitetura |
| Otimização | [PyPortfolioOpt](https://github.com/robertmartin8/PyPortfolioOpt) | Referência (usamos implementation própria) |
| SaaS | [bulletproof-nodejs](https://github.com/santiq/bulletproof-nodejs) | Arquitetura para Fase 6 |

---

## Impacto Esperado por Fase

| Fase | De | Para |
|------|----|------|
| 3 | Motor com dados fake | Análises com dados reais do mercado |
| 4 | Código frágil | Motor robusto para uso diário |
| 5 | Pesos fixos, só FIIs | Otimização adaptativa, multi-ativos |
| 6 | Ferramenta local | Produto SaaS com usuários |
