# Proposal: AlphaCota v2 — Roadmap Estratégico

## Por quê

O AlphaCota hoje possui um motor promissor: score engine, simulação de bola de neve, perfis de alocação e integração com IA via Groq. Porém, **falta evidência estatística**. Sem um backtest sólido, todas as recomendações do sistema são hipóteses não validadas.

O maior risco atual não é tecnológico — é a ausência de prova de performance. Finanças exige evidência quantitativa. Um dashboard bonito sem backtest é apenas interface.

## O que Muda

Este roadmap transforma o AlphaCota de um sistema de recomendações heurísticas em um **motor quantitativo validado**, capaz de evoluir para SaaS.

---

## Fase 1 — Quant Foundation (0–3 meses)

**Objetivo**: transformar o projeto em motor quantitativo validado.

### 1.1 Backtest Engine
- Novo módulo: `core/backtest_engine.py`
- Simular aportes mensais e rebalanceamentos periódicos
- Comparar performance contra o IFIX
- Métricas obrigatórias: CAGR, Sharpe, Sortino, Max Drawdown, Volatilidade Anual
- **Dependência**: dados históricos de cotação e dividendos

### 1.2 Camada de Dados Históricos
- Estrutura: `data/historical_prices/`, `data/historical_dividends/`, `data/macro/`
- Coletar: histórico de cotação, dividendos, P/VP histórico, vacância quando possível
- Preparar migração futura: SQLite → PostgreSQL

### 1.3 Formalização do Score Engine
- Transformar lógica heurística em modelo matemático explícito:
  ```
  score = (w_valuation × valuation_score) + (w_income × dividend_stability) + (w_risk × risk_factor)
  ```
- Isso permite backtest do próprio score e otimização de pesos futura

---

## Fase 2 — Risk & Optimization (3–6 meses)

**Objetivo**: sair de ranking de FIIs e evoluir para sistema de alocação otimizada.

### 2.1 Correlação entre FIIs
- Novo módulo: `core/correlation_engine.py`
- Gerar matriz de correlação, mapa de concentração por setor e risco sistêmico
- Melhora direta do `class_rebalancer.py`

### 2.2 Otimização de Carteira (Markowitz)
- Integrar `PyPortfolioOpt` (https://github.com/robertmartin8/PyPortfolioOpt)
- Implementar: Mean-Variance Optimization, Monte Carlo de portfólio, fronteira eficiente
- Métricas alvo: Max Sharpe e Min Volatility

### 2.3 Stress Testing
- Simular cenários adversos: alta de juros, queda de mercado, corte de dividendos

---

## Fase 3 — Arquitetura SaaS (6–12 meses)

**Objetivo**: separar o motor matemático do produto comercial.

### 3.1 Quant Engine como Microserviço
- Isolar em `alphacota-quant/` usando FastAPI
- Responsável exclusivamente por: cálculo, score, backtest, simulação

### 3.2 API Principal em TypeScript
- Stack: NestJS + PostgreSQL + JWT Auth
- Responsável por: usuários, carteiras, billing, logs, histórico de recomendações

### 3.3 Frontend Moderno
- Next.js com charts interativos e dashboard responsivo

---

## Fase 4 — Diferenciação Real (12+ meses)

**Objetivo**: tornar o AlphaCota único no mercado brasileiro.

- Aprendizado adaptativo + ajuste automático de pesos
- Multi-ativos (além de FIIs)
- API pública
- Simulador FIRE comparativo por estratégia

---

## Referências Técnicas

| Categoria           | Repositório                                                 | Uso Principal                             |
|---------------------|-------------------------------------------------------------|-------------------------------------------|
| Backtest            | [Backtrader](https://github.com/mementum/backtrader)        | Estudar arquitetura de engine             |
| Backtest            | [Zipline](https://github.com/quantopian/zipline)            | Pipeline de dados e engine de simulação   |
| Otimização          | [PyPortfolioOpt](https://github.com/robertmartin8/PyPortfolioOpt) | Integração direta na Fase 2         |
| Engine Quant        | [QuantConnect Lean](https://github.com/QuantConnect/Lean)   | Referência de arquitetura profissional    |
| RL Financeiro       | [FinRL](https://github.com/AI4Finance-Foundation/FinRL)     | Exploração futura de ML                   |
| SaaS TS             | [bulletproof-nodejs](https://github.com/santiq/bulletproof-nodejs) | Arquitetura limpa para Fase 3      |

---

## Impacto Esperado

| Antes (Hoje)            | Depois (Fase 1)                          |
|-------------------------|------------------------------------------|
| Score heurístico        | Score matemático com pesos explícitos    |
| Simulação sem validação | Backtest contra benchmark (IFIX)         |
| Recomendações subjetivas| Decisões baseadas em CAGR e Sharpe       |
| Motor isolado           | Base para SaaS escalável                 |
