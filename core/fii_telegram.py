"""
core/fii_telegram.py — Telegram alert templates for FII signals.

Fire-and-forget via daemon thread. Never crashes the loop.

Environment variables (shared with crypto_telegram):
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID
"""

from __future__ import annotations

import os
import threading
import time

import httpx

from core.logger import logger

_API = "https://api.telegram.org"
_TIMEOUT = 8.0


def _token() -> str | None:
    return os.getenv("TELEGRAM_BOT_TOKEN")


def _chat_id() -> str | None:
    return os.getenv("TELEGRAM_CHAT_ID")


def _enabled() -> bool:
    return bool(_token() and _chat_id())


def _do_send(text: str) -> None:
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                f"{_API}/bot{_token()}/sendMessage",
                json={"chat_id": _chat_id(), "text": text, "parse_mode": "HTML"},
            )
            if not resp.is_success:
                logger.warning("fii_telegram: send failed %s — %s", resp.status_code, resp.text[:120])
    except Exception as exc:
        logger.warning("fii_telegram: send error — %s", exc)


def send_message(text: str) -> bool:
    if not _enabled():
        return False
    t = threading.Thread(target=_do_send, args=(text,), daemon=True)
    t.start()
    return True


def _score_emoji(score: float) -> str:
    if score >= 72:
        return "🟢"
    if score >= 55:
        return "🟡"
    return "🔴"


def _sector_icon(setor: str) -> str:
    icons = {
        "Papel (CRI)": "📄",
        "Logística": "🏭",
        "Shopping": "🛍",
        "Lajes Corp.": "🏢",
        "Fundo de Fundos": "📦",
        "Híbrido": "🔀",
        "Agro": "🌾",
        "Saúde": "🏥",
        "Residencial": "🏠",
        "Educacional": "🎓",
    }
    return icons.get(setor, "📊")


def notify_fii_buy(
    ticker: str,
    nome: str,
    setor: str,
    score: float,
    score_prev: float,
    dy: float,
    pvp: float,
    price: float,
    income_score: float,
    valuation_score: float,
    risk_score: float,
    trigger: str,
) -> None:
    """Alert when FII score crosses BUY threshold."""
    icon = _sector_icon(setor)
    delta = score - score_prev
    delta_str = f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"

    text = (
        f"🟢 <b>OPORTUNIDADE FII</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Ticker: <b>{ticker}</b> — {nome}\n"
        f"{icon} Setor: <b>{setor}</b>\n"
        f"⭐ Score: <b>{score:.1f}/100</b> ({delta_str} pts)\n"
        f"💰 DY (12m): <b>{dy*100:.1f}%</b>\n"
        f"📐 P/VP: <b>{pvp:.2f}</b>\n"
        f"💵 Preço: <b>R$ {price:.2f}</b>\n"
        f"📈 Renda: {income_score:.0f} | Valuation: {valuation_score:.0f} | Risco: {risk_score:.0f}\n"
        f"✅ Gatilho: <i>{trigger}</i>\n"
        f"⏰ {time.strftime('%d/%m/%Y %H:%M')}"
    )
    send_message(text)


def notify_fii_sell(
    ticker: str,
    nome: str,
    setor: str,
    score: float,
    score_prev: float,
    dy: float,
    pvp: float,
    price: float,
    trigger: str,
) -> None:
    """Alert when FII score drops below EXIT threshold or deteriorates sharply."""
    icon = _sector_icon(setor)
    delta = score - score_prev
    delta_str = f"{delta:.1f}"

    text = (
        f"🔴 <b>DETERIORAÇÃO FII</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Ticker: <b>{ticker}</b> — {nome}\n"
        f"{icon} Setor: <b>{setor}</b>\n"
        f"⭐ Score: <b>{score:.1f}/100</b> ({delta_str} pts)\n"
        f"💰 DY (12m): <b>{dy*100:.1f}%</b>\n"
        f"📐 P/VP: <b>{pvp:.2f}</b>\n"
        f"💵 Preço: <b>R$ {price:.2f}</b>\n"
        f"⚠️ Gatilho: <i>{trigger}</i>\n"
        f"⏰ {time.strftime('%d/%m/%Y %H:%M')}"
    )
    send_message(text)


def notify_fii_ranking(ranked: list[dict], top_n: int = 5) -> None:
    """Send daily top-N FII ranking."""
    lines = [
        f"📋 <b>TOP {top_n} FIIs — AlphaCota</b>",
        "━━━━━━━━━━━━━━━━━━━",
    ]
    for i, fii in enumerate(ranked[:top_n], 1):
        ticker = fii.get("ticker", "?")
        score = fii.get("alpha_score", 0.0)
        dy = fii.get("dividend_yield", 0.0)
        pvp = fii.get("pvp", 1.0)
        emoji = _score_emoji(score)
        lines.append(
            f"{i}. {emoji} <b>{ticker}</b>  Score: <b>{score:.0f}</b>  "
            f"DY: {dy*100:.1f}%  P/VP: {pvp:.2f}"
        )
    lines.append(f"📅 {time.strftime('%d/%m/%Y %H:%M')}")
    send_message("\n".join(lines))


def notify_fii_loop_error(error: str) -> None:
    """Alert on repeated FII loop failures."""
    text = (
        f"⚠️ <b>FII LOOP ERRO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"❌ {error}\n"
        f"⏰ {time.strftime('%d/%m/%Y %H:%M')}"
    )
    send_message(text)
