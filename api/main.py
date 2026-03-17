"""
api/main.py

API REST do AlphaCota — serve o frontend React com dados reais.
Endpoints públicos (sem auth): scanner, fii detail, macro, simulate, AI, etc.
Endpoints protegidos (com auth): report, history.
"""

from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional
import os

# --- Services & Engines ---
from services.portfolio_service import run_full_cycle
from services.simulador_service import (
    simulate_12_months,
    simulate_monte_carlo,
)
from infra.database import get_portfolio_snapshots, create_user, get_user_by_email
from core.security import hash_password, verify_password, create_access_token, get_current_user
from core.quant_engine import evaluate_company
from core.macro_engine import get_macro_snapshot
from core.fire_engine import calculate_years_to_fire, calculate_required_capital
from core.momentum_engine import rank_by_momentum
from core.cluster_engine import cluster_portfolio
from core.stress_engine import run_stress_suite
from core.ai_engine import analyze_fii_news
from core.correlation_engine import build_correlation_matrix
from data.universe import get_universe, get_tickers, get_sector_map, get_sectors_summary
from data.fundamentals_scraper import fetch_fundamentals, fetch_fundamentals_bulk
from data.data_bridge import (
    load_returns_bulk,
    load_last_price,
    load_monthly_dividend,
    build_portfolio_from_tickers,
)
from data.news_scraper import fetch_fii_news, fetch_market_news, list_sources

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AlphaCota API",
    description="Motor quantitativo de FIIs — dados reais via yfinance, BCB, StatusInvest",
    version="2.0.0",
)

# CORS — permite o frontend React (Vite dev server) acessar a API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class UserCreate(BaseModel):
    email: str
    password: str


class ReportRequest(BaseModel):
    precos_atuais: dict[str, float]
    alocacao_alvo: dict[str, float]
    aporte_mensal: float
    taxa_anual_esperada: float
    renda_alvo_anual: float


class SimulateRequest(BaseModel):
    tickers: list[str]
    quantities: dict[str, int] = {}
    aporte_mensal: float = 1000.0
    target_allocation: dict[str, float] = {}
    meses: int = 12


class MonteCarloRequest(BaseModel):
    tickers: list[str]
    quantities: dict[str, int] = {}
    aporte_mensal: float = 1000.0
    target_allocation: dict[str, float] = {}
    growth_rates: dict[str, float] = {}
    volatilities: dict[str, float] = {}
    meses: int = 12
    simulacoes: int = 500


class StressRequest(BaseModel):
    tickers: list[str]
    quantities: dict[str, int] = {}
    scenarios: list[str] = []


class CorrelationRequest(BaseModel):
    tickers: list[str]
    start_date: str = "2023-01-01"
    end_date: str = "2025-12-31"


class FireRequest(BaseModel):
    patrimonio_atual: float
    aporte_mensal: float
    taxa_anual: float = 0.09
    renda_alvo_anual: float = 60000.0


class AIAnalyzeRequest(BaseModel):
    ticker: str
    api_key: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth endpoints (existing)
# ---------------------------------------------------------------------------
@app.get("/health")
def health_check():
    return {"status": "ok", "version": "2.0.0"}


@app.post("/register")
def register(user: UserCreate):
    hashed_pwd = hash_password(user.password)
    user_id = create_user(user.email, hashed_pwd)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="E-mail já registrado")
    return {"message": "Usuário registrado com sucesso", "user_id": user_id}


@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = get_user_by_email(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais incorretas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token({"user_id": user["id"]})
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/report")
def generate_report(request: ReportRequest, user_id: int = Depends(get_current_user)):
    report = run_full_cycle(
        user_id=user_id,
        precos_atuais=request.precos_atuais,
        alocacao_alvo=request.alocacao_alvo,
        aporte_mensal=request.aporte_mensal,
        taxa_anual_esperada=request.taxa_anual_esperada,
        renda_alvo_anual=request.renda_alvo_anual,
    )
    return report


@app.get("/history")
def get_history(user_id: int = Depends(get_current_user)):
    return get_portfolio_snapshots(user_id=user_id)


# ---------------------------------------------------------------------------
# Scanner — lista todos os FIIs com score quantitativo e fundamentals reais
# ---------------------------------------------------------------------------
@app.get("/api/scanner")
def scanner(
    sectors: Optional[str] = Query(None, description="Comma-separated sectors filter"),
):
    """Retorna todos os FIIs do universo com fundamentals e alpha score reais."""
    sector_filter = [s.strip() for s in sectors.split(",")] if sectors else None
    universe = get_universe(sectors=sector_filter)
    tickers = [f["ticker"] for f in universe]

    # Bulk fetch fundamentals (cache + scraping)
    fundamentals = fetch_fundamentals_bulk(tickers)
    sector_map = get_sector_map()

    results = []
    for fii in universe:
        ticker = fii["ticker"]
        fund = fundamentals.get(ticker, {})

        # Evaluate quant score
        eval_data = {
            "dividend_yield": fund.get("dividend_yield", 0.08),
            "pvp": fund.get("pvp", 1.0),
            "vacancia": fund.get("vacancia", 0.05),
            "liquidez_diaria": fund.get("liquidez_diaria", 5000000),
        }

        try:
            evaluation = evaluate_company(ticker, eval_data)
            score = evaluation.get("score_final", 0)
        except Exception:
            score = 0

        # Get last price
        try:
            price, _ = load_last_price(ticker)
        except Exception:
            price = fund.get("cotacao", 0)

        results.append({
            "ticker": ticker,
            "name": fii.get("nome", ticker),
            "segment": sector_map.get(ticker, "Outros"),
            "price": round(price, 2),
            "change": 0,  # TODO: calculate from price history
            "dy": round(fund.get("dividend_yield", 0.08) * 100, 2),
            "pvp": round(fund.get("pvp", 1.0), 2),
            "score": round(score, 0),
            "liquidity": fund.get("liquidez_diaria", 0),
            "_source": fund.get("_source", "default"),
        })

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"fiis": results, "total": len(results)}


# ---------------------------------------------------------------------------
# FII Detail — dados completos de um FII específico
# ---------------------------------------------------------------------------
@app.get("/api/fii/{ticker}")
def fii_detail(ticker: str):
    """Retorna detalhes completos de um FII: fundamentals, preço, dividendos, score."""
    ticker = ticker.upper()
    fund = fetch_fundamentals(ticker)

    try:
        price, price_source = load_last_price(ticker)
    except Exception:
        price, price_source = 0, "unavailable"

    try:
        dividend, div_source = load_monthly_dividend(ticker)
    except Exception:
        dividend, div_source = 0, "unavailable"

    eval_data = {
        "dividend_yield": fund.get("dividend_yield", 0.08),
        "pvp": fund.get("pvp", 1.0),
        "vacancia": fund.get("vacancia", 0.05),
        "liquidez_diaria": fund.get("liquidez_diaria", 5000000),
    }
    try:
        evaluation = evaluate_company(ticker, eval_data)
    except Exception:
        evaluation = {}

    sector_map = get_sector_map()

    return {
        "ticker": ticker,
        "segment": sector_map.get(ticker, "Outros"),
        "price": round(price, 2),
        "price_source": price_source,
        "dividend_monthly": round(dividend, 4),
        "dividend_source": div_source,
        "fundamentals": fund,
        "evaluation": evaluation,
    }


# ---------------------------------------------------------------------------
# Universe — lista de tickers e setores
# ---------------------------------------------------------------------------
@app.get("/api/universe")
def universe_list(sectors: Optional[str] = None):
    sector_filter = [s.strip() for s in sectors.split(",")] if sectors else None
    return {
        "fiis": get_universe(sectors=sector_filter),
        "sectors": get_sectors_summary(),
    }


# ---------------------------------------------------------------------------
# Macro — snapshot macroeconômico (Selic, CDI, IPCA)
# ---------------------------------------------------------------------------
@app.get("/api/macro")
def macro_snapshot():
    """Retorna snapshot macro atual: Selic, CDI, IPCA do BCB."""
    return get_macro_snapshot()


# ---------------------------------------------------------------------------
# Correlation — matriz de correlação entre FIIs
# ---------------------------------------------------------------------------
@app.post("/api/correlation")
def correlation(req: CorrelationRequest):
    """Calcula matriz de correlação e análise de risco do portfólio."""
    return_series, sources = load_returns_bulk(req.tickers, req.start_date, req.end_date)

    # Filter tickers with enough data
    valid_tickers = [t for t in req.tickers if len(return_series.get(t, [])) >= 3]
    if len(valid_tickers) < 2:
        raise HTTPException(status_code=400, detail="Dados insuficientes para correlação")

    matrix = build_correlation_matrix(valid_tickers, return_series)
    return {
        "tickers": valid_tickers,
        "matrix": matrix,
        "sources": sources,
    }


# ---------------------------------------------------------------------------
# Stress Test — cenários de estresse
# ---------------------------------------------------------------------------
@app.post("/api/stress")
def stress_test(req: StressRequest):
    """Executa suite de cenários de estresse no portfólio."""
    portfolio = build_portfolio_from_tickers(req.tickers, req.quantities or None)
    sector_map = get_sector_map()
    scenarios = req.scenarios if req.scenarios else None
    results = run_stress_suite(portfolio, sector_map, scenarios)
    return {"scenarios": results}


# ---------------------------------------------------------------------------
# Momentum Ranking
# ---------------------------------------------------------------------------
@app.get("/api/momentum")
def momentum(
    start_date: str = "2024-01-01",
    end_date: str = "2025-12-31",
    top_n: int = 10,
):
    """Ranking de momentum dos FIIs do universo."""
    tickers = get_tickers()
    return_series, _ = load_returns_bulk(tickers, start_date, end_date)
    valid = {t: r for t, r in return_series.items() if len(r) >= 6}
    ranking = rank_by_momentum(valid)
    return {"ranking": ranking[:top_n], "total_analyzed": len(valid)}


# ---------------------------------------------------------------------------
# Cluster Analysis (K-Means)
# ---------------------------------------------------------------------------
@app.get("/api/clusters")
def clusters(
    start_date: str = "2024-01-01",
    end_date: str = "2025-12-31",
):
    """Agrupa FIIs por comportamento via K-Means clustering."""
    tickers = get_tickers()
    return_series, _ = load_returns_bulk(tickers, start_date, end_date)
    valid = {t: r for t, r in return_series.items() if len(r) >= 6}
    if len(valid) < 4:
        raise HTTPException(status_code=400, detail="Dados insuficientes para clustering")
    result = cluster_portfolio(valid)
    return result


# ---------------------------------------------------------------------------
# FIRE Calculator
# ---------------------------------------------------------------------------
@app.post("/api/fire")
def fire(req: FireRequest):
    """Calcula anos até FIRE e capital necessário."""
    years = calculate_years_to_fire(
        req.patrimonio_atual, req.aporte_mensal, req.taxa_anual, req.renda_alvo_anual
    )
    required = calculate_required_capital(req.renda_alvo_anual, req.taxa_anual)
    return {
        "years_to_fire": round(years, 1),
        "required_capital": round(required, 2),
        "monthly_income_at_fire": round(req.renda_alvo_anual / 12, 2),
        "current_patrimony": req.patrimonio_atual,
    }


# ---------------------------------------------------------------------------
# Simulate — projeção 12 meses
# ---------------------------------------------------------------------------
@app.post("/api/simulate")
def simulate(req: SimulateRequest):
    """Simula evolução da carteira por N meses com aportes."""
    portfolio = build_portfolio_from_tickers(req.tickers, req.quantities or None)

    # Build asset universe from fundamentals
    asset_universe = []
    for t in req.tickers:
        try:
            price, _ = load_last_price(t)
        except Exception:
            price = 100.0
        asset_universe.append({"ticker": t, "preco": price})

    # Default target allocation if not provided
    target = req.target_allocation
    if not target:
        weight = round(1.0 / len(req.tickers), 4)
        target = {t: weight for t in req.tickers}

    result = simulate_12_months(
        portfolio_inicial=portfolio,
        asset_universe=asset_universe,
        target_allocation=target,
        aporte_mensal=req.aporte_mensal,
        meses=req.meses,
    )
    return result


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------
@app.post("/api/monte-carlo")
def monte_carlo(req: MonteCarloRequest):
    """Simulação Monte Carlo com múltiplos cenários estocásticos."""
    portfolio = build_portfolio_from_tickers(req.tickers, req.quantities or None)

    asset_universe = []
    for t in req.tickers:
        try:
            price, _ = load_last_price(t)
        except Exception:
            price = 100.0
        asset_universe.append({"ticker": t, "preco": price})

    target = req.target_allocation
    if not target:
        weight = round(1.0 / len(req.tickers), 4)
        target = {t: weight for t in req.tickers}

    growth = req.growth_rates if req.growth_rates else {t: 0.005 for t in req.tickers}
    vols = req.volatilities if req.volatilities else {t: 0.03 for t in req.tickers}

    result = simulate_monte_carlo(
        portfolio_inicial=portfolio,
        asset_universe=asset_universe,
        target_allocation=target,
        aporte_mensal=req.aporte_mensal,
        growth_rates=growth,
        volatilities=vols,
        meses=req.meses,
        simulacoes=req.simulacoes,
    )
    return result


# ---------------------------------------------------------------------------
# AI Insights — análise de sentimento via Groq/Llama
# ---------------------------------------------------------------------------
@app.post("/api/ai/analyze")
def ai_analyze(req: AIAnalyzeRequest):
    """Busca notícias do FII e analisa sentimento via AI (Groq/Llama)."""
    news = fetch_fii_news(req.ticker.upper(), max_results=5)
    if not news:
        return {"success": False, "error": "Nenhuma notícia encontrada", "ticker": req.ticker}

    result = analyze_fii_news(req.ticker.upper(), news, api_key=req.api_key)
    result["news"] = news
    return result


@app.get("/api/news/{ticker}")
def get_news(ticker: str, limit: int = 10):
    """Retorna notícias recentes de um FII via múltiplas fontes RSS."""
    news = fetch_fii_news(ticker.upper(), max_results=limit)
    return {"ticker": ticker.upper(), "news": news, "count": len(news)}


@app.get("/api/news")
def get_market_news(limit: int = 20):
    """Retorna notícias gerais do mercado de FIIs."""
    news = fetch_market_news(max_results=limit)
    return {"news": news, "count": len(news)}


@app.get("/api/sources")
def get_data_sources():
    """Lista todas as fontes de dados configuradas."""
    return {
        "rss_sources": list_sources(),
        "data_sources": [
            {"name": "yfinance", "type": "prices", "description": "Preços e dividendos via Yahoo Finance"},
            {"name": "BCB/SGS", "type": "macro", "description": "Selic, CDI, IPCA via API do Banco Central"},
            {"name": "StatusInvest", "type": "fundamentals", "description": "DY, P/VP, vacância via scraping"},
            {"name": "FundsExplorer", "type": "fundamentals", "description": "Dados complementares de FIIs"},
            {"name": "Google News RSS", "type": "news", "description": "Notícias via busca RSS"},
            {"name": "Vectorizer", "type": "semantic_search", "description": "Busca semântica para RAG/AI"},
        ],
    }
