"""
api/main.py

API REST do AlphaCota — serve o frontend React com dados reais.
Endpoints públicos (sem auth): scanner, fii detail, macro, simulate, AI, etc.
Endpoints protegidos (com auth): report, history.
"""

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import logging
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional
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
from core.prediction_engine import get_prediction_signal
from core.fire_engine import calculate_years_to_fire, calculate_required_capital
from core.momentum_engine import rank_by_momentum
from core.cluster_engine import cluster_portfolio
from core.stress_engine import run_stress_suite
from core.ai_engine import analyze_fii_news
from core.fii_agent_pipeline import run_deep_analysis
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
from data.cvm_b3_client import fetch_cvm_fii_registry
from data.fundsexplorer_scraper import scrape_fii_detail
from data.data_loader import fetch_prices
from core.quant_engine import calculate_fii_score
import datetime

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
    override_initial_capital: Optional[float] = None


class CustomStressScenario(BaseModel):
    name: str = "Cenário Customizado"
    price_shock: dict[str, float] = {}
    dividend_shock: dict[str, float] = {}

class StressRequest(BaseModel):
    tickers: list[str]
    quantities: dict[str, int] = {}
    scenarios: list[str] = []
    custom_scenario: Optional[CustomStressScenario] = None


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

class AIBatchRequest(BaseModel):
    tickers: list[str]
    api_key: Optional[str] = None

class DeepAnalysisRequest(BaseModel):
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
            score = evaluation.get("final_score", evaluation.get("score_final", 0))
        except Exception:
            score = 0

        # Get last price + daily change
        change = 0.0
        try:
            import datetime as _dt
            end_d = _dt.date.today().isoformat()
            start_d = (_dt.date.today() - _dt.timedelta(days=10)).isoformat()
            recent = fetch_prices(ticker, start_d, end_d, frequency="1d")
            if len(recent) >= 2:
                prev_close = float(recent[-2]["close"])
                last_close = float(recent[-1]["close"])
                if prev_close > 0:
                    change = round((last_close / prev_close - 1) * 100, 2)
            price = float(recent[-1]["close"]) if recent else fund.get("cotacao", 0)
        except Exception:
            try:
                price, _ = load_last_price(ticker)
            except Exception:
                price = fund.get("cotacao", 0)

        _pvp = fund.get("pvp")
        _dy_raw = fund.get("dividend_yield", 0.0) or 0.0
        _liquidity = fund.get("liquidez_diaria") or fund.get("daily_liquidity") or 0

        # Confidence: debt/vacancy now None by default; only score what's real
        _conf = 0
        if float(price) > 0:
            _conf += 20
        if _dy_raw > 0:
            _conf += 20
        if _pvp is not None and _pvp != 1.0:
            _conf += 20
        if fund.get("vacancy_rate") is not None:
            _conf += 20
        if fund.get("debt_ratio") is not None:
            _conf += 20

        # Quality flags (5.3)
        _low_liquidity = _liquidity > 0 and _liquidity < 500_000
        _dividend_trap = _dy_raw > 0.20  # DY > 20% — armadilha
        _pvp_outlier = _pvp is not None and (_pvp > 2.0 or _pvp < 0.5)

        results.append(
            {
                "ticker": ticker,
                "name": fii.get("nome", ticker),
                "segment": sector_map.get(ticker, "Outros"),
                "price": round(float(price), 2),
                "change": change,
                "dy": round(_dy_raw * 100, 2),
                "pvp": round(_pvp, 2) if _pvp is not None else None,
                "score": round(score, 0),
                "liquidity": _liquidity,
                "_source": fund.get("_source", "default"),
                "data_confidence": _conf,
                "low_liquidity": _low_liquidity,
                "dividend_trap": _dividend_trap,
                "pvp_outlier": _pvp_outlier,
            }
        )

    # Sort by score descending; exclude low-liquidity from top (move to end)
    results.sort(key=lambda x: (not x["low_liquidity"], x["score"]), reverse=True)
    return {"fiis": results, "total": len(results)}


# ---------------------------------------------------------------------------
# FII Detail — dados completos de um FII específico
# ---------------------------------------------------------------------------
def _calculate_data_confidence(detail: dict) -> int:
    """Calcula score de confiança nos dados de 0 a 100 (5 dimensões x 20 pts cada)."""
    score = 0
    if detail.get("price", 0) > 0 and detail.get("price_source", "fallback") not in ("fallback", ""):
        score += 20
    dy = detail.get("dividend_monthly", 0)
    div_source = detail.get("dividend_source", "fallback")
    if dy > 0 and div_source not in ("fallback", "estimated", ""):
        score += 20
    fundamentals = detail.get("fundamentals", {})
    pvp = fundamentals.get("pvp", 1.0)
    if pvp and pvp != 1.0:
        score += 20
    vacancy = fundamentals.get("vacancy_rate", fundamentals.get("vacancia", 0.05))
    if vacancy is not None and vacancy != 0.05:
        score += 20
    debt = fundamentals.get("debt_ratio", 0.3)
    if debt is not None and debt != 0.3:
        score += 20
    return score


def _build_price_history(ticker: str, months: int = 24) -> list[dict]:
    """Retorna histórico mensal de preços via yfinance (até 24 meses)."""
    try:
        import yfinance as yf
        symbol = ticker if ticker.endswith(".SA") else f"{ticker}.SA"
        df = yf.Ticker(symbol).history(period=f"{months}mo", interval="1mo")
        if df.empty:
            return []
        result = []
        for ts, row in df.iterrows():
            month = str(ts)[:7]  # YYYY-MM
            if row["Close"] > 0:
                result.append({"month": month, "price": round(float(row["Close"]), 2)})
        return result[-months:]
    except Exception:
        return []


def _build_dividend_history(ticker: str, fe_data: Optional[dict], months: int = 24) -> list[dict]:
    """Retorna histórico mensal de dividendos por cota via yfinance (até 24 meses)."""
    try:
        import yfinance as yf
        symbol = ticker if ticker.endswith(".SA") else f"{ticker}.SA"
        divs = yf.Ticker(symbol).dividends
        if divs.empty:
            raise ValueError("no dividends")
        result = []
        for ts, val in divs.items():
            if val > 0:
                result.append({"month": str(ts)[:7], "value": round(float(val), 4)})
        # deduplicate (keep last per month)
        by_month: dict[str, float] = {}
        for item in result:
            by_month[item["month"]] = item["value"]
        return [{"month": m, "value": v} for m, v in sorted(by_month.items())[-months:]]
    except Exception:
        pass
    # Fallback: FundsExplorer
    if fe_data and fe_data.get("historico_dividendos"):
        hist = fe_data["historico_dividendos"]
        return [{"month": h.get("data", "")[:7], "value": h.get("valor", 0)} for h in hist[:months]]
    return []


def _build_fund_info(ticker: str, fe_data: Optional[dict]) -> dict:
    """Retorna info cadastral: nome, cotas, patrimônio, administrador, CNPJ."""
    info: dict = {}
    # yfinance info (faster + reliable)
    try:
        import yfinance as yf
        symbol = ticker if ticker.endswith(".SA") else f"{ticker}.SA"
        yi = yf.Ticker(symbol).info
        if yi.get("longName"):
            info["nome"] = yi["longName"]
        if yi.get("sharesOutstanding"):
            info["num_cotas"] = yi["sharesOutstanding"]
        if yi.get("marketCap"):
            info["patrimonio_liquido"] = yi["marketCap"]
        if yi.get("dividendRate"):
            info["dividendo_anual_por_cota"] = round(float(yi["dividendRate"]), 2)
        if yi.get("dividendYield"):
            info["dy_yfinance"] = round(float(yi["dividendYield"]), 2)
        if yi.get("fundFamily"):
            info["gestora"] = yi["fundFamily"]
    except Exception:
        pass
    # CVM registry (CNPJ + administrador)
    try:
        registry = fetch_cvm_fii_registry()
        for entry in registry:
            if ticker.upper() in entry.get("nome", "").upper() or ticker.upper() in (entry.get("ticker") or "").upper():
                if entry.get("administrador"):
                    info["administrador"] = entry["administrador"]
                if entry.get("cnpj"):
                    info["cnpj"] = entry["cnpj"]
                break
    except Exception:
        pass
    # FundsExplorer complement
    if fe_data:
        info.setdefault("num_cotistas", fe_data.get("num_cotistas"))
        info.setdefault("patrimonio_liquido", fe_data.get("patrimonio_liquido"))
    return info


@app.get("/api/fii/{ticker}")
def fii_detail(ticker: str):
    """Retorna detalhes completos de um FII: fundamentals, preço, dividendos, score, históricos."""
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

    # Score FII-specific (4 dimensões)
    score_data = {
        "pvp": fund.get("pvp", 1.0),
        "debt_ratio": fund.get("debt_ratio", 0.3),
        "dividend_yield": fund.get("dividend_yield", 0.08),
        "dividend_consistency": fund.get("dividend_consistency", 0.5),
        "vacancy_rate": fund.get("vacancia", 0.05),
        "daily_liquidity": fund.get("liquidez_diaria", 5_000_000),
    }
    try:
        score_breakdown = calculate_fii_score(score_data)
    except Exception:
        score_breakdown = {"fundamentos": 0, "rendimento": 0, "risco": 0, "liquidez": 0, "total": 0}

    # FundsExplorer data (histórico + patrimônio)
    try:
        fe_data = scrape_fii_detail(ticker)
    except Exception:
        fe_data = None

    # Históricos
    price_history = _build_price_history(ticker)
    dividend_history = _build_dividend_history(ticker, fe_data)

    # Fund info (CVM + FundsExplorer)
    fund_info = _build_fund_info(ticker, fe_data)

    # Extra indicators — volatilidade 30d via preços recentes
    vol_30d = None
    try:
        import math

        end_v = datetime.date.today()
        start_v = end_v - datetime.timedelta(days=45)
        rows_v = fetch_prices(ticker, str(start_v), str(end_v))
        closes = [r["close"] for r in rows_v if r["close"] > 0]
        if len(closes) >= 5:
            returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
            mean_r = sum(returns) / len(returns)
            variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
            vol_30d = round(math.sqrt(variance) * math.sqrt(252) * 100, 2)  # % a.a.
    except Exception:
        vol_30d = None

    sector_map = get_sector_map()

    response = {
        "ticker": ticker,
        "segment": sector_map.get(ticker, "Outros"),
        "price": round(price, 2),
        "price_source": price_source,
        "dividend_monthly": round(dividend, 4),
        "dividend_source": div_source,
        "fundamentals": fund,
        "evaluation": evaluation,
        "score_breakdown": score_breakdown,
        "price_history": price_history,
        "dividend_history": dividend_history,
        "fund_info": fund_info,
        "cap_rate": fund.get("cap_rate"),
        "volatilidade_30d": vol_30d,
        "num_imoveis": fund.get("num_imoveis"),
        "num_locatarios": fund.get("num_locatarios"),
    }
    response["data_confidence"] = _calculate_data_confidence(response)
    return response


# ---------------------------------------------------------------------------
# FII Compare — dados comparativos de múltiplos FIIs
# ---------------------------------------------------------------------------
@app.get("/api/fiis/compare")
def compare_fiis(tickers: str = Query(..., description="Comma-separated tickers, e.g. MXRF11,HGLG11,XPML11")):
    """Retorna dados completos de múltiplos FIIs para comparação lado a lado."""
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if len(ticker_list) < 1:
        raise HTTPException(status_code=400, detail="Informe ao menos um ticker")
    if len(ticker_list) > 10:
        raise HTTPException(status_code=400, detail="Máximo de 10 tickers por comparação")

    sector_map = get_sector_map()
    results = []

    for ticker in ticker_list:
        fund = fetch_fundamentals(ticker)

        try:
            price, price_source = load_last_price(ticker)
        except Exception:
            price, price_source = 0.0, "unavailable"

        try:
            dividend, div_source = load_monthly_dividend(ticker)
        except Exception:
            dividend, div_source = 0.0, "unavailable"

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

        score_data = {
            "pvp": fund.get("pvp", 1.0),
            "debt_ratio": fund.get("debt_ratio", 0.3),
            "dividend_yield": fund.get("dividend_yield", 0.08),
            "dividend_consistency": fund.get("dividend_consistency", 0.5),
            "vacancy_rate": fund.get("vacancia", 0.05),
            "daily_liquidity": fund.get("liquidez_diaria", 5_000_000),
        }
        try:
            score_breakdown = calculate_fii_score(score_data)
        except Exception:
            score_breakdown = {"fundamentos": 0, "rendimento": 0, "risco": 0, "liquidez": 0, "total": 0}

        try:
            fe_data = scrape_fii_detail(ticker)
        except Exception:
            fe_data = None

        price_history = _build_price_history(ticker, months=12)
        dividend_history = _build_dividend_history(ticker, fe_data, months=12)
        fund_info = _build_fund_info(ticker, fe_data)

        vol_30d = None
        try:
            import math as _math
            end_v = datetime.date.today()
            start_v = end_v - datetime.timedelta(days=45)
            rows_v = fetch_prices(ticker, str(start_v), str(end_v))
            closes = [r["close"] for r in rows_v if r["close"] > 0]
            if len(closes) >= 5:
                returns = [_math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
                mean_r = sum(returns) / len(returns)
                variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
                vol_30d = round(_math.sqrt(variance) * _math.sqrt(252) * 100, 2)
        except Exception:
            vol_30d = None

        compare_entry: dict = {
            "ticker": ticker,
            "segment": sector_map.get(ticker, "Outros"),
            "price": round(float(price), 2),
            "price_source": price_source,
            "dividend_monthly": round(float(dividend), 4),
            "dividend_source": div_source,
            "fundamentals": fund,
            "evaluation": evaluation,
            "score_breakdown": score_breakdown,
            "price_history": price_history,
            "dividend_history": dividend_history,
            "fund_info": fund_info,
            "cap_rate": fund.get("cap_rate"),
            "volatilidade_30d": vol_30d,
            "num_imoveis": fund.get("num_imoveis"),
            "num_locatarios": fund.get("num_locatarios"),
            # Convenience top-level fields for compare table
            "dy": round(fund.get("dividend_yield", 0.0) * 100, 2),
            "pvp": round(fund.get("pvp", 1.0), 2),
            "liquidez": fund.get("liquidez_diaria", 0),
            "vacancia": round(fund.get("vacancia", 0.0) * 100, 2),
            "score": round(score_breakdown.get("total", 0), 0),
        }
        compare_entry["data_confidence"] = _calculate_data_confidence(compare_entry)
        results.append(compare_entry)

    return {"fiis": results}


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
    raw = get_macro_snapshot()
    # Remap internal keys to the names the frontend MacroSnapshot type expects
    return {
        "selic": raw.get("selic_anual", 0),
        "cdi": raw.get("cdi_anual", 0),
        "ipca": raw.get("ipca_anual", 0),
        "selic_source": raw.get("fonte_selic", "bcb"),
        "cdi_source": raw.get("fonte_selic", "bcb"),
        "ipca_source": raw.get("fonte_ipca", "bcb"),
        **raw,  # keep originals for MCP / other consumers
    }


# ---------------------------------------------------------------------------
# Prediction Markets — sinais macro via Polymarket
# ---------------------------------------------------------------------------
@app.get("/api/prediction")
def prediction_signal():
    """Retorna sinal macro de mercados de previsão (Polymarket) para FIIs.

    Score 0-100: >65 = bullish, <35 = bearish, restante = neutro.
    Cache local de 6h para evitar chamadas excessivas.
    """
    return get_prediction_signal()


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
    
    if req.custom_scenario:
        from core.stress_engine import STRESS_SCENARIOS
        STRESS_SCENARIOS["custom_user_scenario"] = {
            "name": req.custom_scenario.name,
            "description": "Cenário modelado pelas variáveis do usuário.",
            "price_shock": req.custom_scenario.price_shock,
            "dividend_shock": req.custom_scenario.dividend_shock,
        }
        if req.scenarios:
            if "custom_user_scenario" not in req.scenarios:
                req.scenarios.append("custom_user_scenario")
        else:
            req.scenarios = list(STRESS_SCENARIOS.keys())

    scenarios = req.scenarios if req.scenarios else None
    results = run_stress_suite(portfolio, sector_map, scenarios)
    
    if req.custom_scenario:
        from core.stress_engine import STRESS_SCENARIOS
        STRESS_SCENARIOS.pop("custom_user_scenario", None)

    return {"scenarios": results}


# ---------------------------------------------------------------------------
# Momentum Ranking
# ---------------------------------------------------------------------------
@app.get("/api/momentum")
def momentum(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    top_n: int = 10,
):
    from datetime import date, timedelta
    actual_end = end_date or date.today().strftime("%Y-%m-%d")
    actual_start = start_date or (date.today() - timedelta(days=365*2)).strftime("%Y-%m-%d")
    """Ranking de momentum dos FIIs do universo."""
    tickers = get_tickers()
    return_series, _ = load_returns_bulk(tickers, actual_start, actual_end)
    valid = {t: r for t, r in return_series.items() if len(r) >= 6}
    ranking = rank_by_momentum(valid)
    
    # Map back to the fields expected by Frontend
    mapped_ranking = []
    for r in ranking:
        mapped_ranking.append({
            "ticker": r["ticker"],
            "score": r["score"] / 100.0, # Frontend multiplies by 100
            "ret_1m": r["retorno_1m_%"] / 100.0,
            "ret_3m": r["retorno_3m_%"] / 100.0,
            "ret_6m": r["retorno_6m_%"] / 100.0,
            "ret_12m": r["retorno_12m_%"] / 100.0,
            "classificacao": r["classificacao"]
        })

    return {"ranking": mapped_ranking[:top_n], "total_analyzed": len(valid)}


# ---------------------------------------------------------------------------
# Cluster Analysis (K-Means)
# ---------------------------------------------------------------------------
@app.get("/api/clusters")
def clusters(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    n_clusters: int = 4,
):
    from datetime import date, timedelta
    actual_end = end_date or date.today().strftime("%Y-%m-%d")
    actual_start = start_date or (date.today() - timedelta(days=365*2)).strftime("%Y-%m-%d")
    
    """Agrupa FIIs em clusters baseados em correlação (PCA+KMeans)."""
    tickers = get_tickers()
    return_series, sources = load_returns_bulk(tickers, actual_start, actual_end)
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
    years = calculate_years_to_fire(req.patrimonio_atual, req.aporte_mensal, req.taxa_anual, req.renda_alvo_anual)
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
        override_initial_capital=req.override_initial_capital,
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

@app.post("/api/ai/analyze-batch")
def ai_analyze_batch(req: AIBatchRequest):
    """Busca notícias e sentimentos para múltiplos FIIs sequencialmente com cache."""
    results = []
    
    # Imports inside block to avoid global side-effects when loading if unneeded
    from core.ai_cache import get_cached_sentiment
    import time
    
    for ticker in req.tickers:
        ticker_upper = ticker.upper()
        
        # Check cache explicitly first to avoid sleep if it's hitting cache
        cached = get_cached_sentiment(ticker_upper)
        if cached:
            results.append(cached)
            continue
            
        # If not cached, fetch news and analyze
        news = fetch_fii_news(ticker_upper, max_results=5)
        if not news:
            results.append({"success": False, "error": "Nenhuma notícia encontrada", "ticker": ticker_upper})
            continue
            
        result = analyze_fii_news(ticker_upper, news, api_key=req.api_key)
        results.append(result)
        
        # Rate limiting delay for Groq Free limits (30 reqs/min usually)
        # Avoid delay if it's the last element
        if ticker != req.tickers[-1]:
            time.sleep(1.5)
            
    return {"success": True, "results": results}


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


# ---------------------------------------------------------------------------
# Dividend Calendar
# ---------------------------------------------------------------------------

@app.get("/api/dividends/calendar")
def get_dividend_calendar(
    year: int = Query(...),
    month: int = Query(...),
    tickers: str = Query(default=""),
):
    """Eventos de dividendos de um mês. tickers=MXRF11,XPML11 ou vazio para todos."""
    from data.dividend_calendar import get_calendar_month
    ticker_list = (
        [t.strip() for t in tickers.split(",") if t.strip()]
        if tickers
        else [u["ticker"] for u in get_universe()]
    )
    events = get_calendar_month(year, month, ticker_list)
    return {"year": year, "month": month, "events": events, "total": len(events)}


@app.get("/api/dividends/portfolio-income")
def get_portfolio_income_projection(
    holdings: str = Query(..., description='JSON: {"MXRF11": 100, "XPML11": 50}'),
    months_ahead: int = Query(default=12),
):
    """Projeção de renda mensal para uma carteira com quantidade de cotas."""
    import json as _json
    from data.dividend_calendar import get_portfolio_income
    try:
        portfolio = _json.loads(holdings)
    except Exception:
        raise HTTPException(status_code=400, detail="holdings deve ser JSON válido")
    return {"projection": get_portfolio_income(portfolio, months_ahead)}


@app.get("/api/dividends/upcoming")
def get_upcoming_dividends(
    days_ahead: int = Query(default=30, ge=1, le=90),
    tickers: str = Query(default=""),
):
    """Eventos de dividendo nos próximos N dias. Usado para alertas e banners."""
    from data.dividend_calendar import get_calendar_month, estimate_next_events
    ticker_list = (
        [t.strip() for t in tickers.split(",") if t.strip()]
        if tickers
        else [u["ticker"] for u in get_universe()]
    )
    today = datetime.date.today()
    cutoff = today + datetime.timedelta(days=days_ahead)

    # Collect events from current + next month
    events = []
    months_to_check = {(today.year, today.month), (cutoff.year, cutoff.month)}
    for year, month in months_to_check:
        events.extend(get_calendar_month(year, month, ticker_list))

    # Filter to window and add days_until fields
    upcoming = []
    for ev in events:
        try:
            pay = datetime.date.fromisoformat(ev["pay_date"])
            ex = datetime.date.fromisoformat(ev["ex_date"])
        except Exception:
            continue
        if today <= pay <= cutoff:
            days_to_pay = (pay - today).days
            days_to_ex = (ex - today).days
            upcoming.append({
                **ev,
                "days_to_pay": days_to_pay,
                "days_to_ex": days_to_ex,
                "is_ex_soon": 0 <= days_to_ex <= 7,
            })

    upcoming.sort(key=lambda e: e["pay_date"])
    return {"days_ahead": days_ahead, "events": upcoming, "total": len(upcoming)}


# ---------------------------------------------------------------------------
# History & Timeline (SQLite)
# ---------------------------------------------------------------------------

@app.get("/api/fiis/{ticker}/history")
def get_fii_score_history(ticker: str, limit: int = 12):
    """Retorna o histórico mensal do score via banco SQLite."""
    from api.db_sqlite import get_score_timeline
    timeline = get_score_timeline(ticker.upper(), limit)
    return {"ticker": ticker.upper(), "timeline": timeline}

@app.get("/api/ai/sentiment/trend/{ticker}")
def get_ai_sentiment_trend(ticker: str, limit: int = 5):
    """Retorna a evolução histórica do sentimento da IA."""
    from api.db_sqlite import get_sentiment_trend
    trend = get_sentiment_trend(ticker.upper(), limit)
    return {"ticker": ticker.upper(), "trend": trend}


@app.post("/api/ai/deep-analysis/{ticker}")
def ai_deep_analysis(ticker: str, req: DeepAnalysisRequest = DeepAnalysisRequest()):
    """
    Pipeline multi-agente de análise profunda de um FII.

    Executa 5 agentes em sequência (Macro → Fundamental → Risk → Persona → Decision)
    e retorna raciocínio auditável por etapa + recomendação final BUY/HOLD/SELL.
    """
    ticker = ticker.upper()

    # --- montar fii_data (mesmo formato que /api/fii/{ticker}) ---
    fund = fetch_fundamentals(ticker)

    try:
        price, _ = load_last_price(ticker)
    except Exception:
        price = 0.0

    try:
        dividend, _ = load_monthly_dividend(ticker)
    except Exception:
        dividend = 0.0

    score_data = {
        "pvp": fund.get("pvp", 1.0),
        "debt_ratio": fund.get("debt_ratio", 0.3),
        "dividend_yield": fund.get("dividend_yield", 0.08),
        "dividend_consistency": fund.get("dividend_consistency", 0.5),
        "vacancy_rate": fund.get("vacancia", 0.05),
        "daily_liquidity": fund.get("liquidez_diaria", 5_000_000),
    }
    try:
        score_breakdown = calculate_fii_score(score_data)
    except Exception:
        score_breakdown = {"total": 0}

    sector_map = get_sector_map()

    fii_data = {
        "ticker": ticker,
        "segment": sector_map.get(ticker, "Outros"),
        "price": round(price, 2),
        "dividend_monthly": round(dividend, 4),
        "fundamentals": fund,
        "score_breakdown": score_breakdown,
        "vol_30d": None,
    }

    # --- macro ---
    try:
        macro = get_macro_snapshot()
    except Exception:
        macro = {"selic_anual": 10.75, "cdi_anual": 10.65, "ipca_anual": 4.83}

    # --- notícias ---
    try:
        news = fetch_fii_news(ticker, max_results=5)
    except Exception:
        news = []

    result = run_deep_analysis(ticker, fii_data, macro, news, api_key=req.api_key)
    return result


@app.get("/api/fiis/alerts")
def score_alerts(tickers: str, threshold: float = 10.0):
    """Retorna alertas se o score de algum dos ativos caiu abruptamente."""
    from api.db_sqlite import get_score_alerts
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        return {"alerts": []}
    alerts = get_score_alerts(ticker_list, drop_threshold=threshold)
    return {"alerts": alerts, "count": len(alerts)}

@app.get("/api/portfolio/tearsheet", response_class=HTMLResponse)
def portfolio_tearsheet(tickers: str, weights: str):
    """
    Gera as lágrimas estatísticas avançadas usando a biblioteca Quantstats.
    Devolve a string de HTML puro.
    ?tickers=MXRF11,HGLG11&weights=0.4,0.6
    """
    from api.services.portfolio_tearsheet import generate_tearsheet
    
    t_list = [t.strip() for t in tickers.split(",") if t.strip()]
    w_list = [float(w.strip()) for w in weights.split(",") if w.strip()]
    
    if len(t_list) != len(w_list) or len(t_list) == 0:
        raise HTTPException(status_code=400, detail="Tickers e weights incompatíveis ou vazios.")
        
    portfolio_alloc = dict(zip(t_list, w_list))
    
    try:
        # Gera o HTML e salva em temp file
        html_path = generate_tearsheet(portfolio_alloc, benchmark="^BVSP", period_days=730)
        # Lê o HTML e deleta o temporário
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        import os
        os.remove(html_path)
        
        return HTMLResponse(content=html_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno ao renderizar tearsheet: {str(e)}")


# ---------------------------------------------------------------------------
# Polymarket trading routes
# ---------------------------------------------------------------------------

import time as _time_mod

_pm_loop_start: float | None = None
_pm_loop_mode: str = "paper"


@app.get("/api/polymarket/status")
def polymarket_status():
    """Return Polymarket loop running status, mode, and uptime."""
    from pathlib import Path
    kill_active = Path("data/POLYMARKET_KILL").exists()
    uptime = round(_time_mod.time() - _pm_loop_start, 1) if _pm_loop_start else None
    return {
        "running": _pm_loop_start is not None,
        "mode": _pm_loop_mode,
        "uptime_seconds": uptime,
        "kill_switch_active": kill_active,
    }


@app.get("/api/polymarket/positions")
def polymarket_positions():
    """Return all open Polymarket positions with unrealized PnL."""
    from core.polymarket_ledger import init_db
    conn = init_db()
    rows = conn.execute(
        "SELECT * FROM pm_positions ORDER BY opened_at DESC"
    ).fetchall()
    conn.close()
    return {
        "positions": [
            {
                "position_id": row["position_id"],
                "condition_id": row["condition_id"],
                "direction": row["direction"],
                "size_usd": round(float(row["size_usd"]), 2),
                "entry_price": round(float(row["entry_price"]), 4),
                "current_price": round(float(row["current_price"]), 4),
                "unrealized_pnl": round(float(row["unrealized_pnl"]), 2),
                "mode": row["mode"],
                "opened_at": float(row["opened_at"]),
            }
            for row in rows
        ],
        "total": len(rows),
    }


@app.get("/api/polymarket/pnl")
def polymarket_pnl():
    """Return realized PnL history from pm_pnl_snapshots."""
    from core.polymarket_ledger import init_db
    conn = init_db()
    rows = conn.execute(
        "SELECT * FROM pm_pnl_snapshots ORDER BY snapshot_date DESC LIMIT 90"
    ).fetchall()
    conn.close()
    return {
        "snapshots": [
            {
                "date": row["snapshot_date"],
                "equity_usd": round(float(row["equity_usd"]), 2),
                "open_positions": int(row["open_positions"]),
                "daily_pnl": round(float(row["daily_pnl"]), 2),
                "mode": row["mode"],
            }
            for row in rows
        ],
        "total": len(rows),
    }


@app.post("/api/polymarket/kill")
def polymarket_kill(_: dict = Depends(get_current_user)):
    """Create the kill-switch file to halt the trading loop (auth required)."""
    from pathlib import Path
    kill_path = Path("data/POLYMARKET_KILL")
    kill_path.parent.mkdir(parents=True, exist_ok=True)
    kill_path.touch()
    return {"killed": True, "message": "Kill-switch activated. Loop will stop at next cycle."}


@app.get("/api/polymarket/live-status")
def polymarket_live_status():
    """Return wallet USDC balance, daily PnL, open positions, mode, and preflight timestamp."""
    from core.polymarket_client import get_wallet_health
    from core.polymarket_ledger import init_db
    from datetime import date

    conn = init_db()
    today = date.today().isoformat()

    open_count = conn.execute("SELECT COUNT(*) FROM pm_positions").fetchone()[0]
    daily_pnl = conn.execute(
        "SELECT COALESCE(SUM(realized_pnl), 0) FROM pm_trades "
        "WHERE date(closed_at, 'unixepoch') = ?",
        (today,),
    ).fetchone()[0]
    conn.close()

    wallet = get_wallet_health()
    return {
        "mode": _pm_loop_mode,
        "usdc_balance": round(wallet.usdc_balance, 2),
        "daily_realized_pnl": round(float(daily_pnl), 2),
        "open_positions": int(open_count),
        "wallet_healthy": wallet.is_healthy,
        "preflight_last_run": None,
    }


@app.get("/api/polymarket/orders")
def polymarket_orders(limit: int = 50):
    """Return the last N orders from the ledger, enriched with market question."""
    import httpx as _httpx
    from core.polymarket_ledger import init_db
    conn = init_db()
    rows = conn.execute(
        "SELECT * FROM pm_orders ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()

    # Fetch market questions in batch (unique condition_ids only)
    condition_ids = list({row["condition_id"] for row in rows if row["condition_id"]})
    questions: dict[str, str] = {}
    for cid in condition_ids:
        try:
            r = _httpx.get(f"https://clob.polymarket.com/markets/{cid}", timeout=5)
            if r.is_success:
                questions[cid] = r.json().get("question", "")
        except Exception:
            pass

    return {
        "orders": [
            {
                "order_id": row["client_order_id"],
                "market_id": row["condition_id"],
                "question": questions.get(row["condition_id"], ""),
                "direction": row["direction"],
                "size_usd": round(float(row["size_usd"]), 2),
                "fill_price": round(float(row["fill_price"]), 4) if row["fill_price"] else None,
                "status": row["status"],
                "mode": row["mode"],
                "created_at": float(row["created_at"]),
            }
            for row in rows
        ],
        "total": len(rows),
    }


@app.get("/api/polymarket/price-history/{condition_id}")
def polymarket_price_history(condition_id: str, interval: str = "1d"):
    """Fetch probability evolution for all outcomes of a market.

    Calls CLOB prices-history for each token_id in the market, returning
    a list of {timestamp, outcome, price} rows suitable for recharts LineChart.
    interval: max (all time), 1d, 1w, 1m, 6m, 1y
    """
    import httpx as _httpx

    _CLOB_BASE = "https://clob.polymarket.com"
    _INTERVAL_MAP = {"max": "max", "1d": "1d", "1w": "1w", "1m": "1m", "6m": "6m", "1y": "1y"}
    clob_interval = _INTERVAL_MAP.get(interval, "max")

    try:
        mkt_resp = _httpx.get(f"{_CLOB_BASE}/markets/{condition_id}", timeout=10)
        if not mkt_resp.is_success:
            raise HTTPException(status_code=502, detail=f"CLOB error {mkt_resp.status_code}")
        mkt = mkt_resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    question = mkt.get("question", "")
    tokens = mkt.get("tokens", [])  # [{token_id, outcome}, ...]
    if not tokens:
        # fallback: parse from outcomePrices / outcomes
        outcomes = mkt.get("outcomes", [])
        if isinstance(outcomes, str):
            import json as _json
            try:
                outcomes = _json.loads(outcomes)
            except Exception:
                outcomes = []
        tokens = [{"token_id": "", "outcome": o} for o in outcomes]

    series: list[dict] = []
    timestamps_set: set[int] = set()
    outcome_data: dict[str, dict[int, float]] = {}  # outcome -> {ts -> price}

    for tok in tokens:
        token_id = tok.get("token_id", "")
        outcome = tok.get("outcome", "?")
        if not token_id:
            continue
        try:
            hist_resp = _httpx.get(
                f"{_CLOB_BASE}/prices-history",
                params={"market": token_id, "interval": clob_interval},
                timeout=15,
            )
            if not hist_resp.is_success:
                continue
            hist = hist_resp.json()
            history = hist.get("history", [])
            ts_prices: dict[int, float] = {}
            for point in history:
                ts = int(point.get("t", 0))
                price = float(point.get("p", 0.0))
                ts_prices[ts] = price
                timestamps_set.add(ts)
            outcome_data[outcome] = ts_prices
        except Exception:
            pass

    # Build merged rows: [{ts, outcome1_price, outcome2_price, ...}]
    all_ts = sorted(timestamps_set)
    raw_series: list[dict] = []
    for ts in all_ts:
        row: dict = {"ts": ts}
        for outcome, ts_map in outcome_data.items():
            row[outcome] = round(ts_map.get(ts, 0.0) * 100, 2)  # convert to %
        raw_series.append(row)

    # Downsample to max 300 points using LTTB-style bucket sampling
    # This keeps shape of the curve without flooding the frontend with 4000+ points
    _MAX_POINTS = 300
    if len(raw_series) > _MAX_POINTS:
        step = len(raw_series) / _MAX_POINTS
        outcome_keys = list(outcome_data.keys())
        sampled: list[dict] = []
        for i in range(_MAX_POINTS):
            # Take the point with the largest change within each bucket
            lo = int(i * step)
            hi = min(int((i + 1) * step), len(raw_series))
            bucket = raw_series[lo:hi]
            if not bucket:
                continue
            if len(bucket) == 1:
                sampled.append(bucket[0])
                continue
            # Pick point with max absolute change from bucket start for any outcome
            ref = bucket[0]
            best = bucket[0]
            best_delta = 0.0
            for pt in bucket[1:]:
                delta = max(abs(pt.get(k, 0) - ref.get(k, 0)) for k in outcome_keys)
                if delta >= best_delta:
                    best_delta = delta
                    best = pt
            sampled.append(best)
        series = sampled
    else:
        series = raw_series

    all_outcomes = [tok.get("outcome", "?") for tok in tokens if tok.get("token_id")]

    # For binary markets (Yes/No that sum to 100%), show only the first outcome.
    # Showing both creates a mirror-image mess — the second line adds no information.
    # For multi-outcome markets (3+ candidates, etc.) show all lines.
    is_binary = (
        len(all_outcomes) == 2
        and set(o.lower() for o in all_outcomes) <= {"yes", "no"}
    )
    if is_binary:
        primary = all_outcomes[0]
        display_outcomes = [primary]
        series = [{k: v for k, v in row.items() if k in ("ts", primary)} for row in series]
    else:
        display_outcomes = all_outcomes

    return {
        "condition_id": condition_id,
        "question": question,
        "outcomes": display_outcomes,
        "series": series,
    }


@app.get("/api/polymarket/trending-markets")
def polymarket_trending_markets(limit: int = 10):
    """Return top active markets by weekly volume from gamma-api."""
    import httpx as _httpx

    _GAMMA = "https://gamma-api.polymarket.com"
    try:
        resp = _httpx.get(
            f"{_GAMMA}/markets",
            params={
                "active": "true",
                "limit": limit,
                "order": "volume1wk",
                "ascending": "false",
                "enableOrderBook": "true",
            },
            timeout=12,
        )
        if not resp.is_success:
            raise HTTPException(status_code=502, detail=f"gamma-api {resp.status_code}")
        markets = resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    result = []
    for m in markets:
        cid = m.get("conditionId", "")
        if not cid:
            continue
        try:
            outcomes = m.get("outcomes", "[]")
            if isinstance(outcomes, str):
                import json as _json
                outcomes = _json.loads(outcomes)
            prices_raw = m.get("outcomePrices", "[]")
            if isinstance(prices_raw, str):
                import json as _json
                prices_raw = _json.loads(prices_raw)
            prices = [round(float(p) * 100, 1) for p in prices_raw]
        except Exception:
            outcomes = []
            prices = []

        result.append({
            "condition_id": cid,
            "question": m.get("question", ""),
            "volume_1wk": m.get("volume1wkClob", 0),
            "outcomes": outcomes,
            "prices": prices,
        })

    return {"markets": result}


@app.get("/api/polymarket/calibration")
def polymarket_calibration(lookback_days: int = 90):
    """Return calibration stats: Brier score, win rate, category breakdown, reliability bins, weight history."""
    from core.polymarket_calibration import compute_calibration_stats, reliability_bins
    from core.polymarket_ledger import init_db

    conn = init_db()
    try:
        report = compute_calibration_stats(conn, lookback_days=lookback_days)
        bins = reliability_bins(conn, lookback_days=lookback_days)

        weight_history = conn.execute(
            """
            SELECT tuned_at, trigger_markets, weights_before, weights_after,
                   brier_score, win_rate
            FROM pm_weight_history
            ORDER BY tuned_at DESC
            LIMIT 5
            """
        ).fetchall()
    finally:
        conn.close()

    import json as _json
    return {
        "overall_brier": report.overall_brier,
        "overall_win_rate": report.overall_win_rate,
        "total_resolved": report.total_resolved,
        "lookback_days": report.lookback_days,
        "generated_at": report.generated_at,
        "categories": [
            {
                "category": c.category,
                "brier_score": c.brier_score,
                "win_rate": c.win_rate,
                "mean_edge": c.mean_edge,
                "resolved_count": c.resolved_count,
            }
            for c in report.categories
        ],
        "reliability_bins": [
            {
                "bin_low": b.bin_low,
                "bin_high": b.bin_high,
                "predicted_prob": b.predicted_prob,
                "actual_win_rate": b.actual_win_rate,
                "count": b.count,
            }
            for b in bins
        ],
        "weight_history": [
            {
                "tuned_at": float(row["tuned_at"]),
                "trigger_markets": row["trigger_markets"],
                "weights_before": _json.loads(row["weights_before"]),
                "weights_after": _json.loads(row["weights_after"]),
                "brier_score": round(float(row["brier_score"]), 6),
                "win_rate": round(float(row["win_rate"]), 4),
            }
            for row in weight_history
        ],
    }


@app.get("/api/polymarket/wallets")
def polymarket_wallets():
    """Return ranked wallet list with alpha scores and rank changes."""
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path
    from core.polymarket_ledger import init_db
    from core.polymarket_wallet_ranker import WalletRank, rerank_wallets

    # Build watchlist from wallet_cache.db (distinct addresses ever tracked)
    _cache_db = _Path("data/wallet_cache.db")
    watchlist: list[str] = []
    if _cache_db.exists():
        try:
            _wconn = _sqlite3.connect(str(_cache_db))
            rows = _wconn.execute("SELECT DISTINCT address FROM wallet_positions").fetchall()
            watchlist = [r[0] for r in rows]
            _wconn.close()
        except Exception:
            pass

    class _Tracker:
        pass

    _tracker = _Tracker()
    _tracker.watchlist = watchlist  # type: ignore[attr-defined]

    conn = init_db()
    try:
        rankings: list[WalletRank] = rerank_wallets(conn, _tracker)
    finally:
        conn.close()

    return {
        "wallets": [
            {
                "address": r.address,
                "alpha_score": r.alpha_score,
                "win_rate": r.win_rate,
                "resolved_count": r.resolved_count,
                "last_active": r.last_active,
                "rank_change": r.rank_change,
            }
            for r in rankings
        ],
        "total": len(rankings),
    }


@app.post("/api/polymarket/wallets/seed")
def polymarket_wallets_seed(markets: int = 100, min_size: float = 5.0):
    """Run wallet seeder in background thread and return immediately."""
    import threading
    from core.polymarket_wallet_seeder import seed_wallets

    def _run():
        try:
            seed_wallets(wallets=markets, min_size_usd=min_size)
        except Exception as exc:
            import logging as _logging
            _logging.getLogger("alphacota").warning("wallet seeder background error: %s", exc)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"status": "started", "markets": markets, "min_size_usd": min_size}


class IngestPosition(BaseModel):
    address: str
    market_id: str
    outcome: str
    side: str
    size_usd: float
    pnl: float
    closed_at: float = 0.0


class IngestPayload(BaseModel):
    positions: list[IngestPosition]
    worker_id: str = "remote"


@app.post("/api/polymarket/wallets/ingest")
def polymarket_wallets_ingest(payload: IngestPayload):
    """Receive resolved positions from a remote worker and upsert into local wallet_cache.db.

    Called by the VM worker after collecting wallet data. No auth required since
    it only writes to the local SQLite cache — no funds involved.
    """
    from core.polymarket_wallet_seeder import _get_cache_conn, _upsert_position

    conn = _get_cache_conn()
    saved = 0
    errors = 0
    for pos in payload.positions:
        try:
            _upsert_position(
                conn,
                address=pos.address,
                market_id=pos.market_id,
                outcome=pos.outcome,
                side=pos.side,
                size_usd=pos.size_usd,
                pnl=pos.pnl,
                closed_at=pos.closed_at,
            )
            saved += 1
        except Exception as exc:
            import logging as _log
            _log.getLogger("alphacota").warning("ingest: %s/%s: %s", pos.address[:12], pos.market_id[:12], exc)
            errors += 1

    # Count eligible wallets after ingest
    try:
        row = conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT address FROM wallet_positions
                WHERE resolved = 1
                GROUP BY address HAVING COUNT(*) >= 5
            )
        """).fetchone()
        eligible = int(row[0]) if row else 0
    except Exception:
        eligible = -1

    conn.close()
    import logging as _log
    _log.getLogger("alphacota").info("ingest from worker=%s: %d saved, %d errors, %d eligible",
                payload.worker_id, saved, errors, eligible)
    return {"saved": saved, "errors": errors, "eligible": eligible}


@app.get("/api/polymarket/wallets/{address}/simulate")
def polymarket_wallet_simulate(address: str, bankroll: float = 100.0):
    """Simulate copying a wallet: replay its resolved positions with proportional sizing.

    For each resolved position, assume we allocated bankroll * kelly_fraction.
    Returns equity curve, total PnL, win rate, and per-trade list.
    """
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path

    _cache_db = _Path("data/wallet_cache.db")
    if not _cache_db.exists():
        raise HTTPException(status_code=404, detail="No wallet data. Run seeder first.")

    conn = _sqlite3.connect(str(_cache_db))
    conn.row_factory = _sqlite3.Row
    rows = conn.execute(
        """
        SELECT market_id, outcome, side, size_usd, pnl, closed_at
        FROM wallet_positions
        WHERE address = ? AND resolved = 1
        ORDER BY closed_at ASC
        """,
        (address.lower(),),
    ).fetchall()
    conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail="Wallet not found or no resolved positions.")

    trades = []
    equity = bankroll
    equity_curve = []
    wins = 0
    total_invested = 0.0

    for row in rows:
        original_size = float(row["size_usd"])
        original_pnl = float(row["pnl"])
        if original_size <= 0:
            continue

        # Scale position proportionally: if wallet bet X, we bet bankroll * (X / bankroll_assumed)
        # Use Kelly-proportional scaling: our bet = bankroll * (original_size / 500)
        # Cap at 10% of current equity
        fraction = min(original_size / 500.0, 0.10)
        bet_size = round(equity * fraction, 2)
        if bet_size < 0.01:
            continue

        # PnL ratio from original trade
        pnl_ratio = original_pnl / original_size
        our_pnl = round(bet_size * pnl_ratio, 4)

        equity += our_pnl
        total_invested += bet_size
        if our_pnl > 0:
            wins += 1

        from datetime import datetime, timezone as _tz
        closed_dt = datetime.fromtimestamp(float(row["closed_at"]), tz=_tz.utc)

        trades.append({
            "date": closed_dt.strftime("%Y-%m-%d"),
            "market_id": row["market_id"][:14] + "…",
            "outcome": row["outcome"],
            "side": row["side"],
            "bet_usd": bet_size,
            "pnl": our_pnl,
            "equity": round(equity, 2),
        })
        equity_curve.append({"date": closed_dt.strftime("%m/%d"), "equity": round(equity, 2)})

    total_pnl = round(equity - bankroll, 2)
    win_rate = round(wins / len(trades), 4) if trades else 0.0
    roi = round(total_pnl / bankroll * 100, 2)

    return {
        "address": address,
        "bankroll": bankroll,
        "total_trades": len(trades),
        "wins": wins,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "final_equity": round(equity, 2),
        "roi_pct": roi,
        "equity_curve": equity_curve[-90:],  # last 90 data points
        "trades": trades[-50:],              # last 50 trades
    }


@app.post("/api/polymarket/wallets/{address}/follow")
def polymarket_wallet_follow(address: str):
    """Mark a wallet as followed — the trading loop will consider its copy signals."""
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path

    _cache_db = _Path("data/wallet_cache.db")
    conn = _sqlite3.connect(str(_cache_db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS followed_wallets (
            address TEXT PRIMARY KEY,
            followed_at REAL NOT NULL
        )
    """)
    import time as _time
    conn.execute(
        "INSERT OR IGNORE INTO followed_wallets (address, followed_at) VALUES (?, ?)",
        (address.lower(), _time.time()),
    )
    conn.commit()
    conn.close()
    return {"status": "following", "address": address}


@app.delete("/api/polymarket/wallets/{address}/follow")
def polymarket_wallet_unfollow(address: str):
    """Unfollow a wallet."""
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path

    _cache_db = _Path("data/wallet_cache.db")
    if not _cache_db.exists():
        return {"status": "not_following", "address": address}
    conn = _sqlite3.connect(str(_cache_db))
    conn.execute("DELETE FROM followed_wallets WHERE address = ?", (address.lower(),))
    conn.commit()
    conn.close()
    return {"status": "unfollowed", "address": address}


@app.get("/api/polymarket/wallets/followed")
def polymarket_wallets_followed():
    """Return list of followed wallet addresses."""
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path

    _cache_db = _Path("data/wallet_cache.db")
    if not _cache_db.exists():
        return {"followed": []}
    try:
        conn = _sqlite3.connect(str(_cache_db))
        rows = conn.execute(
            "SELECT address, followed_at FROM followed_wallets ORDER BY followed_at DESC"
        ).fetchall()
        conn.close()
        return {"followed": [{"address": r[0], "followed_at": r[1]} for r in rows]}
    except Exception:
        return {"followed": []}


# ---------------------------------------------------------------------------
# Crypto trading endpoints — consumed by autotrader-hub frontend
# ---------------------------------------------------------------------------

def _crypto_conn():
    """Return a row-factory sqlite3 connection to the crypto ledger."""
    import sqlite3 as _sq
    from core.crypto_ledger import connect_default, init_crypto_db
    conn = connect_default()
    init_crypto_db(conn)
    return conn


@app.get("/api/crypto/status")
def crypto_status():
    """Return current crypto bot mode, balance and open position count."""
    import os as _os
    from core.crypto_ledger import get_balance_estimate, get_open_positions
    mode = _os.getenv("CRYPTO_MODE", "paper")
    conn = _crypto_conn()
    try:
        positions = get_open_positions(conn, mode)
        balance = get_balance_estimate(conn, mode)
    finally:
        conn.close()
    return {
        "mode": mode,
        "active": True,
        "balance_usd": round(balance, 2),
        "open_positions": len(positions),
    }


@app.get("/api/crypto/positions")
def crypto_positions():
    """Return all currently open positions."""
    import os as _os
    from core.crypto_ledger import get_open_positions
    mode = _os.getenv("CRYPTO_MODE", "paper")
    conn = _crypto_conn()
    try:
        rows = get_open_positions(conn, mode)
    finally:
        conn.close()
    return {
        "positions": [
            {
                "id": p.id,
                "symbol": p.symbol,
                "side": p.side,
                "entry_price": p.entry_price,
                "qty_usd": p.qty,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "opened_at": p.opened_at,
                "mode": p.mode,
            }
            for p in rows
        ]
    }


@app.get("/api/crypto/trades")
def crypto_trades(limit: int = 50, mode: str = "paper"):
    """Return recent closed trades."""
    conn = _crypto_conn()
    try:
        rows = conn.execute(
            """
            SELECT id, symbol, side, entry_price, exit_price, qty_usd,
                   realized_pnl, pnl_pct, opened_at, closed_at, exit_reason, mode
            FROM crypto_trades
            WHERE mode = ?
            ORDER BY closed_at DESC
            LIMIT ?
            """,
            (mode, limit),
        ).fetchall()
    finally:
        conn.close()
    return {
        "trades": [
            {
                "id": r[0],
                "symbol": r[1],
                "side": r[2],
                "entry_price": r[3],
                "exit_price": r[4],
                "qty_usd": r[5],
                "pnl": round(r[6], 4),
                "pnl_pct": round(r[7] * 100, 2),
                "opened_at": r[8],
                "closed_at": r[9],
                "reason": r[10],
                "mode": r[11],
            }
            for r in rows
        ]
    }


@app.get("/api/crypto/pnl")
def crypto_pnl(mode: str = "paper"):
    """Return PnL summary: total, today, win rate, trade count."""
    conn = _crypto_conn()
    try:
        rows = conn.execute(
            "SELECT realized_pnl, pnl_pct, closed_at FROM crypto_trades WHERE mode = ?",
            (mode,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"total_pnl": 0.0, "today_pnl": 0.0, "win_rate": 0.0, "trade_count": 0}

    import time as _time
    day_start = _time.time() - 86400
    total_pnl = sum(r[0] for r in rows)
    today_pnl = sum(r[0] for r in rows if r[2] >= day_start)
    wins = sum(1 for r in rows if r[0] > 0)
    return {
        "total_pnl": round(total_pnl, 4),
        "today_pnl": round(today_pnl, 4),
        "win_rate": round(wins / len(rows) * 100, 1),
        "trade_count": len(rows),
    }


@app.get("/api/crypto/balance")
def crypto_balance():
    """Return Binance account USDT balance (live) or ledger estimate (paper)."""
    import os as _os
    mode = _os.getenv("CRYPTO_MODE", "paper")
    if mode == "live":
        try:
            from core.crypto_live_executor import get_account_balance
            usdt = get_account_balance("USDT")
            return {"mode": "live", "usdt": round(usdt, 2), "source": "binance"}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))
    from core.crypto_ledger import get_balance_estimate
    conn = _crypto_conn()
    try:
        bal = get_balance_estimate(conn, "paper")
    finally:
        conn.close()
    return {"mode": "paper", "usdt": round(bal, 2), "source": "ledger"}


@app.post("/api/crypto/mode")
def crypto_set_mode(body: dict):
    """Switch bot mode between paper and live (writes CRYPTO_MODE to .env)."""
    new_mode = body.get("mode", "").lower()
    if new_mode not in ("paper", "live"):
        raise HTTPException(status_code=400, detail="mode must be 'paper' or 'live'")
    env_path = ".env"
    try:
        with open(env_path, "r") as f:
            content = f.read()
        if "CRYPTO_MODE=" in content:
            lines = [
                f"CRYPTO_MODE={new_mode}" if l.startswith("CRYPTO_MODE=") else l
                for l in content.splitlines()
            ]
            new_content = "\n".join(lines) + "\n"
        else:
            new_content = content + f"\nCRYPTO_MODE={new_mode}\n"
        with open(env_path, "w") as f:
            f.write(new_content)
        import os as _os
        _os.environ["CRYPTO_MODE"] = new_mode
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"mode": new_mode, "message": f"Switched to {new_mode} mode. Restart loop to apply."}


@app.post("/api/crypto/kill")
def crypto_kill():
    """Drop the kill-switch file to stop the crypto loop gracefully."""
    from pathlib import Path as _Path
    kill_file = _Path("data/CRYPTO_KILL")
    kill_file.parent.mkdir(parents=True, exist_ok=True)
    kill_file.touch()
    return {"killed": True, "message": "Kill-switch activated. Loop will stop after current iteration."}


@app.delete("/api/crypto/kill")
def crypto_unkill():
    """Remove the kill-switch file to allow the loop to start."""
    from pathlib import Path as _Path
    kill_file = _Path("data/CRYPTO_KILL")
    if kill_file.exists():
        kill_file.unlink()
    return {"killed": False, "message": "Kill-switch removed. Loop can now start."}


# ---------------------------------------------------------------------------
# Crypto strategies, backtest, and market scan
# ---------------------------------------------------------------------------

# All supported pairs for the multi-pair scanner
_CRYPTO_PAIRS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "XRPUSDT", "ADAUSDT", "AVAXUSDT", "DOGEUSDT",
    "DOTUSDT", "LINKUSDT", "MATICUSDT", "UNIUSDT",
]


@app.get("/api/crypto/strategies")
def crypto_strategies():
    """Return list of available trading strategies with metadata."""
    from core.crypto_strategy_engine import list_strategies
    strats = list_strategies()
    return {
        "strategies": [
            {
                "name": s.name,
                "label": s.label,
                "description": s.description,
                "default_params": s.default_params,
            }
            for s in strats
        ]
    }


@app.get("/api/crypto/signals")
def crypto_signals(strategy: str = "combined"):
    """Return current signals for all supported pairs using the given strategy."""
    from core.crypto_data_engine import fetch_candles, fetch_ticker_price
    from core.crypto_strategy_engine import run_strategy
    results = []
    for symbol in _CRYPTO_PAIRS:
        try:
            candles = fetch_candles(symbol, "15m", 100)
            sig = run_strategy(strategy, candles)
            price = candles[-1].close if candles else 0.0
            results.append({
                "symbol": symbol,
                "price": price,
                "direction": sig.direction,
                "confidence": sig.confidence,
                "reason": sig.reason,
                "entry_price": sig.entry_price,
                "stop_loss": sig.stop_loss,
                "take_profit": sig.take_profit,
                "indicators": sig.indicators,
            })
        except Exception as exc:
            results.append({"symbol": symbol, "error": str(exc), "direction": "flat"})
    return {"strategy": strategy, "signals": results, "timestamp": __import__("time").time()}


@app.post("/api/crypto/backtest")
def crypto_backtest(body: dict):
    """
    Run a walk-forward backtest of a strategy on a given symbol.

    Body:
        symbol: e.g. "BTCUSDT"
        strategy: strategy name
        interval: candle interval e.g. "1h", "4h", "1d"
        limit: number of candles (max 1000)
        params: optional strategy param overrides
        initial_balance: USD starting capital (default 1000)
        min_confidence: minimum signal confidence (default 0.60)
    """
    from core.crypto_data_engine import fetch_candles
    from core.crypto_strategy_engine import backtest as run_backtest

    symbol = body.get("symbol", "BTCUSDT").upper()
    strategy = body.get("strategy", "combined")
    interval = body.get("interval", "1h")
    limit = min(int(body.get("limit", 500)), 1000)
    params = body.get("params")
    initial_balance = float(body.get("initial_balance", 1000.0))
    min_confidence = float(body.get("min_confidence", 0.60))

    try:
        candles = fetch_candles(symbol, interval, limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Binance data fetch failed: {exc}")

    if len(candles) < 70:
        raise HTTPException(status_code=400, detail=f"Not enough candles ({len(candles)}) for backtest — need ≥70")

    result = run_backtest(strategy, candles, params, initial_balance, min_confidence=min_confidence)

    return {
        "strategy": result.strategy,
        "symbol": symbol,
        "interval": interval,
        "candle_count": result.candle_count,
        "initial_balance": result.initial_balance,
        "final_balance": result.final_balance,
        "total_return_pct": result.total_return_pct,
        "win_rate": result.win_rate,
        "max_drawdown_pct": result.max_drawdown_pct,
        "sharpe_ratio": result.sharpe_ratio,
        "profit_factor": result.profit_factor,
        "avg_trade_pct": result.avg_trade_pct,
        "trade_count": len(result.trades),
        "equity_curve": result.equity_curve,
        "trades": [
            {
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "entry_idx": t.entry_idx,
                "exit_idx": t.exit_idx,
                "pnl_pct": t.pnl_pct,
                "pnl_usd": t.pnl_usd,
                "size_usd": t.size_usd,
                "reason": t.reason,
            }
            for t in result.trades
        ],
    }


@app.get("/api/crypto/scan")
def crypto_market_scan(strategy: str = "combined", interval: str = "15m"):
    """Scan all supported pairs and return ranked signals + key indicators."""
    from core.crypto_data_engine import fetch_candles
    from core.crypto_strategy_engine import run_strategy
    from core.crypto_indicators import calculate_rsi, calculate_macd
    from core.crypto_signal_engine import calculate_atr
    import math as _math

    results = []
    for symbol in _CRYPTO_PAIRS:
        try:
            candles = fetch_candles(symbol, interval, 100)
            closes = [c.close for c in candles]
            sig = run_strategy(strategy, candles)

            rsi_vals = calculate_rsi(closes, 14)
            rsi = rsi_vals[-1] if rsi_vals and not _math.isnan(rsi_vals[-1]) else 50.0
            _, _, hist = calculate_macd(closes, 12, 26, 9)
            macd_hist = hist[-1] if hist and not _math.isnan(hist[-1]) else 0.0
            atr = calculate_atr(candles, 14)
            price = closes[-1]
            change_24h = (price - closes[0]) / closes[0] * 100 if closes[0] > 0 else 0.0

            results.append({
                "symbol": symbol,
                "price": round(price, 6),
                "change_24h_pct": round(change_24h, 2),
                "direction": sig.direction,
                "confidence": sig.confidence,
                "reason": sig.reason,
                "rsi": round(rsi, 2),
                "macd_hist": round(macd_hist, 6),
                "atr": round(atr, 6),
                "atr_pct": round(atr / price * 100, 3),
                "stop_loss": sig.stop_loss,
                "take_profit": sig.take_profit,
            })
        except Exception as exc:
            results.append({"symbol": symbol, "error": str(exc), "direction": "flat", "confidence": 0.0})

    # Sort: non-flat first, then by confidence desc
    results.sort(key=lambda r: (0 if r.get("direction") != "flat" else 1, -r.get("confidence", 0)))
    return {"strategy": strategy, "interval": interval, "pairs": results, "timestamp": __import__("time").time()}


@app.get("/api/crypto/indicators/{symbol}")
def crypto_indicators(symbol: str, interval: str = "15m", limit: int = 100):
    """Return full indicator snapshot for a single symbol."""
    from core.crypto_data_engine import fetch_candles
    from core.crypto_indicators import calculate_rsi, calculate_macd, calculate_ema
    from core.crypto_signal_engine import calculate_atr
    import math as _math

    symbol = symbol.upper()
    try:
        candles = fetch_candles(symbol, interval, limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]

    rsi_vals = calculate_rsi(closes, 14)
    rsi = rsi_vals[-1] if rsi_vals and not _math.isnan(rsi_vals[-1]) else 50.0

    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)
    macd_line, sig_line, hist = calculate_macd(closes, 12, 26, 9)
    atr = calculate_atr(candles, 14)

    avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 1.0
    rel_vol = volumes[-1] / (avg_vol + 1e-9) if avg_vol > 0 else 1.0

    return {
        "symbol": symbol,
        "interval": interval,
        "price": closes[-1] if closes else 0.0,
        "rsi": round(rsi, 2),
        "rsi_signal": "buy" if rsi < 30 else "sell" if rsi > 70 else "neutral",
        "ema20": round(ema20[-1], 6) if ema20 and not _math.isnan(ema20[-1]) else None,
        "ema50": round(ema50[-1], 6) if ema50 and not _math.isnan(ema50[-1]) else None,
        "ma_signal": "buy" if (not _math.isnan(ema20[-1]) and not _math.isnan(ema50[-1]) and ema20[-1] > ema50[-1]) else "sell",
        "macd": round(macd_line[-1], 6) if macd_line and not _math.isnan(macd_line[-1]) else None,
        "macd_signal": round(sig_line[-1], 6) if sig_line and not _math.isnan(sig_line[-1]) else None,
        "macd_hist": round(hist[-1], 6) if hist and not _math.isnan(hist[-1]) else None,
        "macd_signal_label": "buy" if (hist and not _math.isnan(hist[-1]) and hist[-1] > 0) else "sell",
        "atr": round(atr, 6),
        "atr_pct": round(atr / closes[-1] * 100, 3) if closes[-1] > 0 else 0.0,
        "volume": round(volumes[-1], 2) if volumes else 0.0,
        "relative_volume": round(rel_vol, 3),
        "volume_signal": "buy" if rel_vol > 1.5 else "sell" if rel_vol < 0.5 else "neutral",
        "ohlcv": [
            {"t": c.timestamp, "o": c.open, "h": c.high, "l": c.low, "c": c.close, "v": c.volume}
            for c in candles[-50:]
        ],
    }
