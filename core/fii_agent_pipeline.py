"""
core/fii_agent_pipeline.py

Pipeline multi-agente para análise profunda de FIIs.

Inspirado na arquitetura do QuantAgent (MIT) e nos conceitos do FinceptTerminal:
  QuantAgent:  Indicator → Pattern  → Trend   → Decision
  AlphaCota:  Macro     → Fundament → Risk    → Persona → Decision

Cada agente recebe saída do anterior como contexto, tem prompt focado
(500-800 tokens) e retorna JSON estruturado. Resultado final inclui
raciocínio auditável por etapa + recomendação sintetizada.

Uso:
    from core.fii_agent_pipeline import run_deep_analysis
    result = run_deep_analysis(ticker, fii_data, macro, news)
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from core.logger import logger

try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False

# ---------------------------------------------------------------------------
# Shared state — passed through the pipeline
# ---------------------------------------------------------------------------

@dataclass
class PipelineState:
    ticker: str
    fii_data: dict[str, Any]           # fundamentals, score, price, dividends
    macro: dict[str, Any]              # selic, cdi, ipca, premio_risco
    news: list[dict[str, Any]]         # [{"titulo": ..., "data": ...}]

    # Outputs — filled by each agent in sequence
    macro_analysis: dict[str, Any] = field(default_factory=dict)
    fundamental_analysis: dict[str, Any] = field(default_factory=dict)
    risk_analysis: dict[str, Any] = field(default_factory=dict)
    persona_analysis: dict[str, Any] = field(default_factory=dict)
    final_decision: dict[str, Any] = field(default_factory=dict)

    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Groq helper
# ---------------------------------------------------------------------------

def _call_groq(
    messages: list[dict],
    api_key: str | None = None,
    model: str = "llama-3.3-70b-versatile",
    max_tokens: int = 900,
    temperature: float = 0.3,
) -> str:
    """Single Groq call. Returns raw response text."""
    if not HAS_GROQ:
        raise RuntimeError("groq package not installed")
    key = api_key or os.getenv("GROQ_API_KEY", "")
    if not key:
        raise RuntimeError("GROQ_API_KEY not configured")

    client = Groq(api_key=key)
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


def _parse_json(text: str) -> dict:
    """Extract and parse the first JSON object found in text."""
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in response")
    return json.loads(match.group(0))


# ---------------------------------------------------------------------------
# Agent 1 — MacroAgent
# Analisa contexto macro (SELIC, CDI, IPCA) e o que significa para FIIs
# ---------------------------------------------------------------------------

def macro_agent(state: PipelineState, api_key: str | None = None) -> None:
    macro = state.macro
    selic = macro.get("selic_anual", 10.75)
    cdi = macro.get("cdi_anual", 10.65)
    ipca = macro.get("ipca_anual", 4.83)
    premio = macro.get("premio_risco", selic - ipca)

    dy = state.fii_data.get("fundamentals", {}).get("dividend_yield", 0.0)
    dy_pct = round(dy * 100, 2) if dy < 1 else round(dy, 2)
    spread = round(dy_pct - cdi, 2)

    prompt = f"""Você é um economista especialista em mercado imobiliário brasileiro.

Contexto macro atual:
- SELIC: {selic}% a.a.
- CDI: {cdi}% a.a.
- IPCA (12m): {ipca}% a.a.
- Prêmio real (SELIC - IPCA): {premio:.2f}%

FII analisado: {state.ticker}
- Dividend Yield atual: {dy_pct}% a.a.
- Spread sobre CDI: {spread:+.2f}%

Responda SOMENTE em JSON com estas chaves:
{{
  "ciclo_juros": "alta|estavel|queda",
  "impacto_fii": "positivo|neutro|negativo",
  "spread_atrativo": true/false,
  "dy_real": {round(dy_pct - ipca, 2)},
  "yield_minimo_aceitavel": <float % que um FII deve pagar hoje para valer vs CDI>,
  "contexto": "<2 frases explicando o momento macro e o que significa para FIIs de papel vs tijolo>",
  "alerta": "<1 frase se há algum risco macro relevante, ou null>"
}}"""

    try:
        raw = _call_groq(
            [
                {"role": "system", "content": "Você é um economista especializado em FIIs brasileiros. Responda apenas JSON válido."},
                {"role": "user", "content": prompt},
            ],
            api_key=api_key,
            max_tokens=400,
        )
        state.macro_analysis = _parse_json(raw)
        # Ensure computed dy_real is accurate (not hallucinated)
        state.macro_analysis["dy_real"] = round(dy_pct - ipca, 2)
        state.macro_analysis["spread_cdi"] = spread
        logger.info("[pipeline:%s] MacroAgent OK", state.ticker)
    except Exception as exc:
        logger.warning("[pipeline:%s] MacroAgent failed: %s", state.ticker, exc)
        state.errors.append(f"MacroAgent: {exc}")
        state.macro_analysis = {
            "ciclo_juros": "estavel",
            "impacto_fii": "neutro",
            "spread_atrativo": spread > 1.5,
            "dy_real": round(dy_pct - ipca, 2),
            "spread_cdi": spread,
            "contexto": f"SELIC {selic}%, IPCA {ipca}%, spread do FII vs CDI: {spread:+.2f}%.",
            "alerta": None,
        }


# ---------------------------------------------------------------------------
# Agent 2 — FundamentalAgent
# Analisa fundamentos + calcula DDM (Dividend Discount Model)
# ---------------------------------------------------------------------------

def fundamental_agent(state: PipelineState, api_key: str | None = None) -> None:
    fund = state.fii_data.get("fundamentals", {})
    score = state.fii_data.get("score_breakdown", {})
    price = state.fii_data.get("price", 0.0)

    dy = fund.get("dividend_yield", 0.0)
    dy_pct = round(dy * 100, 2) if dy < 1 else round(dy, 2)
    pvp = fund.get("pvp", 1.0)
    vacancia = fund.get("vacancia", fund.get("vacancy_rate", 0.05))
    vacancia_pct = round(vacancia * 100 if vacancia < 1 else vacancia, 1)
    alpha_score = score.get("total", score.get("alpha_score", 0))
    div_consistency = fund.get("dividend_consistency", 50.0)
    macro = state.macro_analysis

    # DDM: preço justo = dividendo_mensal / (taxa_desconto_mensal)
    # taxa_desconto = CDI + spread_risco_imobiliario (2%)
    cdi = state.macro.get("cdi_anual", 10.65)
    taxa_desconto_anual = (cdi + 2.0) / 100
    taxa_desconto_mensal = (1 + taxa_desconto_anual) ** (1 / 12) - 1
    div_mensal = state.fii_data.get("dividend_monthly", 0.0)
    ddm_preco_justo = round(div_mensal / taxa_desconto_mensal, 2) if taxa_desconto_mensal > 0 and div_mensal > 0 else None
    ddm_upside = round((ddm_preco_justo / price - 1) * 100, 1) if ddm_preco_justo and price > 0 else None

    prompt = f"""Você é um analista de FIIs especializado em análise fundamentalista.

Contexto macro: {macro.get('contexto', '')}
Ciclo de juros: {macro.get('ciclo_juros', 'estavel')}

FII: {state.ticker}
- AlphaScore: {alpha_score}/100
- P/VP: {pvp} (< 1.0 = desconto, > 1.2 = prêmio)
- Dividend Yield: {dy_pct}% a.a.
- Consistência dividendos (0-100): {div_consistency}
- Vacância: {vacancia_pct}%
- Preço atual: R$ {price:.2f}
- Preço justo DDM: R$ {ddm_preco_justo if ddm_preco_justo else 'N/D'} (upside: {f'{ddm_upside:+.1f}%' if ddm_upside is not None else 'N/D'})

Score detalhado: {json.dumps(score, ensure_ascii=False)}

Responda SOMENTE em JSON:
{{
  "qualidade": "excelente|boa|media|fraca",
  "pvp_status": "muito_barato|barato|justo|caro|muito_caro",
  "dy_sustentavel": true/false,
  "ddm_preco_justo": {ddm_preco_justo},
  "ddm_upside_pct": {ddm_upside},
  "pontos_fortes": ["<ponto 1>", "<ponto 2>"],
  "pontos_fracos": ["<ponto 1>"],
  "resumo": "<2 frases objetivas sobre os fundamentos deste FII>"
}}"""

    try:
        raw = _call_groq(
            [
                {"role": "system", "content": "Você é um analista fundamentalista de FIIs. Responda apenas JSON válido."},
                {"role": "user", "content": prompt},
            ],
            api_key=api_key,
            max_tokens=500,
        )
        state.fundamental_analysis = _parse_json(raw)
        # Ensure DDM values are from our calculation, not hallucinated
        state.fundamental_analysis["ddm_preco_justo"] = ddm_preco_justo
        state.fundamental_analysis["ddm_upside_pct"] = ddm_upside
        logger.info("[pipeline:%s] FundamentalAgent OK", state.ticker)
    except Exception as exc:
        logger.warning("[pipeline:%s] FundamentalAgent failed: %s", state.ticker, exc)
        state.errors.append(f"FundamentalAgent: {exc}")
        state.fundamental_analysis = {
            "qualidade": "media",
            "pvp_status": "justo" if 0.9 <= pvp <= 1.1 else ("barato" if pvp < 0.9 else "caro"),
            "dy_sustentavel": dy_pct > cdi,
            "ddm_preco_justo": ddm_preco_justo,
            "ddm_upside_pct": ddm_upside,
            "pontos_fortes": [],
            "pontos_fracos": [],
            "resumo": f"P/VP {pvp}, DY {dy_pct}%, AlphaScore {alpha_score}/100.",
        }


# ---------------------------------------------------------------------------
# Agent 3 — RiskAgent
# Analisa riscos quantitativos e qualitativos
# ---------------------------------------------------------------------------

def risk_agent(state: PipelineState, api_key: str | None = None) -> None:
    fund = state.fii_data.get("fundamentals", {})
    macro = state.macro_analysis
    fundamental = state.fundamental_analysis

    debt = fund.get("debt_ratio", fund.get("endividamento", 0.3))
    debt_pct = round(debt * 100 if debt < 1 else debt, 1)
    liquidity = fund.get("liquidez_diaria", fund.get("daily_liquidity", 5_000_000))
    liquidity_k = round(liquidity / 1000, 0)
    vacancia = fund.get("vacancia", fund.get("vacancy_rate", 0.05))
    vacancia_pct = round(vacancia * 100 if vacancia < 1 else vacancia, 1)

    # Volatilidade (from fii_data if available)
    vol_30d = state.fii_data.get("vol_30d")

    # Sensibilidade a juros: FIIs de papel (CRI) sofrem mais com alta de SELIC
    segmento = state.fii_data.get("segment", "Outros")
    juros_sensivel = any(k in segmento.lower() for k in ["papel", "cri", "cra", "recebivel"])

    prompt = f"""Você é um gestor de risco especializado em FIIs.

Contexto macro: {macro.get('contexto', '')}
Ciclo de juros: {macro.get('ciclo_juros', 'estavel')} | Alerta: {macro.get('alerta', 'nenhum')}
Fundamentos: {fundamental.get('resumo', '')}

FII: {state.ticker} | Segmento: {segmento}
- Endividamento: {debt_pct}%
- Liquidez diária: R$ {liquidity_k:,.0f}k
- Vacância: {vacancia_pct}%
- Volatilidade 30d (anualizada): {f'{vol_30d}%' if vol_30d else 'N/D'}
- Sensível a juros (FII de papel): {'SIM' if juros_sensivel else 'NÃO'}

Responda SOMENTE em JSON:
{{
  "nivel_risco": "baixo|medio|alto|muito_alto",
  "risco_liquidez": "baixo|medio|alto",
  "risco_credito": "baixo|medio|alto",
  "risco_vacancia": "baixo|medio|alto",
  "risco_juros": "baixo|medio|alto",
  "var_estimado_5pct": "<estimativa qualitativa de perda máxima em cenário adverso, ex: '-8% em 30d'>",
  "cenario_stress": "<o que acontece com este FII se SELIC subir 2pp>",
  "resumo_risco": "<2 frases objetivas sobre o perfil de risco>"
}}"""

    try:
        raw = _call_groq(
            [
                {"role": "system", "content": "Você é um gestor de risco de FIIs. Responda apenas JSON válido."},
                {"role": "user", "content": prompt},
            ],
            api_key=api_key,
            max_tokens=500,
        )
        state.risk_analysis = _parse_json(raw)
        logger.info("[pipeline:%s] RiskAgent OK", state.ticker)
    except Exception as exc:
        logger.warning("[pipeline:%s] RiskAgent failed: %s", state.ticker, exc)
        state.errors.append(f"RiskAgent: {exc}")
        state.risk_analysis = {
            "nivel_risco": "medio",
            "risco_liquidez": "medio" if liquidity < 1_000_000 else "baixo",
            "risco_credito": "medio",
            "risco_vacancia": "alto" if vacancia_pct > 15 else ("medio" if vacancia_pct > 8 else "baixo"),
            "risco_juros": "alto" if juros_sensivel else "baixo",
            "var_estimado_5pct": "N/D",
            "cenario_stress": "N/D",
            "resumo_risco": f"Endividamento {debt_pct}%, vacância {vacancia_pct}%, liquidez R${liquidity_k:,.0f}k/dia.",
        }


# ---------------------------------------------------------------------------
# Agent 4 — PersonaAgent
# Gera 2 visões de investidores (conservador Barsi-style + crescimento)
# ---------------------------------------------------------------------------

def persona_agent(state: PipelineState, api_key: str | None = None) -> None:
    macro = state.macro_analysis
    fund_a = state.fundamental_analysis
    risk_a = state.risk_analysis

    ticker = state.ticker
    dy_real = macro.get("dy_real", 0)
    spread = macro.get("spread_cdi", 0)
    pvp_status = fund_a.get("pvp_status", "justo")
    ddm_upside = fund_a.get("ddm_upside_pct")
    nivel_risco = risk_a.get("nivel_risco", "medio")
    dy_sustentavel = fund_a.get("dy_sustentavel", True)
    qualidade = fund_a.get("qualidade", "media")
    cenario_stress = risk_a.get("cenario_stress", "")

    prompt = f"""Você é dois investidores brasileiros distintos analisando o FII {ticker}.

Dados consolidados:
- Qualidade dos fundamentos: {qualidade}
- P/VP: {pvp_status}
- DY real (acima da inflação): {dy_real:+.2f}%
- Spread vs CDI: {spread:+.2f}%
- DDM upside: {f'{ddm_upside:+.1f}%' if ddm_upside is not None else 'N/D'}
- Nível de risco: {nivel_risco}
- DY sustentável: {'sim' if dy_sustentavel else 'não'}
- Stress SELIC+2pp: {cenario_stress}

PERSONA 1 — Luiz Barsi (conservador, renda passiva, longo prazo, avesso a risco):
- Foco: consistência de dividendos, segurança patrimonial, margem de segurança
- Aceita P/VP > 1 se DY for consistente e real

PERSONA 2 — Investidor Crescimento (agressivo, busca upside de preço + DY crescente):
- Foco: upside de valorização, expansão de carteira, vacância declinante
- Aceita maior risco se o upside compensar

Responda SOMENTE em JSON:
{{
  "barsi": {{
    "opiniao": "comprar|aguardar|evitar",
    "raciocinio": "<2 frases no estilo conservador de Barsi>",
    "condicao_entrada": "<o que mudaria para ele comprar/evitar>"
  }},
  "crescimento": {{
    "opiniao": "comprar|aguardar|evitar",
    "raciocinio": "<2 frases no estilo de quem busca crescimento>",
    "condicao_entrada": "<o que mudaria para ele comprar/evitar>"
  }}
}}"""

    try:
        raw = _call_groq(
            [
                {"role": "system", "content": "Você é dois investidores distintos de FIIs. Responda apenas JSON válido."},
                {"role": "user", "content": prompt},
            ],
            api_key=api_key,
            max_tokens=600,
        )
        state.persona_analysis = _parse_json(raw)
        logger.info("[pipeline:%s] PersonaAgent OK", state.ticker)
    except Exception as exc:
        logger.warning("[pipeline:%s] PersonaAgent failed: %s", state.ticker, exc)
        state.errors.append(f"PersonaAgent: {exc}")
        state.persona_analysis = {
            "barsi": {"opiniao": "aguardar", "raciocinio": "Análise indisponível.", "condicao_entrada": "N/D"},
            "crescimento": {"opiniao": "aguardar", "raciocinio": "Análise indisponível.", "condicao_entrada": "N/D"},
        }


# ---------------------------------------------------------------------------
# Agent 5 — DecisionAgent
# Sintetiza todos os agentes em recomendação final auditável
# ---------------------------------------------------------------------------

def decision_agent(state: PipelineState, api_key: str | None = None) -> None:
    macro = state.macro_analysis
    fund_a = state.fundamental_analysis
    risk_a = state.risk_analysis
    persona = state.persona_analysis

    ticker = state.ticker
    price = state.fii_data.get("price", 0.0)
    fund = state.fii_data.get("fundamentals", {})
    dy = fund.get("dividend_yield", 0.0)
    dy_pct = round(dy * 100 if dy < 1 else dy, 2)
    pvp = fund.get("pvp", 1.0)
    ddm_preco_justo = fund_a.get("ddm_preco_justo")
    ddm_upside = fund_a.get("ddm_upside_pct")

    # Notícias recentes (primeiras 3 manchetes)
    news_headlines = "\n".join(
        f"- {n.get('titulo', '')[:80]}" for n in state.news[:3]
    ) or "Sem notícias recentes."

    barsi_op = persona.get("barsi", {}).get("opiniao", "aguardar")
    crescimento_op = persona.get("crescimento", {}).get("opiniao", "aguardar")

    prompt = f"""Você é o Decision Agent de um sistema de análise de FIIs.
Sintetize os outputs de todos os agentes anteriores em uma recomendação final.

=== RESUMO DOS AGENTES ===
MACRO: {macro.get('contexto', '')} | Spread CDI: {macro.get('spread_cdi', 0):+.2f}%
FUNDAMENTOS: {fund_a.get('resumo', '')} | Qualidade: {fund_a.get('qualidade', 'media')} | P/VP: {fund_a.get('pvp_status', 'justo')}
RISCO: {risk_a.get('resumo_risco', '')} | Nível: {risk_a.get('nivel_risco', 'medio')}
PERSONAS: Barsi={barsi_op} | Crescimento={crescimento_op}

=== DADOS DO FII {ticker} ===
- Preço: R$ {price:.2f}
- P/VP: {pvp}
- DY: {dy_pct}% a.a.
- DDM Preço Justo: R$ {ddm_preco_justo if ddm_preco_justo else 'N/D'} (upside: {f'{ddm_upside:+.1f}%' if ddm_upside is not None else 'N/D'})

=== NOTÍCIAS RECENTES ===
{news_headlines}

Responda SOMENTE em JSON:
{{
  "recomendacao": "COMPRAR|AGUARDAR|EVITAR",
  "forca_sinal": "forte|moderado|fraco",
  "preco_entrada_ideal": <float ou null — preço máximo recomendado para entrada>,
  "preco_alvo_12m": <float ou null — preço alvo em 12 meses baseado em DDM>,
  "stop_sugerido": <float ou null — preço de saída em caso de deterioração>,
  "dy_alvo_minimo": <float % — DY mínimo que justifica a posição no cenário atual>,
  "tese": "<3-4 frases sintetizando toda a análise e o porquê da recomendação>",
  "gatilhos_compra": ["<condição que tornaria a compra mais clara>"],
  "gatilhos_saida": ["<condição que indicaria saída da posição>"],
  "rating": "A|B|C|D|F"
}}"""

    try:
        raw = _call_groq(
            [
                {"role": "system", "content": "Você é um analista-chefe de FIIs. Sintetize tudo em uma decisão clara. Responda apenas JSON válido."},
                {"role": "user", "content": prompt},
            ],
            api_key=api_key,
            max_tokens=700,
        )
        state.final_decision = _parse_json(raw)
        logger.info("[pipeline:%s] DecisionAgent OK → %s", state.ticker, state.final_decision.get("recomendacao"))
    except Exception as exc:
        logger.warning("[pipeline:%s] DecisionAgent failed: %s", state.ticker, exc)
        state.errors.append(f"DecisionAgent: {exc}")
        state.final_decision = {
            "recomendacao": "AGUARDAR",
            "forca_sinal": "fraco",
            "preco_entrada_ideal": None,
            "preco_alvo_12m": ddm_preco_justo,
            "stop_sugerido": None,
            "dy_alvo_minimo": round(state.macro.get("cdi_anual", 10.65) + 1.5, 2),
            "tese": "Análise parcial — alguns agentes falharam. Aguardar dados completos.",
            "gatilhos_compra": [],
            "gatilhos_saida": [],
            "rating": "C",
        }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_deep_analysis(
    ticker: str,
    fii_data: dict[str, Any],
    macro: dict[str, Any],
    news: list[dict[str, Any]],
    api_key: str | None = None,
) -> dict[str, Any]:
    """
    Executa o pipeline completo de 5 agentes e retorna análise estruturada.

    Args:
        ticker: Código do FII (ex: "HGLG11")
        fii_data: Dict retornado por /api/fii/{ticker} (price, fundamentals, score, etc.)
        macro: Dict de get_macro_snapshot()
        news: Lista de notícias [{"titulo": ..., "data": ...}]
        api_key: Groq API key (usa env var se None)

    Returns:
        Dict com macro_analysis, fundamental_analysis, risk_analysis,
        persona_analysis, final_decision, pipeline_meta.
    """
    if not HAS_GROQ:
        return {"success": False, "error": "groq package not installed"}

    state = PipelineState(
        ticker=ticker.upper(),
        fii_data=fii_data,
        macro=macro,
        news=news,
    )

    agents = [
        ("MacroAgent",       macro_agent),
        ("FundamentalAgent", fundamental_agent),
        ("RiskAgent",        risk_agent),
        ("PersonaAgent",     persona_agent),
        ("DecisionAgent",    decision_agent),
    ]

    timings: dict[str, float] = {}
    for name, fn in agents:
        t0 = time.monotonic()
        fn(state, api_key=api_key)
        timings[name] = round(time.monotonic() - t0, 2)
        # Small delay to respect Groq free-tier RPM (30 req/min)
        time.sleep(1.0)

    return {
        "success": True,
        "ticker": state.ticker,
        "macro_analysis": state.macro_analysis,
        "fundamental_analysis": state.fundamental_analysis,
        "risk_analysis": state.risk_analysis,
        "persona_analysis": state.persona_analysis,
        "final_decision": state.final_decision,
        "pipeline_meta": {
            "agents_run": len(agents),
            "errors": state.errors,
            "timings_s": timings,
            "total_s": round(sum(timings.values()), 2),
        },
    }
