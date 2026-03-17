# AlphaCota — Intelligent Portfolio Engine for FIIs

AlphaCota e um sistema de analise quantitativa e inteligencia financeira para **Fundos de Investimento Imobiliario (FIIs)** da B3. Combina engenharia de dados, modelos quantitativos e IA (Llama 3 via Groq) para gerar recomendacoes estruturadas de investimento.

## Funcionalidades

- **Market Scanner** — Varredura automatica de FIIs listados na B3 com indicadores fundamentais
- **Alpha Score** — Modelo de pontuacao proprio (income, valuation, risk, growth)
- **Backtest Engine** — Simulacao historica com aportes mensais e reinvestimento de dividendos
- **Markowitz Optimizer** — Fronteira eficiente via Monte Carlo (Max Sharpe, Min Vol)
- **Correlation & Risk** — Matriz de correlacao, HHI, Diversification Ratio
- **Stress Testing** — 7 cenarios pre-definidos com choques setoriais diferenciados
- **Macro Integration** — Dados do BCB (Selic, CDI, IPCA) e premio de risco FII
- **Momentum Ranking** — Ranking multi-periodo (1m, 3m, 6m, 12m)
- **K-Means Clustering** — Agrupamento de FIIs por perfil de risco/retorno (pure Python)
- **FIRE Projection** — Simulador de independencia financeira
- **AI Insights** — Analise de sentimento via Groq/Llama 3.3-70B com cache
- **Monte Carlo** — 500 caminhos estocasticos para projecao de carteira

## Arquitetura

```
Streamlit Dashboard / CLI / FastAPI REST
              |
     services/ (orquestracao)
              |
     core/ (motores quantitativos puros)
              |
     data/ (yfinance, BCB, Status Invest)
              |
     infra/ (SQLite)
```

Detalhes em [docs/architecture.md](docs/architecture.md) e [docs/modules.md](docs/modules.md).

## Tech Stack

- **Python 3.11+**
- **Streamlit** (Dashboard interativo)
- **FastAPI** (REST API com JWT auth)
- **SQLite** (Persistencia local)
- **yfinance** (Dados de mercado)
- **Groq API** (Llama 3.3-70B para insights IA)
- **python-bcb** (Dados macroeconomicos do Banco Central)
- **BeautifulSoup4** (Scraping de fundamentos)

## Quick Start

```bash
# 1. Clone
git clone git@github.com:rusthp/AlphaCota.git
cd AlphaCota

# 2. Instale dependencias
pip install -r requirements.txt

# 3. Configure variaveis de ambiente
cp .env.example .env
# Edite .env com sua GROQ_API_KEY

# 4. Rode o dashboard
streamlit run frontend/dashboard.py
```

## Desenvolvimento

```bash
# Instale dependencias de desenvolvimento
pip install -r requirements-dev.txt

# Rode os testes
pytest

# Lint e formatacao
ruff check .
black --check .
mypy .
```

## Entry Points

| Comando | Descricao |
|---------|-----------|
| `streamlit run frontend/dashboard.py` | Dashboard interativo |
| `uvicorn api.main:app --reload` | API REST |
| `python cli.py --help` | Linha de comando |

## Estrutura do Projeto

```
alphacota/
├── core/           # Motores quantitativos (25 modulos)
├── services/       # Camada de orquestracao
├── data/           # Integracao de dados (yfinance, BCB, scraper)
├── frontend/       # Dashboard Streamlit
├── api/            # FastAPI REST
├── infra/          # SQLite e schema
├── tests/          # Testes automatizados (pytest)
├── scripts/        # Scripts utilitarios
├── docs/           # Documentacao tecnica
└── cota_ai/        # Prototipo legado (deprecated)
```

---

*Transformando dados de mercado em decisoes de investimento estruturadas.*
