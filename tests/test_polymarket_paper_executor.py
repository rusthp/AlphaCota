"""tests/test_polymarket_paper_executor.py — Tests for paper executor."""

import time
from unittest.mock import MagicMock, patch

import pytest

from core.polymarket_ledger import init_db
from core.polymarket_paper_executor import close_paper_position, execute_paper
from core.polymarket_types import Order, Trade, TradeDecision


def _decision(
    condition_id: str = "cid1",
    token_id: str = "tok1",
    direction: str = "yes",
    size_usd: float = 50.0,
    score: float = 72.0,
    kelly_fraction: float = 0.10,
) -> TradeDecision:
    return TradeDecision(
        condition_id=condition_id,
        token_id=token_id,
        direction=direction,
        size_usd=size_usd,
        score=score,
        kelly_fraction=kelly_fraction,
        reasoning="test",
    )


@pytest.fixture
def conn(tmp_path):
    db_file = str(tmp_path / "test_exec.db")
    c = init_db(db_file)
    yield c
    c.close()


class TestExecutePaper:
    def test_returns_filled_order(self, conn):
        with patch("core.polymarket_paper_executor._get_fill_price", return_value=0.55):
            order = execute_paper(_decision(), conn)
        assert isinstance(order, Order)
        assert order.status == "filled"
        assert order.mode == "paper"

    def test_fill_price_applied(self, conn):
        with patch("core.polymarket_paper_executor._get_fill_price", return_value=0.62):
            order = execute_paper(_decision(), conn)
        assert order.fill_price == pytest.approx(0.62)

    def test_order_persisted_in_ledger(self, conn):
        with patch("core.polymarket_paper_executor._get_fill_price", return_value=0.55):
            order = execute_paper(_decision(condition_id="cid-persist"), conn)
        row = conn.execute(
            "SELECT * FROM pm_orders WHERE client_order_id = ?",
            (order.client_order_id,),
        ).fetchone()
        assert row is not None
        assert row["status"] == "filled"
        assert row["condition_id"] == "cid-persist"

    def test_position_created_in_ledger(self, conn):
        with patch("core.polymarket_paper_executor._get_fill_price", return_value=0.55):
            execute_paper(_decision(condition_id="cid-pos"), conn)
        row = conn.execute(
            "SELECT * FROM pm_positions WHERE condition_id = ?", ("cid-pos",)
        ).fetchone()
        assert row is not None
        assert row["mode"] == "paper"
        assert float(row["entry_price"]) == pytest.approx(0.55)

    def test_yes_direction_uses_ask_side(self, conn):
        from core.polymarket_types import OrderBook, OrderBookLevel
        mock_book = OrderBook(
            token_id="tok1",
            bids=(OrderBookLevel(0.44, 500.0),),
            asks=(OrderBookLevel(0.46, 400.0),),
            mid_price=0.45,
            spread_pct=0.02,
        )
        with patch("core.polymarket_client.get_order_book", return_value=mock_book):
            order = execute_paper(_decision(direction="yes"), conn, client=MagicMock())
        assert order.fill_price > 0.45

    def test_size_usd_preserved(self, conn):
        with patch("core.polymarket_paper_executor._get_fill_price", return_value=0.50):
            order = execute_paper(_decision(size_usd=123.45), conn)
        assert order.size_usd == pytest.approx(123.45)


class TestClosePaperPosition:
    def _open_position(self, conn, condition_id: str = "cid1", direction: str = "yes") -> str:
        from core.polymarket_paper_executor import _upsert_position
        d = _decision(condition_id=condition_id, direction=direction)
        _upsert_position(conn, "test-order-id", d, 0.50, time.time())
        row = conn.execute(
            "SELECT position_id FROM pm_positions WHERE condition_id = ?", (condition_id,)
        ).fetchone()
        return row["position_id"]

    def test_returns_trade(self, conn):
        pid = self._open_position(conn)
        with patch("core.polymarket_paper_executor._get_fill_price", return_value=0.70):
            trade = close_paper_position(pid, conn)
        assert isinstance(trade, Trade)
        assert trade.mode == "paper"

    def test_positive_pnl_on_yes_profit(self, conn):
        pid = self._open_position(conn, direction="yes")
        with patch("core.polymarket_paper_executor._get_fill_price", return_value=0.80):
            trade = close_paper_position(pid, conn)
        assert trade.realized_pnl > 0

    def test_negative_pnl_on_yes_loss(self, conn):
        pid = self._open_position(conn, direction="yes")
        with patch("core.polymarket_paper_executor._get_fill_price", return_value=0.20):
            trade = close_paper_position(pid, conn)
        assert trade.realized_pnl < 0

    def test_position_removed_after_close(self, conn):
        pid = self._open_position(conn, condition_id="cid-rm")
        with patch("core.polymarket_paper_executor._get_fill_price", return_value=0.60):
            close_paper_position(pid, conn)
        row = conn.execute(
            "SELECT * FROM pm_positions WHERE position_id = ?", (pid,)
        ).fetchone()
        assert row is None

    def test_trade_recorded_in_ledger(self, conn):
        pid = self._open_position(conn, condition_id="cid-trade")
        with patch("core.polymarket_paper_executor._get_fill_price", return_value=0.75):
            trade = close_paper_position(pid, conn)
        row = conn.execute(
            "SELECT * FROM pm_trades WHERE trade_id = ?", (trade.trade_id,)
        ).fetchone()
        assert row is not None
        assert float(row["realized_pnl"]) == pytest.approx(trade.realized_pnl)

    def test_raises_on_unknown_position(self, conn):
        with pytest.raises(ValueError, match="not found"):
            close_paper_position("nonexistent-uuid", conn)

    def test_no_direction_inverts_pnl_for_no(self, conn):
        pid = self._open_position(conn, direction="no")
        with patch("core.polymarket_paper_executor._get_fill_price", return_value=0.30):
            trade = close_paper_position(pid, conn)
        assert trade.realized_pnl > 0
