"""tests/test_polymarket_discovery.py — Tests for enhanced market discovery."""

from unittest.mock import patch

import pytest

from core.polymarket_discovery import (
    DiscoveryConfig,
    _apply_quality_filter,
    _parse_market,
    discover_markets,
    volume_weighted_probability,
)
from core.polymarket_types import Market


def _raw_market(
    condition_id: str = "cid1",
    volume: float = 10_000.0,
    best_bid: float = 0.44,
    best_ask: float = 0.46,
    days: float = 14.0,
    active: bool = True,
    closed: bool = False,
) -> dict:
    import time
    from datetime import datetime, timedelta, timezone

    end_iso = (datetime.now(tz=timezone.utc) + timedelta(days=days)).isoformat()
    return {
        "conditionId": condition_id,
        "tokens": [{"outcome": "Yes", "token_id": f"tok-{condition_id}"}],
        "question": f"Will {condition_id} happen?",
        "endDate": end_iso,
        "volumeNum": volume,
        "bestBid": str(best_bid),
        "bestAsk": str(best_ask),
        "lastTradePrice": str((best_bid + best_ask) / 2),
        "active": active,
        "closed": closed,
        "tags": [{"label": "politics"}],
    }


def _market(condition_id: str = "cid1", volume: float = 10_000.0,
            spread: float = 0.02, days: float = 14.0) -> Market:
    return Market(
        condition_id=condition_id,
        token_id=f"tok-{condition_id}",
        question="Test market?",
        end_date_iso="2026-06-01T00:00:00Z",
        volume_24h=volume,
        spread_pct=spread,
        days_to_resolution=days,
        yes_price=0.55,
        category="politics",
        is_active=True,
    )


class TestQualityFilter:
    def test_passes_good_market(self):
        cfg = DiscoveryConfig()
        assert _apply_quality_filter(_market(), cfg) is True

    def test_rejects_low_volume(self):
        cfg = DiscoveryConfig(min_volume_24h=5_000.0)
        assert _apply_quality_filter(_market(volume=100.0), cfg) is False

    def test_rejects_wide_spread(self):
        cfg = DiscoveryConfig(max_spread_pct=0.05)
        assert _apply_quality_filter(_market(spread=0.10), cfg) is False

    def test_rejects_expired(self):
        cfg = DiscoveryConfig(min_days_to_resolution=2.0)
        assert _apply_quality_filter(_market(days=0.5), cfg) is False

    def test_rejects_too_far_out(self):
        cfg = DiscoveryConfig(max_days_to_resolution=180.0)
        assert _apply_quality_filter(_market(days=200.0), cfg) is False

    def test_rejects_inactive(self):
        m = Market(
            condition_id="cid1", token_id="tok1", question="?",
            end_date_iso="", volume_24h=50_000.0, spread_pct=0.02,
            days_to_resolution=14.0, yes_price=0.5, category="",
            is_active=False,
        )
        assert _apply_quality_filter(m, DiscoveryConfig()) is False


class TestParseMarket:
    def test_parses_valid_raw(self):
        raw = _raw_market()
        m = _parse_market(raw)
        assert m is not None
        assert m.condition_id == "cid1"
        assert m.token_id == "tok-cid1"
        assert m.volume_24h == 10_000.0
        assert m.spread_pct == pytest.approx(0.02, abs=0.001)

    def test_returns_none_for_missing_condition_id(self):
        raw = _raw_market()
        raw.pop("conditionId")
        assert _parse_market(raw) is None

    def test_uses_first_token_when_no_yes_outcome(self):
        raw = _raw_market()
        raw["tokens"] = [{"outcome": "No", "token_id": "tok-no"}]
        m = _parse_market(raw)
        assert m is not None
        assert m.token_id == "tok-no"

    def test_closed_market_is_inactive(self):
        raw = _raw_market(closed=True)
        m = _parse_market(raw)
        assert m is not None
        assert m.is_active is False


class TestDiscoverMarkets:
    def test_deduplicates_by_condition_id(self):
        raw = [_raw_market("cid1"), _raw_market("cid1"), _raw_market("cid2")]
        with patch("core.polymarket_discovery._fetch_trending", return_value=raw):
            markets = discover_markets()
        ids = [m.condition_id for m in markets]
        assert ids.count("cid1") == 1

    def test_returns_empty_on_api_error(self):
        with patch("core.polymarket_discovery._fetch_trending", side_effect=Exception("timeout")):
            assert discover_markets() == []

    def test_applies_quality_filter(self):
        raw = [
            _raw_market("cid1", volume=10_000.0, days=14.0),   # passes
            _raw_market("cid2", volume=100.0, days=14.0),       # fails volume
            _raw_market("cid3", volume=10_000.0, days=0.5),     # fails days
        ]
        with patch("core.polymarket_discovery._fetch_trending", return_value=raw):
            markets = discover_markets(DiscoveryConfig(min_volume_24h=5_000.0))
        assert len(markets) == 1
        assert markets[0].condition_id == "cid1"

    def test_respects_limit(self):
        raw = [_raw_market(f"cid{i}", volume=10_000.0) for i in range(20)]
        with patch("core.polymarket_discovery._fetch_trending", return_value=raw):
            markets = discover_markets(DiscoveryConfig(limit=5))
        assert len(markets) == 5


class TestVolumeWeightedProbability:
    def test_empty_returns_zero(self):
        assert volume_weighted_probability([]) == 0.0

    def test_weights_by_volume(self):
        m1 = _market("cid1", volume=100.0)
        m1 = Market(**{**m1.__dict__, "yes_price": 0.20})  # type: ignore[arg-type]
        m2 = _market("cid2", volume=900.0)
        m2 = Market(**{**m2.__dict__, "yes_price": 0.80})  # type: ignore[arg-type]
        # expected: (0.20*100 + 0.80*900) / 1000 = 740/1000 = 0.74
        result = volume_weighted_probability([m1, m2])
        assert result == pytest.approx(0.74, abs=0.001)

    def test_falls_back_to_simple_average_when_zero_volume(self):
        m1 = _market("cid1", volume=0.0)
        m1 = Market(**{**m1.__dict__, "yes_price": 0.30})  # type: ignore[arg-type]
        m2 = _market("cid2", volume=0.0)
        m2 = Market(**{**m2.__dict__, "yes_price": 0.70})  # type: ignore[arg-type]
        result = volume_weighted_probability([m1, m2])
        assert result == pytest.approx(0.50, abs=0.001)
