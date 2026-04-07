# AlphaCota — Intelligent Portfolio Engine for FIIs

AlphaCota e um sistema de analise quantitativa e inteligencia financeira para **Fundos de Investimento Imobiliario (FIIs)** da B3. Combina engenharia de dados, modelos quantitativos e IA (Llama 3 via Groq) para gerar recomendacoes estruturadas de investimento.

## Funcionalidades

- **Market Scanner** — Varredura automatica de FIIs com indicadores fundamentais e AlphaScore
- **Alpha Score** — Modelo de pontuacao proprio (income 40%, valuation 25%, risk 20%, growth 15%)
- **Backtest Engine** — Simulacao historica com aportes mensais e reinvestimento de dividendos
- **Markowitz Optimizer** — Fronteira eficiente via Monte Carlo (Max Sharpe, Min Vol)
- **Correlation & Risk** — Matriz de correlacao, HHI, Diversification Ratio
- **Stress Testing** — 7 cenarios pre-definidos com choques setoriais diferenciados
- **Macro Integration** — Dados do BCB (Selic, CDI, IPCA) e premio de risco FII
- **Momentum Ranking** — Ranking multi-periodo (1m, 3m, 6m, 12m)
- **K-Means Clustering** — Agrupamento de FIIs por perfil de risco/retorno (pure Python)
- **FIRE Projection** — Simulador de independencia financeira
- **AI Insights** — Analise de sentimento via Groq/Llama 3.3-70B + RAG (Vectorizer)
- **Monte Carlo** — 500 caminhos estocasticos para projecao de carteira
- **MCP Server** — 19 tools para integracao com Claude, Cursor, Cline e outras IAs

## Arquitetura

```
React Frontend (Vite + shadcn/ui)  ←→  FastAPI REST API (21 endpoints)
                                            |
                                    services/ (orquestracao)
                                            |
                                    core/ (29 motores quantitativos puros)
                                            |
                                    data/ (yfinance, BCB, StatusInvest, FundsExplorer, CVM/B3, RSS, Vectorizer)
                                            |
                                    infra/ (SQLite)
```

Detalhes em [docs/architecture.md](docs/architecture.md) e [docs/modules.md](docs/modules.md).

## Tech Stack

**Backend:**
- Python 3.11+ / FastAPI (REST API com JWT auth)
- SQLite (persistencia local)
- yfinance (precos e dividendos)
- python-bcb (Selic, CDI, IPCA do Banco Central)
- BeautifulSoup4 (scraping StatusInvest, FundsExplorer)
- Groq API (Llama 3.3-70B para insights IA)
- Vectorizer (semantic search / RAG)

**Frontend:**
- React 18 + TypeScript + Vite 5
- shadcn/ui + Tailwind CSS
- TanStack Query (data fetching)
- Recharts (graficos)
- React Router v6

**MCP Server:**
- 19 tools para analise de FIIs via protocolo MCP
- Compativel com Claude Code, Cursor, Cline, Claude Desktop

## Quick Start

```bash
# 1. Clone
git clone git@github.com:rusthp/AlphaCota.git
cd AlphaCota

# 2. Instale dependencias
pip install -r requirements.txt
cd frontend && npm install && cd ..

# 3. Configure variaveis de ambiente
cp .env.example .env
# Edite .env com sua GROQ_API_KEY

# 4. Rode (backend + frontend com um comando)
python start.py
# Acesse http://localhost:8080
```

## Entry Points

| Comando | Descricao |
|---------|-----------|
| `python start.py` | Backend (8000) + Frontend (8080) |
| `uvicorn api.main:app --reload` | Apenas API REST |
| `cd frontend && npm run dev` | Apenas frontend |
| `python -m alphacota_mcp.financial_data` | MCP Server (para Claude/Cursor) |

## MCP Server

O AlphaCota inclui um servidor MCP com 19 tools para analise de FIIs. Qualquer ferramenta que suporte MCP pode usar.

**Configuracao** (adicione ao config da sua ferramenta):

```json
{
  "mcpServers": {
    "alphacota-financial-data": {
      "command": "python",
      "args": ["-m", "alphacota_mcp.financial_data.server"],
      "cwd": "/path/to/alphacota"
    }
  }
}
```

**Tools disponiveis:**

| Categoria | Tools |
|-----------|-------|
| Market | `get_fii_price`, `get_fii_detail`, `get_scanner` |
| Macro | `get_macro_snapshot`, `get_selic`, `get_ipca` |
| Screening | `find_undervalued_fiis`, `find_high_dividend_fiis`, `scan_opportunities` |
| Analysis | `run_correlation`, `run_momentum`, `run_stress`, `run_clusters` |
| News | `get_fii_news`, `get_market_news`, `list_news_sources` |
| AI | `analyze_fii_sentiment`, `generate_fii_report`, `generate_daily_market_report` |

## Estrutura do Projeto

```
alphacota/
├── core/               # 29 motores quantitativos puros
├── services/           # Camada de orquestracao
├── data/               # Integracao (yfinance, BCB, scrapers, vectorizer, RSS)
├── api/                # FastAPI REST (21 endpoints)
├── frontend/           # React + Vite + shadcn/ui
├── alphacota_mcp/      # MCP Server (19 tools)
├── infra/              # SQLite e schema
├── tests/              # 581 testes automatizados (pytest)
├── scripts/            # Scripts utilitarios
├── docs/               # Documentacao tecnica
└── cota_ai/            # Prototipo legado (deprecated)
```

## Desenvolvimento

```bash
# Instale dependencias de desenvolvimento
pip install -r requirements-dev.txt

# Rode os testes
pytest

# Com cobertura
pytest --cov=core --cov=data --cov=services --cov=api --cov=infra

# Lint e formatacao
ruff check .
black --check .
```

---

*Transformando dados de mercado em decisoes de investimento estruturadas.*
