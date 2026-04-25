"""
core/crypto_telegram.py — Telegram trade alert notifier for AlphaCota.

Sends real-time notifications via Telegram Bot API (raw httpx, no SDK).
All calls are fire-and-forget — failures are logged but never crash the loop.

Environment variables:
    TELEGRAM_BOT_TOKEN  — Bot token from @BotFather
    TELEGRAM_CHAT_ID    — Chat/group ID to send alerts to

Public API:
    notify_position_opened(signal, size_usd, strategy)
    notify_position_closed(trade, strategy)
    notify_circuit_breaker(reason, daily_loss)
    notify_daily_summary(pnl, trades, win_rate, balance)
    send_message(text)
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

import httpx

from core.crypto_types import CryptoSignal, CryptoTrade
from core.logger import logger

_API = "https://api.telegram.org"
_TIMEOUT = 8.0


def _token() -> str | None:
    return os.getenv("TELEGRAM_BOT_TOKEN")


def _chat_id() -> str | None:
    return os.getenv("TELEGRAM_CHAT_ID")


def _enabled() -> bool:
    return bool(_token() and _chat_id())


def _do_send(text: str, parse_mode: str) -> None:
    """Blocking HTTP call — always run in a daemon thread."""
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                f"{_API}/bot{_token()}/sendMessage",
                json={"chat_id": _chat_id(), "text": text, "parse_mode": parse_mode},
            )
            if not resp.is_success:
                logger.warning("telegram: send failed %s — %s", resp.status_code, resp.text[:120])
    except Exception as exc:
        logger.warning("telegram: send error — %s", exc)


def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """Dispatch a Telegram message in a daemon thread (true fire-and-forget).

    Returns True immediately if credentials are configured; the actual HTTP
    call runs in the background and never blocks the trading loop.
    """
    if not _enabled():
        return False
    t = threading.Thread(target=_do_send, args=(text, parse_mode), daemon=True)
    t.start()
    return True


def _direction_emoji(direction: str) -> str:
    return "🟢" if direction == "long" else "🔴" if direction == "short" else "⚪"


def _pnl_emoji(pnl: float) -> str:
    return "✅" if pnl > 0 else "❌"


def notify_position_opened(
    signal: CryptoSignal,
    size_usd: float,
    strategy: str,
    mode: str = "paper",
) -> None:
    """Alert when a new position is opened."""
    emoji = _direction_emoji(signal.direction)
    mode_tag = "📄 PAPER" if mode == "paper" else "💰 LIVE"
    pair = signal.symbol.replace("USDT", "/USDT")

    text = (
        f"{emoji} <b>POSIÇÃO ABERTA</b> {mode_tag}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Par: <b>{pair}</b>\n"
        f"📈 Direção: <b>{signal.direction.upper()}</b>\n"
        f"💵 Tamanho: <b>${size_usd:.2f}</b>\n"
        f"🎯 Entrada: <b>${signal.entry_price:,.4f}</b>\n"
        f"🛡 Stop Loss: <b>${signal.stop_loss:,.4f}</b>\n"
        f"🏆 Take Profit: <b>${signal.take_profit:,.4f}</b>\n"
        f"🤖 Estratégia: <b>{strategy}</b>\n"
        f"📉 Confiança: <b>{signal.confidence * 100:.1f}%</b>\n"
        f"📝 Razão: <i>{signal.reason}</i>\n"
        f"⏰ {time.strftime('%d/%m/%Y %H:%M:%S')}"
    )
    send_message(text)


def notify_position_closed(
    trade: CryptoTrade,
    strategy: str = "",
    mode: str = "paper",
) -> None:
    """Alert when a position is closed with realised PnL."""
    pnl_emoji = _pnl_emoji(trade.pnl)
    dir_emoji = _direction_emoji(trade.side)
    mode_tag = "📄 PAPER" if mode == "paper" else "💰 LIVE"
    pair = trade.symbol.replace("USDT", "/USDT")
    pnl_sign = "+" if trade.pnl >= 0 else ""
    pnl_pct_sign = "+" if trade.pnl_pct >= 0 else ""

    text = (
        f"{pnl_emoji} <b>POSIÇÃO FECHADA</b> {mode_tag}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Par: <b>{pair}</b>\n"
        f"{dir_emoji} Direção: <b>{trade.side.upper()}</b>\n"
        f"🎯 Entrada: <b>${trade.entry_price:,.4f}</b>\n"
        f"🏁 Saída: <b>${trade.exit_price:,.4f}</b>\n"
        f"💰 PnL: <b>{pnl_sign}${trade.pnl:.4f} ({pnl_pct_sign}{trade.pnl_pct * 100:.2f}%)</b>\n"
        f"📋 Razão: <b>{trade.reason}</b>\n"
        f"🤖 Estratégia: {strategy or '—'}\n"
        f"⏰ {time.strftime('%d/%m/%Y %H:%M:%S')}"
    )
    send_message(text)


def notify_circuit_breaker(reason: str, daily_loss: float) -> None:
    """Alert when the daily loss circuit breaker trips."""
    text = (
        f"🚨 <b>CIRCUIT BREAKER ATIVADO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"❌ Razão: <b>{reason}</b>\n"
        f"📉 Perda diária: <b>-${abs(daily_loss):.2f}</b>\n"
        f"⛔ Bot pausado até amanhã.\n"
        f"⏰ {time.strftime('%d/%m/%Y %H:%M:%S')}"
    )
    send_message(text)


def notify_daily_summary(
    pnl_today: float,
    total_trades: int,
    win_rate: float,
    balance: float,
    mode: str = "paper",
) -> None:
    """Send end-of-day performance summary."""
    pnl_emoji = "📈" if pnl_today >= 0 else "📉"
    sign = "+" if pnl_today >= 0 else ""
    mode_tag = "📄 Paper" if mode == "paper" else "💰 Live"

    text = (
        f"{pnl_emoji} <b>RESUMO DIÁRIO — AlphaCota</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💼 Modo: <b>{mode_tag}</b>\n"
        f"💰 Saldo atual: <b>${balance:,.2f}</b>\n"
        f"📊 PnL hoje: <b>{sign}${pnl_today:.4f}</b>\n"
        f"🔢 Total trades: <b>{total_trades}</b>\n"
        f"🎯 Win rate: <b>{win_rate:.1f}%</b>\n"
        f"📅 {time.strftime('%d/%m/%Y')}"
    )
    send_message(text)
