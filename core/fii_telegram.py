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


def _delta_str(delta: float | None) -> str:
    if delta is None:
        return "—"
    if delta >= 0:
        return f"▲{delta:.1f}"
    return f"▼{abs(delta):.1f}"


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
    score_delta_30d: float | None = None,
    macro_line: str = "",
) -> None:
    """Alert when FII score crosses BUY threshold."""
    icon = _sector_icon(setor)
    delta = score - score_prev
    delta_str = f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"
    momentum = f"  📊 Momentum 30d: <b>{_delta_str(score_delta_30d)} pts</b>" if score_delta_30d is not None else ""

    text = (
        f"🟢 <b>OPORTUNIDADE FII</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Ticker: <b>{ticker}</b> — {nome}\n"
        f"{icon} Setor: <b>{setor}</b>\n"
        f"⭐ Score: <b>{score:.1f}/100</b> ({delta_str} pts){momentum}\n"
        f"💰 DY (12m): <b>{dy*100:.1f}%</b>\n"
        f"📐 P/VP: <b>{pvp:.2f}</b>\n"
        f"💵 Preço: <b>R$ {price:.2f}</b>\n"
        f"📈 Renda: {income_score:.0f} | Valuation: {valuation_score:.0f} | Risco: {risk_score:.0f}\n"
        + (f"{macro_line}\n" if macro_line else "")
        + f"✅ Gatilho: <i>{trigger}</i>\n"
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
    score_delta_30d: float | None = None,
    macro_line: str = "",
) -> None:
    """Alert when FII score drops below EXIT threshold or deteriorates sharply."""
    icon = _sector_icon(setor)
    delta = score - score_prev
    momentum = f"  📊 Momentum 30d: <b>{_delta_str(score_delta_30d)} pts</b>" if score_delta_30d is not None else ""

    text = (
        f"🔴 <b>DETERIORAÇÃO FII</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Ticker: <b>{ticker}</b> — {nome}\n"
        f"{icon} Setor: <b>{setor}</b>\n"
        f"⭐ Score: <b>{score:.1f}/100</b> ({delta:.1f} pts){momentum}\n"
        f"💰 DY (12m): <b>{dy*100:.1f}%</b>\n"
        f"📐 P/VP: <b>{pvp:.2f}</b>\n"
        f"💵 Preço: <b>R$ {price:.2f}</b>\n"
        + (f"{macro_line}\n" if macro_line else "")
        + f"⚠️ Gatilho: <i>{trigger}</i>\n"
        f"⏰ {time.strftime('%d/%m/%Y %H:%M')}"
    )
    send_message(text)


def notify_fii_ranking(
    ranked: list[dict],
    top_n: int = 5,
    sector_map: dict[str, str] | None = None,
    score_deltas: dict[str, float | None] | None = None,
    macro_line: str = "",
) -> None:
    """Send daily top-N overall ranking + per-sector top-3 breakdown."""
    deltas = score_deltas or {}
    smap = sector_map or {}

    # --- Overall top-N ---
    lines = [
        f"📋 <b>TOP {top_n} FIIs — AlphaCota</b>",
        "━━━━━━━━━━━━━━━━━━━",
    ]
    for i, fii in enumerate(ranked[:top_n], 1):
        ticker = fii.get("ticker", "?")
        score = fii.get("alpha_score", 0.0)
        dy = fii.get("dividend_yield", 0.0)
        pvp = fii.get("pvp", 1.0)
        d30 = deltas.get(ticker)
        emoji = _score_emoji(score)
        momentum = f" {_delta_str(d30)}" if d30 is not None else ""
        lines.append(
            f"{i}. {emoji} <b>{ticker}</b>  Score: <b>{score:.0f}</b>{momentum}"
            f"  DY: {dy*100:.1f}%  P/VP: {pvp:.2f}"
        )

    # --- Per-sector top-3 ---
    if smap and ranked:
        sectors: dict[str, list[dict]] = {}
        for fii in ranked:
            sec = smap.get(fii.get("ticker", ""), "Outros")
            sectors.setdefault(sec, []).append(fii)

        # Only sectors with ≥ 2 FIIs
        relevant = {s: fiis for s, fiis in sectors.items() if len(fiis) >= 2}
        if relevant:
            lines.append("")
            lines.append("🏆 <b>Top por setor</b>")
            for sec, fiis in sorted(relevant.items()):
                top3 = fiis[:3]
                icon = _sector_icon(sec)
                entries = "  ".join(
                    f"<b>{f['ticker']}</b> {f['alpha_score']:.0f}" for f in top3
                )
                lines.append(f"{icon} <b>{sec}</b>: {entries}")

    if macro_line:
        lines.append("")
        lines.append(macro_line)
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


def notify_coverage_health(stats: dict, sector_breakdown: dict[str, int] | None = None) -> None:
    """Send weekly universe coverage health dashboard to Telegram.

    Args:
        stats:            Output of get_registry_stats() — total, ativos, ifix_count,
                          yahoo_ok, yahoo_broken, last_validated.
        sector_breakdown: Optional dict setor → count for the 'Outros' breakdown.
    """
    total        = stats.get("total", 0)
    ativos       = stats.get("ativos", 0) or 0
    ifix_count   = stats.get("ifix_count", 0) or 0
    yahoo_ok     = stats.get("yahoo_ok", 0) or 0
    yahoo_broken = stats.get("yahoo_broken", 0) or 0
    last_val     = stats.get("last_validated", "—") or "—"

    outros = sector_breakdown.get("Outros", 0) if sector_breakdown else 0
    classified = ativos - outros

    lines = [
        "📡 <b>Coverage Health — AlphaCota FII</b>",
        "━━━━━━━━━━━━━━━━━━━",
        f"🏦 Universo total: <b>{total}</b> FIIs registrados",
        f"✅ Ativos: <b>{ativos}</b>  (IFIX: {ifix_count})",
        f"📊 Yahoo Finance OK: <b>{yahoo_ok}</b>",
    ]
    if yahoo_broken:
        lines.append(f"⚠️ Yahoo sem dados: <b>{yahoo_broken}</b>")
    lines.append(f"🗂️ Setor classificado: <b>{classified}/{ativos}</b>")
    if outros:
        lines.append(f"❓ Setor desconhecido ('Outros'): <b>{outros}</b>")

    if sector_breakdown:
        top_sectors = sorted(
            [(s, c) for s, c in sector_breakdown.items() if s != "Outros"],
            key=lambda x: -x[1],
        )[:6]
        if top_sectors:
            lines.append("")
            lines.append("🏷️ <b>FIIs por setor</b>")
            for setor, count in top_sectors:
                lines.append(f"  {setor}: {count}")
            if outros:
                lines.append(f"  Outros: {outros}")

    lines.append(f"📅 Validado: {last_val}  ⏰ {time.strftime('%d/%m/%Y %H:%M')}")
    send_message("\n".join(lines))
