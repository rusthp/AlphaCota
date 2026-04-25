"""tests/test_polymarket_client.py — Tests for polymarket_client module."""

import time
from unittest.mock import MagicMock, patch

import pytest

from core.polymarket_types import Market, OrderBook, OrderBookLevel, WalletHealth


class TestDiscoverMarkets:
    def _raw_market(
        self,
        condition_id: str = "cid1",
        token_id: str = "tok1",
        volume: float = 50_000.0,
        best_bid: float = 0.45,
        best_ask: float = 0.47,
        days: float = 14.0,
    ) -> dict:
        end_ts = time.time() + days * 86400
        from datetime import datetime, timezone
        end_date = datetime.fromtimestamp(end_ts, tz=timezone.utc).isoformat()
        return {
            "conditionId": condition_id,
            "tokens": [
                {"outcome": "Yes", "token_id": token_id},
                {"outcome": "No", "token_id": "tok_no"},
            ],
            "question": "Will X happen?",
            "endDate": end_date,
            "volume24hr": volume,
            "bestBid": best_bid,
            "bestAsk": best_ask,
            "lastTradePrice": 0.46,
            "tags": [{"label": "politics"}],
        }

    def test_returns_filtered_markets(self):
        raw = [self._raw_market("cid1", "tok1"), self._raw_market("cid2", "tok2")]
        with patch("core.polymarket_discovery._fetch_trending", return_value=raw):
            from core.polymarket_client import discover_markets
            markets = discover_markets(min_volume=1_000.0, max_spread=0.10, limit=10)
        assert len(markets) == 2
        assert all(isinstance(m, Market) for m in markets)

    def test_filters_low_volume(self):
        raw = [self._raw_market("cid1", "tok1", volume=500.0)]
        with patch("core.polymarket_discovery._fetch_trending", return_value=raw):
            from core.polymarket_client import discover_markets
            markets = discover_markets(min_volume=1_000.0)
        assert len(markets) == 0

    def test_filters_high_spread(self):
        raw = [self._raw_market("cid1", "tok1", best_bid=0.40, best_ask=0.60)]
        with patch("core.polymarket_discovery._fetch_trending", return_value=raw):
            from core.polymarket_client import discover_markets
            markets = discover_markets(max_spread=0.05)
        assert len(markets) == 0

    def test_deduplicates_condition_ids(self):
        raw = [
            self._raw_market("cid1", "tok1"),
            self._raw_market("cid1", "tok1b"),
        ]
        with patch("core.polymarket_discovery._fetch_trending", return_value=raw):
            from core.polymarket_client import discover_markets
            markets = discover_markets()
        assert len(markets) == 1

    def test_respects_limit(self):
        raw = [self._raw_market(f"cid{i}", f"tok{i}") for i in range(10)]
        with patch("core.polymarket_discovery._fetch_trending", return_value=raw):
            from core.polymarket_client import discover_markets
            markets = discover_markets(limit=3)
        assert len(markets) == 3

    def test_gamma_api_error_returns_empty(self):
        with patch("core.polymarket_discovery._fetch_trending", side_effect=RuntimeError("API down")):
            from core.polymarket_client import discover_markets
            markets = discover_markets()
        assert markets == []

    def test_category_extracted_from_tags(self):
        raw = [self._raw_market("cid1", "tok1")]
        with patch("core.polymarket_discovery._fetch_trending", return_value=raw):
            from core.polymarket_client import discover_markets
            markets = discover_markets()
        assert markets[0].category == "politics"


class TestGetOrderBook:
    def _mock_response(self, bids=None, asks=None) -> dict:
        return {
            "bids": bids or [{"price": "0.44", "size": "500"}, {"price": "0.43", "size": "300"}],
            "asks": asks or [{"price": "0.46", "size": "400"}, {"price": "0.47", "size": "200"}],
        }

    def test_returns_order_book(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._mock_response()
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_resp):
            from core.polymarket_client import get_order_book
            book = get_order_book("tok1")

        assert isinstance(book, OrderBook)
        assert book.token_id == "tok1"
        assert len(book.bids) == 2
        assert len(book.asks) == 2
        assert book.bids[0].price == pytest.approx(0.44)
        assert book.asks[0].price == pytest.approx(0.46)

    def test_mid_price_calculation(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "bids": [{"price": "0.44", "size": "100"}],
            "asks": [{"price": "0.46", "size": "100"}],
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_resp):
            from core.polymarket_client import get_order_book
            book = get_order_book("tok1")

        assert book.mid_price == pytest.approx(0.45)
        assert book.spread_pct == pytest.approx(0.02)

    def test_empty_order_book(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"bids": [], "asks": []}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_resp):
            from core.polymarket_client import get_order_book
            book = get_order_book("tok1")

        assert book.bids == ()
        assert book.asks == ()

    def test_api_error_raises_runtime_error(self):
        with patch("httpx.get", side_effect=Exception("Connection refused")):
            from core.polymarket_client import get_order_book
            with pytest.raises(RuntimeError, match="CLOB API error"):
                get_order_book("tok1")


class TestGetMidPrice:
    def test_returns_float(self):
        mock_book = OrderBook(
            token_id="tok1",
            bids=(OrderBookLevel(0.44, 500.0),),
            asks=(OrderBookLevel(0.46, 400.0),),
            mid_price=0.45,
            spread_pct=0.02,
        )
        with patch("core.polymarket_client.get_order_book", return_value=mock_book):
            from core.polymarket_client import get_mid_price
            price = get_mid_price("tok1")
        assert price == pytest.approx(0.45)


class TestGetWalletHealth:
    def test_paper_mode_returns_healthy(self):
        mock_settings = MagicMock()
        mock_settings.polymarket_mode = "paper"

        with (
            patch("core.polymarket_client.os.getenv", return_value=""),
            patch("core.polymarket_client.settings", mock_settings, create=True),
        ):
            from core.polymarket_client import get_wallet_health
            with patch("core.config.settings", mock_settings):
                health = get_wallet_health()

        assert isinstance(health, WalletHealth)
        assert health.is_healthy is True
        assert health.usdc_balance == 10_000.0

    def test_paper_mode_when_no_private_key(self):
        import importlib
        import sys

        with patch.dict("os.environ", {"POLYMARKET_PRIVATE_KEY_ENC": "", "POLYMARKET_MODE": "paper"}):
            import core.config as cfg_mod
            mock_settings = MagicMock()
            mock_settings.polymarket_mode = "paper"

            with patch("core.polymarket_client.settings", mock_settings, create=True):
                from core.polymarket_client import get_wallet_health
                health = get_wallet_health()

        assert health.is_healthy is True
        assert health.address == "0x0000000000000000000000000000000000000000"
