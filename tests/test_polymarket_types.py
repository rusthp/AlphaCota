"""tests/test_polymarket_types.py — Unit tests for polymarket_types dataclasses."""

import time

import pytest

from core.polymarket_types import (
    CopySignal,
    Market,
    Order,
    OrderBook,
    OrderBookLevel,
    OrderIntent,
    Position,
    Trade,
    TradeDecision,
    WalletHealth,
)


class TestMarket:
    def test_create_minimal(self):
        m = Market(
            condition_id="cid1",
            token_id="tok1",
            question="Will X happen?",
            end_date_iso="2025-12-31T00:00:00Z",
            volume_24h=50_000.0,
            spread_pct=0.02,
            days_to_resolution=30.0,
            yes_price=0.65,
        )
        assert m.condition_id == "cid1"
        assert m.token_id == "tok1"
        assert m.category == ""
        assert m.is_active is True

    def test_create_with_category(self):
        m = Market(
            condition_id="cid2",
            token_id="tok2",
            question="?",
            end_date_iso="",
            volume_24h=0.0,
            spread_pct=0.0,
            days_to_resolution=0.0,
            yes_price=0.5,
            category="politics",
            is_active=False,
        )
        assert m.category == "politics"
        assert m.is_active is False

    def test_frozen(self):
        m = Market(
            condition_id="cid3",
            token_id="tok3",
            question="?",
            end_date_iso="",
            volume_24h=0.0,
            spread_pct=0.0,
            days_to_resolution=0.0,
            yes_price=0.5,
        )
        with pytest.raises(Exception):
            m.condition_id = "new"  # type: ignore[misc]


class TestOrderBookLevel:
    def test_fields(self):
        lvl = OrderBookLevel(price=0.45, size=1000.0)
        assert lvl.price == 0.45
        assert lvl.size == 1000.0

    def test_frozen(self):
        lvl = OrderBookLevel(price=0.5, size=100.0)
        with pytest.raises(Exception):
            lvl.price = 0.6  # type: ignore[misc]


class TestOrderBook:
    def test_create(self):
        bids = (OrderBookLevel(0.44, 500.0), OrderBookLevel(0.43, 300.0))
        asks = (OrderBookLevel(0.46, 400.0), OrderBookLevel(0.47, 200.0))
        book = OrderBook(
            token_id="tok1",
            bids=bids,
            asks=asks,
            mid_price=0.45,
            spread_pct=0.02,
        )
        assert book.mid_price == 0.45
        assert len(book.bids) == 2
        assert len(book.asks) == 2

    def test_frozen(self):
        book = OrderBook(token_id="t", bids=(), asks=(), mid_price=0.5, spread_pct=0.0)
        with pytest.raises(Exception):
            book.mid_price = 0.6  # type: ignore[misc]


class TestOrderIntent:
    def test_fields(self):
        oi = OrderIntent(
            condition_id="cid",
            token_id="tok",
            direction="yes",
            size_usd=25.0,
            limit_price=0.55,
            mode="paper",
        )
        assert oi.direction == "yes"
        assert oi.mode == "paper"


class TestOrder:
    def test_fields(self):
        now = time.time()
        o = Order(
            client_order_id="uuid-1",
            condition_id="cid",
            token_id="tok",
            direction="no",
            size_usd=50.0,
            fill_price=0.42,
            status="filled",
            mode="live",
            created_at=now,
        )
        assert o.status == "filled"
        assert o.mode == "live"


class TestPosition:
    def test_fields(self):
        now = time.time()
        pos = Position(
            position_id="pos-1",
            condition_id="cid",
            token_id="tok",
            direction="yes",
            size_usd=100.0,
            entry_price=0.6,
            current_price=0.65,
            unrealized_pnl=5.0,
            mode="paper",
            opened_at=now,
        )
        assert pos.unrealized_pnl == 5.0
        assert pos.entry_price == 0.6


class TestTrade:
    def test_fields(self):
        now = time.time()
        t = Trade(
            trade_id="trade-1",
            condition_id="cid",
            direction="yes",
            size_usd=75.0,
            entry_price=0.55,
            exit_price=0.90,
            realized_pnl=26.25,
            mode="paper",
            opened_at=now - 86400,
            closed_at=now,
        )
        assert t.realized_pnl == pytest.approx(26.25)


class TestTradeDecision:
    def test_fields(self):
        td = TradeDecision(
            condition_id="cid",
            token_id="tok",
            direction="yes",
            size_usd=30.0,
            score=72.5,
            kelly_fraction=0.15,
            reasoning="Strong edge detected",
        )
        assert td.score == 72.5
        assert td.kelly_fraction == 0.15

    def test_no_trade_size_zero(self):
        td = TradeDecision(
            condition_id="cid",
            token_id="tok",
            direction="yes",
            size_usd=0.0,
            score=20.0,
            kelly_fraction=0.0,
            reasoning="Insufficient edge",
        )
        assert td.size_usd == 0.0


class TestWalletHealth:
    def test_healthy(self):
        wh = WalletHealth(
            address="0xABC",
            matic_balance=5.0,
            usdc_balance=500.0,
            usdc_allowance=500.0,
            is_healthy=True,
            checked_at=time.time(),
        )
        assert wh.is_healthy is True

    def test_unhealthy(self):
        wh = WalletHealth(
            address="0xDEF",
            matic_balance=0.0,
            usdc_balance=5.0,
            usdc_allowance=0.0,
            is_healthy=False,
            checked_at=time.time(),
        )
        assert wh.is_healthy is False


class TestCopySignal:
    def test_fields(self):
        cs = CopySignal(
            direction="yes",
            confidence=0.75,
            wallet_count=3,
            consensus_ratio=0.80,
        )
        assert cs.direction == "yes"
        assert cs.consensus_ratio == 0.80

    def test_no_signal(self):
        cs = CopySignal(
            direction="none",
            confidence=0.0,
            wallet_count=0,
            consensus_ratio=0.5,
        )
        assert cs.direction == "none"
