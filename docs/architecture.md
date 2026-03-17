# AlphaCota - Architecture

## System Overview

AlphaCota is a quantitative analysis platform for Brazilian Real Estate Investment Funds (FIIs)
traded on B3. The system combines data engineering, quantitative models, and AI to generate
structured investment recommendations.

## Architecture Layers

```
┌─────────────────────────────────────────────┐
│          Presentation Layer                 │
│  Streamlit Dashboard │ CLI │ FastAPI REST   │
├─────────────────────────────────────────────┤
│          Service Layer                      │
│  AllocationPipeline │ Simulador │ Explain   │
│  PortfolioService │ RebalanceEngine         │
├─────────────────────────────────────────────┤
│          Core Engines (Pure Functions)      │
│  Backtest │ Score │ Markowitz │ Correlation │
│  Stress │ Macro │ Momentum │ Cluster       │
│  FIRE │ Risk │ Report │ Decision           │
│  Portfolio │ Income │ Position │ SmartAporte│
├─────────────────────────────────────────────┤
│          Data Layer                         │
│  DataBridge │ DataLoader │ Universe         │
│  FundamentalsScraper                        │
├─────────────────────────────────────────────┤
│          Infrastructure                     │
│  SQLite (database.py) │ Schema (SQL)        │
└─────────────────────────────────────────────┘
```

## Design Principles

1. **Defensive Imports** — Every external dependency is wrapped in `try/except ImportError`
   with a `HAS_*` flag, enabling full offline operation with synthetic data fallbacks.

2. **Pure Functions** — All `core/` modules use module-level functions (no classes except
   dataclasses). Functions have explicit typed parameters and docstrings.

3. **Zero Heavy ML Dependencies** — K-Means, Markowitz optimization, and Pearson correlation
   are implemented from scratch using Python `math` and `statistics` stdlib.

4. **Multi-tier Fallback** — Data sources follow a cascade: real API data -> cached data ->
   synthetic data with sector-specific Gaussian parameters.

5. **SQLite Everywhere** — Three separate databases for different concerns:
   - `alphacota.db` — User portfolio and snapshots
   - `alphacota_fundamentals.db` — Scraper cache (24h TTL)
   - `data/macro/*.csv` — BCB macro data cache

## External Integrations

| Service | Library | Usage |
|---------|---------|-------|
| Yahoo Finance | `yfinance` | Price and dividend history (B3 tickers via `.SA` suffix) |
| Groq Cloud | `groq` | Llama-3.3-70B for market sentiment analysis |
| Banco Central (BCB) | `python-bcb` | Selic, CDI, IPCA macro series |
| Status Invest | `requests` + `bs4` | FII fundamentals scraping |
| Google News | `feedparser` | News headlines for AI analysis |

## Data Flow

```
Yahoo Finance / BCB / Status Invest
        │
   data/data_loader.py ──→ CSV cache (per ticker)
        │
   data/data_bridge.py ──→ Fallback logic + synthetic data
        │
   core/* engines ──→ Pure quantitative calculations
        │
   services/* ──→ Orchestration + Monte Carlo simulations
        │
   frontend/dashboard.py ──→ Streamlit UI
   api/main.py ──→ REST API (FastAPI)
   cli.py ──→ Command line interface
```

## Entry Points

| Entry Point | Command | Purpose |
|-------------|---------|---------|
| Dashboard | `streamlit run frontend/dashboard.py` | Main interactive UI |
| API | `uvicorn api.main:app` | REST API server |
| CLI | `python cli.py <command>` | Command line tools |

## Database Schema

4 tables in `alphacota.db`:
- `users` — Authentication (email, hashed password)
- `operations` — Buy/sell transactions
- `proventos` — Dividend records
- `portfolio_snapshots` — Historical portfolio state
