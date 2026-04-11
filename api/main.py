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
