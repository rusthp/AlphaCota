# AlphaCota - Module Reference

## core/ — Quantitative Engines

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `backtest_engine.py` | Portfolio backtesting with monthly contributions | `run_backtest()`, `compare_against_benchmark()`, `format_metrics_report()` |
| `score_engine.py` | Alpha Score model for FIIs (DY, P/VP, risk, growth) | `calculate_alpha_score()`, `rank_fiis()` |
| `quant_engine.py` | Quality scoring for stocks (Altman Z, momentum) | `calculate_quality_score()`, `calculate_altman_z()`, `evaluate_company()` |
| `markowitz_engine.py` | Mean-variance optimization (Monte Carlo frontier) | `simulate_portfolio_frontier()`, `find_max_sharpe()`, `find_min_volatility()` |
| `correlation_engine.py` | Correlation matrix and concentration risk | `build_correlation_matrix()`, `calculate_herfindahl_index()`, `analyse_portfolio_risk()` |
| `stress_engine.py` | 7 pre-defined stress scenarios | `apply_stress_scenario()`, `run_stress_suite()` |
| `macro_engine.py` | BCB macro data (Selic, CDI, IPCA) | `get_macro_snapshot()`, `calcular_premio_risco_fii()` |
| `momentum_engine.py` | Multi-period momentum ranking | `momentum_score()`, `rank_by_momentum()`, `top_momentum()` |
| `cluster_engine.py` | K-Means clustering (pure Python) | `cluster_portfolio()`, `suggest_diversification()` |
| `fire_engine.py` | FIRE projection (financial independence) | `calculate_years_to_fire()`, `calculate_required_capital()` |
| `risk_engine.py` | Volatility calculation | `calculate_volatility()` |
| `report_engine.py` | HTML tearsheet and CSV export | `generate_html_tearsheet()`, `generate_portfolio_csv_download()` |
| `decision_engine.py` | Master report orchestrator | `generate_decision_report()` |
| `portfolio_engine.py` | Allocation and rebalance suggestions | `calculate_portfolio_allocation()`, `calculate_rebalance_suggestion()` |
| `position_engine.py` | Position P&L calculations | Position tracking and profit/loss |
| `income_engine.py` | Dividend income calculations | Yield and income projections |
| `profile_allocator.py` | Risk profile target allocations | `getTargetAllocation()` — conservador/moderado/agressivo |
| `class_rebalancer.py` | Asset class rebalancing | `calculateRebalanceSuggestion()` |
| `smart_aporte.py` | Intelligent contribution allocation | `generateAporteSuggestion()` |
| `state_repository.py` | SQLite persistence for snapshots | Save/load allocation snapshots and scores |
| `security.py` | JWT authentication and password hashing | `create_access_token()`, `decode_access_token()`, `hash_password()` |
| `config.py` | Application settings (pydantic) | `Settings` class with env vars |
| `logger.py` | Centralized logging | Logger configuration |

## services/ — Orchestration

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `allocation_pipeline.py` | Full quantamental pipeline (7 stages) | `build_elite_universe()`, `optimize_with_constraints()` |
| `simulador_service.py` | Monte Carlo and deterministic simulations | `simulate_monte_carlo()`, `simulate_12_months()`, `compare_profiles_under_scenario()` |
| `portfolio_service.py` | Master cycle orchestrator | `run_full_cycle()` |
| `rebalance_engine.py` | Drift detection and rebalance triggers | `calculate_weight_drift()`, `should_rebalance()` |
| `explain_engine.py` | Deterministic audit trail for decisions | `generate_portfolio_explanation()` |

## data/ — Data Layer

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `data_bridge.py` | Integration bridge with multi-tier fallback | `load_returns()`, `load_returns_bulk()`, `build_portfolio_from_tickers()` |
| `data_loader.py` | yfinance wrapper with CSV caching | `fetch_prices()`, `fetch_dividends()`, `calculate_monthly_returns()` |
| `universe.py` | FII universe registry (56+ funds, 11 sectors) | `get_universe()`, `get_tickers()`, `get_sector_map()` |
| `fundamentals_scraper.py` | Status Invest scraper with SQLite cache | `fetch_fundamentals()`, `fetch_fundamentals_bulk()` |

## api/ — REST API

| Module | Purpose | Endpoints |
|--------|---------|-----------|
| `main.py` | FastAPI application | `GET /health`, `POST /register`, `POST /login`, `POST /report`, `GET /history` |

## infra/ — Infrastructure

| Module | Purpose |
|--------|---------|
| `database.py` | SQLite schema and CRUD operations (users, operations, proventos, snapshots) |
| `advanced_schema.sql` | SQL schema definition |

## frontend/ — UI

| Module | Purpose |
|--------|---------|
| `dashboard.py` | Streamlit dashboard with 6+ analysis tabs |

## FII Universe Sectors

Logistica, Shopping, Lajes Corporativas, Papel (CRI), Fundo de Fundos, Hibrido,
Agro, Saude, Residencial, Educacional, Hotel.
