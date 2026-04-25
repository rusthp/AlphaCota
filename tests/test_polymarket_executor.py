"""tests/test_polymarket_executor.py — Tests for live executor."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.polymarket_executor import (
    HardLimitExceeded,
    MAX_DAILY_LOSS_USD,
    MAX_POSITION_USD,
    close_live_position,
    execute_live,
)
from core.polymarket_ledger import init_db
from core.polymarket_types import TradeDecision


def _decision(size_usd: float = 25.0, direction: str = "yes") -> TradeDecision:
    return TradeDecision(
        condition_id="cid1",
        token_id="tok1",
        direction=direction,
        size_usd=size_usd,
        score=72.0,
        kelly_fraction=0.10,
        reasoning="test",
    )


@pytest.fixture
def conn(tmp_path):
    db_file = str(tmp_path / "exec_test.db")
    c = init_db(db_file)
    yield c
    c.close()


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.create_and_post_order.return_value = {"orderID": "exch-001"}
    client.get_order.return_value = {"status": "filled", "avgPrice": "0.55"}
    return client


class TestHardLimits:
    def test_rejects_oversized_order(self, conn, mock_client):
        oversized = _decision(size_usd=MAX_POSITION_USD + 1)
        from core.polymarket_types import OrderBook, OrderBookLevel
        book = OrderBook("tok1", (OrderBookLevel(0.44, 500),), (OrderBookLevel(0.46, 400),), 0.45, 0.02)
        with patch("core.polymarket_client.get_order_book", return_value=book):
            with pytest.raises(HardLimitExceeded, match="hard limit"):
                execute_live(oversized, conn, mock_client)

    def test_rejects_when_daily_loss_exceeded(self, conn, mock_client):
        conn.execute(
            "INSERT INTO pm_trades (trade_id, condition_id, direction, size_usd, "
            "entry_price, exit_price, realized_pnl, mode, opened_at, closed_at) "
            "VALUES ('t1','cid1','yes',50.0,0.6,0.5,-15.0,'live',?,?)",
            (time.time() - 3600, time.time()),
        )
        conn.commit()

        d = _decision(size_usd=10.0)
        from core.polymarket_types import OrderBook, OrderBookLevel
        book = OrderBook("tok1", (OrderBookLevel(0.44, 500),), (OrderBookLevel(0.46, 400),), 0.45, 0.02)
        with patch("core.polymarket_client.get_order_book", return_value=book):
            with pytest.raises(HardLimitExceeded, match="Daily loss"):
                execute_live(d, conn, mock_client)

    def test_accepts_order_within_limits(self, conn, mock_client):
        from core.polymarket_types import OrderBook, OrderBookLevel
        book = OrderBook("tok1", (OrderBookLevel(0.44, 500),), (OrderBookLevel(0.46, 400),), 0.45, 0.02)
        with (
            patch("core.polymarket_client.get_order_book", return_value=book),
            patch("core.polymarket_executor.time") as mock_time,
        ):
            mock_time.time.return_value = time.time()
            mock_time.sleep = MagicMock()
            order = execute_live(_decision(size_usd=20.0), conn, mock_client)
        assert order.status == "filled"
        assert order.mode == "live"


class TestEip712Signing:
    def test_order_submitted_to_clob(self, conn, mock_client):
        from core.polymarket_types import OrderBook, OrderBookLevel
        book = OrderBook("tok1", (OrderBookLevel(0.44, 500),), (OrderBookLevel(0.46, 400),), 0.45, 0.02)
        with (
            patch("core.polymarket_client.get_order_book", return_value=book),
            patch("core.polymarket_executor.time") as mock_time,
        ):
            mock_time.time.return_value = time.time()
            mock_time.sleep = MagicMock()
            execute_live(_decision(), conn, mock_client)
        mock_client.create_and_post_order.assert_called_once()
        call_args = mock_client.create_and_post_order.call_args[0][0]
        assert call_args["token_id"] == "tok1"
        assert call_args["time_in_force"] == "GTC"

    def test_fill_price_from_exchange_response(self, conn, mock_client):
        mock_client.get_order.return_value = {"status": "filled", "avgPrice": "0.62"}
        from core.polymarket_types import OrderBook, OrderBookLevel
        book = OrderBook("tok1", (OrderBookLevel(0.44, 500),), (OrderBookLevel(0.46, 400),), 0.45, 0.02)
        with (
            patch("core.polymarket_client.get_order_book", return_value=book),
            patch("core.polymarket_executor.time") as mock_time,
        ):
            mock_time.time.return_value = time.time()
            mock_time.sleep = MagicMock()
            order = execute_live(_decision(), conn, mock_client)
        assert order.fill_price == pytest.approx(0.62)


class TestKillSwitchBlocksClose:
    def _open_position(self, conn) -> str:
        pos_id = "pos-live-1"
        conn.execute(
            "INSERT INTO pm_positions (position_id, condition_id, token_id, direction, "
            "size_usd, entry_price, current_price, unrealized_pnl, mode, opened_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (pos_id, "cid1", "tok1", "yes", 50.0, 0.50, 0.55, 2.5, "live",
             time.time(), time.time()),
        )
        conn.commit()
        return pos_id

    def test_kill_switch_blocks_close(self, conn, mock_client, tmp_path, monkeypatch):
        kill_file = tmp_path / "POLYMARKET_KILL"
        kill_file.touch()
        monkeypatch.setattr("core.polymarket_executor._KILL_FILE", kill_file)

        pid = self._open_position(conn)
        with pytest.raises(RuntimeError, match="Kill-switch"):
            close_live_position(pid, conn, mock_client)

    def test_close_succeeds_without_kill_switch(self, conn, mock_client, tmp_path, monkeypatch):
        kill_file = tmp_path / "POLYMARKET_KILL"
        monkeypatch.setattr("core.polymarket_executor._KILL_FILE", kill_file)

        pid = self._open_position(conn)
        from core.polymarket_types import OrderBook, OrderBookLevel
        book = OrderBook("tok1", (OrderBookLevel(0.54, 500),), (OrderBookLevel(0.56, 400),), 0.55, 0.02)
        with patch("core.polymarket_client.get_order_book", return_value=book):
            trade = close_live_position(pid, conn, mock_client)
        assert trade.realized_pnl > 0
