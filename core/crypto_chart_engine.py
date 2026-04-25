"""
core/crypto_chart_engine.py — Chart generation (PNG renderer).

Re-exports the pure indicator math from `core.crypto_indicators` so existing
callers that imported EMA/RSI/MACD from here keep working, and adds the
matplotlib-backed PNG renderer.

Chart generation writes PNGs using matplotlib's "Agg" backend (no display
required), so it runs inside a headless loop.

Public API (pure math, re-exported):
    calculate_ema(values, period) -> list[float]
    calculate_rsi(closes, period) -> list[float]
    calculate_macd(closes, fast, slow, signal) -> (macd, signal, histogram)

Public API (I/O — writes PNG):
    generate_ohlcv_chart(candles, symbol, output_path) -> str
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import matplotlib

# Force a non-interactive backend BEFORE importing pyplot — required for
# server loops where no display is available.
matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from core.crypto_indicators import calculate_ema, calculate_macd, calculate_rsi  # noqa: E402,F401
from core.crypto_types import CryptoCandle  # noqa: E402
from core.logger import logger  # noqa: E402


# ---------------------------------------------------------------------------
# Chart generation (PNG writer)
# ---------------------------------------------------------------------------


_BG_COLOR = "#1a1a2e"
_GRID_COLOR = "#2a2a4e"
_TEXT_COLOR = "#d0d0e0"
_PRICE_COLOR = "#00e5ff"      # cyan
_EMA20_COLOR = "#ff9f1c"      # orange
_EMA50_COLOR = "#ffd166"      # yellow
_RSI_COLOR = "#2ec4b6"        # green
_RSI_OVERBOUGHT = "#ef476f"   # dashed red line @ 70
_RSI_OVERSOLD = "#06d6a0"     # dashed green line @ 30
_VOLUME_UP = "#06d6a0"
_VOLUME_DOWN = "#ef476f"


def _style_axes(ax: "plt.Axes") -> None:
    """Apply dark-theme styling to a matplotlib Axes."""
    ax.set_facecolor(_BG_COLOR)
    ax.grid(True, color=_GRID_COLOR, linewidth=0.5, alpha=0.6)
    for spine in ax.spines.values():
        spine.set_color(_GRID_COLOR)
    ax.tick_params(colors=_TEXT_COLOR, labelsize=8)
    ax.yaxis.label.set_color(_TEXT_COLOR)
    ax.xaxis.label.set_color(_TEXT_COLOR)


def generate_ohlcv_chart(
    candles: list[CryptoCandle],
    symbol: str,
    output_path: str,
) -> str:
    """Render a 3-panel dark-theme chart (price/EMA, RSI, volume) to PNG.

    Panels (top → bottom):
        1. Close price line with EMA20 and EMA50 overlays.
        2. RSI(14) with horizontal guides at 70 (overbought) and 30 (oversold).
        3. Volume bars, coloured green for up-candles and red for down-candles.

    Args:
        candles: List of CryptoCandle, oldest → newest. At least 2 required.
        symbol: Display label (e.g. "BTCUSDT").
        output_path: Destination PNG path. Parent directory is created if missing.

    Returns:
        The absolute output path.

    Raises:
        ValueError: If fewer than 2 candles are supplied.
    """
    if len(candles) < 2:
        raise ValueError(
            f"generate_ohlcv_chart: need >= 2 candles, got {len(candles)}"
        )

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    closes = [c.close for c in candles]
    opens = [c.open for c in candles]
    volumes = [c.volume for c in candles]
    times = [datetime.fromtimestamp(c.timestamp, tz=timezone.utc) for c in candles]

    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)
    rsi = calculate_rsi(closes, 14)

    # Infer interval label from first gap (in seconds) — purely cosmetic.
    if len(candles) >= 2:
        gap_sec = candles[1].timestamp - candles[0].timestamp
        interval_label = _humanize_interval(gap_sec)
    else:
        interval_label = "?"

    fig, axes = plt.subplots(
        nrows=3,
        ncols=1,
        sharex=True,
        figsize=(12, 8),
        gridspec_kw={"height_ratios": [3, 1, 1]},
    )
    fig.patch.set_facecolor(_BG_COLOR)

    ax_price, ax_rsi, ax_vol = axes[0], axes[1], axes[2]

    # ---- Panel 1: price + EMAs ----
    _style_axes(ax_price)
    ax_price.plot(times, closes, color=_PRICE_COLOR, linewidth=1.5, label="Close")
    ax_price.plot(times, ema20, color=_EMA20_COLOR, linewidth=1.0, label="EMA20")
    ax_price.plot(times, ema50, color=_EMA50_COLOR, linewidth=1.0, label="EMA50")
    ax_price.set_ylabel("Price")
    leg = ax_price.legend(loc="upper left", fontsize=8, facecolor=_BG_COLOR, edgecolor=_GRID_COLOR)
    for text in leg.get_texts():
        text.set_color(_TEXT_COLOR)

    now_iso = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ax_price.set_title(
        f"{symbol} — {interval_label} — {now_iso}",
        color=_TEXT_COLOR,
        fontsize=11,
        pad=10,
    )

    # ---- Panel 2: RSI ----
    _style_axes(ax_rsi)
    ax_rsi.plot(times, rsi, color=_RSI_COLOR, linewidth=1.2, label="RSI(14)")
    ax_rsi.axhline(70, color=_RSI_OVERBOUGHT, linestyle="--", linewidth=0.8, alpha=0.8)
    ax_rsi.axhline(30, color=_RSI_OVERSOLD, linestyle="--", linewidth=0.8, alpha=0.8)
    ax_rsi.set_ylim(0, 100)
    ax_rsi.set_ylabel("RSI")
    ax_rsi.set_yticks([0, 30, 50, 70, 100])

    # ---- Panel 3: Volume ----
    _style_axes(ax_vol)
    colors = [
        _VOLUME_UP if closes[i] >= opens[i] else _VOLUME_DOWN
        for i in range(len(candles))
    ]
    # Bar width in matplotlib date units — 80% of interval gap.
    if len(times) >= 2:
        bar_width = (times[1] - times[0]).total_seconds() / 86400.0 * 0.8
    else:
        bar_width = 0.01
    ax_vol.bar(times, volumes, color=colors, width=bar_width, edgecolor="none")
    ax_vol.set_ylabel("Volume")

    # Format x-axis dates on the bottom panel.
    ax_vol.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    for label in ax_vol.get_xticklabels():
        label.set_rotation(30)
        label.set_ha("right")

    fig.tight_layout()
    try:
        fig.savefig(output_path, dpi=110, facecolor=_BG_COLOR, bbox_inches="tight")
    finally:
        plt.close(fig)

    logger.info("generate_ohlcv_chart: wrote %s", output_path)
    return os.path.abspath(output_path)


def _humanize_interval(seconds: float) -> str:
    """Convert a seconds gap into a Binance-style label (e.g. 900 -> '15m')."""
    if seconds <= 0:
        return "?"
    s = int(round(seconds))
    if s % 86400 == 0:
        return f"{s // 86400}d"
    if s % 3600 == 0:
        return f"{s // 3600}h"
    if s % 60 == 0:
        return f"{s // 60}m"
    return f"{s}s"
