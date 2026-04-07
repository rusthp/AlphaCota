"""Tests for data/data_loader.py — CSV cache utilities and calculations."""

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import data.data_loader as loader


class TestCachePath:
    def test_returns_csv_path(self):
        path = loader._cache_path("/tmp/test", "HGLG11", "prices")
        assert path.endswith("HGLG11_prices.csv")

    def test_sanitizes_dot(self):
        path = loader._cache_path("/tmp", "HGLG11.SA", "prices")
        assert "HGLG11_SA" in path


class TestLoadSaveCSV:
    def test_roundtrip(self, tmp_path):
        path = str(tmp_path / "test.csv")
        rows = [{"date": "2025-01-01", "close": "150.0"}, {"date": "2025-02-01", "close": "155.0"}]
        loader._save_csv(path, rows, ["date", "close"])
        loaded = loader._load_csv(path)
        assert len(loaded) == 2
        assert loaded[0]["close"] == "150.0"

    def test_load_nonexistent(self):
        assert loader._load_csv("/nonexistent/file.csv") == []


class TestEnsureDirs:
    def test_creates_directories(self, tmp_path, monkeypatch):
        prices = str(tmp_path / "prices")
        divs = str(tmp_path / "dividends")
        monkeypatch.setattr(loader, "PRICES_DIR", prices)
        monkeypatch.setattr(loader, "DIVIDENDS_DIR", divs)
        loader._ensure_dirs()
        assert os.path.isdir(prices)
        assert os.path.isdir(divs)


class TestGetClosePrices:
    def test_extracts_close(self):
        prices = [{"close": "150.0"}, {"close": "155.0"}, {"close": "160.0"}]
        result = loader.get_close_prices(prices)
        assert result == [150.0, 155.0, 160.0]

    def test_empty_list(self):
        assert loader.get_close_prices([]) == []


class TestCalculateMonthlyReturns:
    def test_basic_returns(self):
        closes = [100.0, 110.0, 99.0]
        returns = loader.calculate_monthly_returns(closes)
        assert len(returns) == 3
        assert returns[0] == 0.0
        assert returns[1] == pytest.approx(0.10)
        assert returns[2] == pytest.approx(-0.10, abs=0.01)

    def test_single_price(self):
        assert loader.calculate_monthly_returns([100.0]) == [0.0]

    def test_empty(self):
        assert loader.calculate_monthly_returns([]) == []

    def test_zero_price_no_error(self):
        closes = [0.0, 100.0]
        returns = loader.calculate_monthly_returns(closes)
        assert returns[1] == 0.0


class TestGetAvailableCache:
    def test_lists_cached_tickers(self, tmp_path):
        (tmp_path / "HGLG11_prices.csv").touch()
        (tmp_path / "XPML11_prices.csv").touch()
        result = loader.get_available_cache(str(tmp_path))
        assert "HGLG11" in result
        assert "XPML11" in result

    def test_empty_dir(self, tmp_path):
        assert loader.get_available_cache(str(tmp_path)) == []

    def test_nonexistent_dir(self):
        assert loader.get_available_cache("/nonexistent/dir") == []


class TestFetchPricesWithoutYfinance:
    def test_raises_without_yfinance(self, monkeypatch):
        monkeypatch.setattr(loader, "HAS_YFINANCE", False)
        with pytest.raises(ImportError, match="yfinance"):
            loader.fetch_prices("HGLG11", "2024-01-01", "2025-01-01")


class TestFetchDividendsWithoutYfinance:
    def test_raises_without_yfinance(self, monkeypatch):
        monkeypatch.setattr(loader, "HAS_YFINANCE", False)
        with pytest.raises(ImportError, match="yfinance"):
            loader.fetch_dividends("HGLG11", "2024-01-01", "2025-01-01")


# ---------------------------------------------------------------------------
# fetch_prices — mocked yfinance paths
# ---------------------------------------------------------------------------


def _inject_yf(monkeypatch):
    """Inject a mock yf module into data.data_loader (yfinance may not be installed)."""
    mock_yf = MagicMock()
    monkeypatch.setattr(loader, "yf", mock_yf, raising=False)
    return mock_yf


def _make_dataframe(rows):
    """Build a mock DataFrame that behaves like yfinance output."""
    mock_df = MagicMock()
    mock_df.empty = len(rows) == 0
    mock_df.__bool__ = lambda self: True
    items = []
    for r in rows:
        idx = MagicMock()
        idx.__str__ = lambda s, d=r["date"]: d
        row_mock = MagicMock()
        row_mock.get = lambda k, default=0, _r=r: _r.get(k, default)
        items.append((idx, row_mock))
    mock_df.iterrows = lambda: iter(items)
    return mock_df


def _make_dividends_series(items):
    """Build a mock Series that behaves like yfinance dividends output."""
    mock_series = MagicMock()
    mock_series.empty = len(items) == 0
    entries = []
    for date_str, value in items:
        idx = MagicMock()
        idx.__str__ = lambda s, d=date_str: d
        entries.append((idx, value))
    mock_series.items = lambda: iter(entries)
    return mock_series


class TestFetchPricesWithMockedYfinance:
    """Tests for fetch_prices with mocked yfinance.download."""

    def test_downloads_and_caches(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "HAS_YFINANCE", True)
        monkeypatch.setattr(loader, "PRICES_DIR", str(tmp_path / "prices"))
        monkeypatch.setattr(loader, "DIVIDENDS_DIR", str(tmp_path / "divs"))
        mock_yf = _inject_yf(monkeypatch)

        df = _make_dataframe(
            [
                {"date": "2024-06-01", "Open": 100, "High": 105, "Low": 99, "Close": 103, "Volume": 5000},
                {"date": "2024-07-01", "Open": 103, "High": 110, "Low": 101, "Close": 108, "Volume": 6000},
            ]
        )
        mock_yf.download.return_value = df
        result = loader.fetch_prices("HGLG11", "2024-06-01", "2024-07-31")

        assert len(result) == 2
        assert result[0]["close"] == 103
        assert result[1]["volume"] == 6000
        cache_file = os.path.join(str(tmp_path / "prices"), "HGLG11_prices.csv")
        assert os.path.exists(cache_file)

    def test_returns_from_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "HAS_YFINANCE", True)
        prices_dir = str(tmp_path / "prices")
        os.makedirs(prices_dir, exist_ok=True)
        monkeypatch.setattr(loader, "PRICES_DIR", prices_dir)
        monkeypatch.setattr(loader, "DIVIDENDS_DIR", str(tmp_path / "divs"))
        mock_yf = _inject_yf(monkeypatch)

        cache_rows = [
            {"date": "2024-06-01", "open": "100", "high": "105", "low": "99", "close": "103", "volume": "5000"},
        ]
        loader._save_csv(
            os.path.join(prices_dir, "HGLG11_prices.csv"),
            cache_rows,
            ["date", "open", "high", "low", "close", "volume"],
        )

        result = loader.fetch_prices("HGLG11", "2024-06-01", "2024-06-30")
        mock_yf.download.assert_not_called()
        assert len(result) == 1
        assert result[0]["date"] == "2024-06-01"

    def test_force_refresh_bypasses_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "HAS_YFINANCE", True)
        prices_dir = str(tmp_path / "prices")
        os.makedirs(prices_dir, exist_ok=True)
        monkeypatch.setattr(loader, "PRICES_DIR", prices_dir)
        monkeypatch.setattr(loader, "DIVIDENDS_DIR", str(tmp_path / "divs"))
        mock_yf = _inject_yf(monkeypatch)

        loader._save_csv(
            os.path.join(prices_dir, "HGLG11_prices.csv"),
            [{"date": "2024-06-01", "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"}],
            ["date", "open", "high", "low", "close", "volume"],
        )

        df = _make_dataframe(
            [
                {"date": "2024-06-01", "Open": 200, "High": 210, "Low": 195, "Close": 205, "Volume": 9000},
            ]
        )
        mock_yf.download.return_value = df
        result = loader.fetch_prices("HGLG11", "2024-06-01", "2024-06-30", force_refresh=True)
        mock_yf.download.assert_called_once()
        assert result[0]["close"] == 205

    def test_adds_sa_suffix(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "HAS_YFINANCE", True)
        monkeypatch.setattr(loader, "PRICES_DIR", str(tmp_path / "p"))
        monkeypatch.setattr(loader, "DIVIDENDS_DIR", str(tmp_path / "d"))
        mock_yf = _inject_yf(monkeypatch)

        df = _make_dataframe(
            [
                {"date": "2024-06-01", "Open": 10, "High": 11, "Low": 9, "Close": 10, "Volume": 100},
            ]
        )
        mock_yf.download.return_value = df
        loader.fetch_prices("MXRF11", "2024-06-01", "2024-06-30")
        call_args = mock_yf.download.call_args
        assert call_args[0][0] == "MXRF11.SA"

    def test_index_ticker_no_sa_suffix(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "HAS_YFINANCE", True)
        monkeypatch.setattr(loader, "PRICES_DIR", str(tmp_path / "p"))
        monkeypatch.setattr(loader, "DIVIDENDS_DIR", str(tmp_path / "d"))
        mock_yf = _inject_yf(monkeypatch)

        df = _make_dataframe(
            [
                {"date": "2024-06-01", "Open": 3000, "High": 3050, "Low": 2980, "Close": 3020, "Volume": 0},
            ]
        )
        mock_yf.download.return_value = df
        loader.fetch_prices("^IFIX", "2024-06-01", "2024-06-30")
        call_args = mock_yf.download.call_args
        assert call_args[0][0] == "^IFIX"

    def test_raises_on_empty_dataframe(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "HAS_YFINANCE", True)
        monkeypatch.setattr(loader, "PRICES_DIR", str(tmp_path / "p"))
        monkeypatch.setattr(loader, "DIVIDENDS_DIR", str(tmp_path / "d"))
        mock_yf = _inject_yf(monkeypatch)

        mock_df = MagicMock()
        mock_df.empty = True
        mock_yf.download.return_value = mock_df
        with pytest.raises(ValueError, match="Nenhum dado retornado"):
            loader.fetch_prices("ZZZZ11", "2024-01-01", "2024-12-31")

    def test_raises_on_none_dataframe(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "HAS_YFINANCE", True)
        monkeypatch.setattr(loader, "PRICES_DIR", str(tmp_path / "p"))
        monkeypatch.setattr(loader, "DIVIDENDS_DIR", str(tmp_path / "d"))
        mock_yf = _inject_yf(monkeypatch)

        mock_yf.download.return_value = None
        with pytest.raises(ValueError, match="Nenhum dado retornado"):
            loader.fetch_prices("ZZZZ11", "2024-01-01", "2024-12-31")

    def test_raises_on_download_exception(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "HAS_YFINANCE", True)
        monkeypatch.setattr(loader, "PRICES_DIR", str(tmp_path / "p"))
        monkeypatch.setattr(loader, "DIVIDENDS_DIR", str(tmp_path / "d"))
        mock_yf = _inject_yf(monkeypatch)

        mock_yf.download.side_effect = Exception("network error")
        with pytest.raises(ValueError, match="Erro ao buscar dados"):
            loader.fetch_prices("HGLG11", "2024-01-01", "2024-12-31")

    def test_cache_empty_rows_still_downloads(self, tmp_path, monkeypatch):
        """When cache file exists but has no rows matching date range, should download."""
        monkeypatch.setattr(loader, "HAS_YFINANCE", True)
        prices_dir = str(tmp_path / "prices")
        os.makedirs(prices_dir, exist_ok=True)
        monkeypatch.setattr(loader, "PRICES_DIR", prices_dir)
        monkeypatch.setattr(loader, "DIVIDENDS_DIR", str(tmp_path / "d"))
        mock_yf = _inject_yf(monkeypatch)

        loader._save_csv(
            os.path.join(prices_dir, "HGLG11_prices.csv"),
            [{"date": "2020-01-01", "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"}],
            ["date", "open", "high", "low", "close", "volume"],
        )

        df = _make_dataframe(
            [
                {"date": "2024-06-01", "Open": 150, "High": 155, "Low": 148, "Close": 152, "Volume": 3000},
            ]
        )
        mock_yf.download.return_value = df
        result = loader.fetch_prices("HGLG11", "2024-06-01", "2024-06-30")
        mock_yf.download.assert_called_once()
        assert result[0]["close"] == 152


# ---------------------------------------------------------------------------
# fetch_dividends — mocked yfinance paths
# ---------------------------------------------------------------------------


class TestFetchDividendsWithMockedYfinance:
    """Tests for fetch_dividends with mocked yfinance.Ticker."""

    def test_downloads_and_caches(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "HAS_YFINANCE", True)
        monkeypatch.setattr(loader, "PRICES_DIR", str(tmp_path / "p"))
        divs_dir = str(tmp_path / "divs")
        monkeypatch.setattr(loader, "DIVIDENDS_DIR", divs_dir)
        mock_yf = _inject_yf(monkeypatch)

        series = _make_dividends_series(
            [
                ("2024-06-15", 0.10),
                ("2024-07-15", 0.12),
            ]
        )
        mock_ticker = MagicMock()
        type(mock_ticker).dividends = PropertyMock(return_value=series)
        mock_yf.Ticker.return_value = mock_ticker

        result = loader.fetch_dividends("HGLG11", "2024-06-01", "2024-07-31")

        assert len(result) == 2
        assert result[0]["dividend"] == 0.1
        assert result[1]["dividend"] == 0.12
        cache_file = os.path.join(divs_dir, "HGLG11_dividends.csv")
        assert os.path.exists(cache_file)

    def test_returns_from_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "HAS_YFINANCE", True)
        monkeypatch.setattr(loader, "PRICES_DIR", str(tmp_path / "p"))
        divs_dir = str(tmp_path / "divs")
        os.makedirs(divs_dir, exist_ok=True)
        monkeypatch.setattr(loader, "DIVIDENDS_DIR", divs_dir)
        mock_yf = _inject_yf(monkeypatch)

        loader._save_csv(
            os.path.join(divs_dir, "HGLG11_dividends.csv"),
            [{"date": "2024-06-15", "dividend": "0.10"}],
            ["date", "dividend"],
        )

        result = loader.fetch_dividends("HGLG11", "2024-06-01", "2024-06-30")
        mock_yf.Ticker.assert_not_called()
        assert len(result) == 1

    def test_force_refresh_bypasses_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "HAS_YFINANCE", True)
        monkeypatch.setattr(loader, "PRICES_DIR", str(tmp_path / "p"))
        divs_dir = str(tmp_path / "divs")
        os.makedirs(divs_dir, exist_ok=True)
        monkeypatch.setattr(loader, "DIVIDENDS_DIR", divs_dir)
        mock_yf = _inject_yf(monkeypatch)

        loader._save_csv(
            os.path.join(divs_dir, "HGLG11_dividends.csv"),
            [{"date": "2024-06-15", "dividend": "0.05"}],
            ["date", "dividend"],
        )

        series = _make_dividends_series([("2024-06-15", 0.20)])
        mock_ticker = MagicMock()
        type(mock_ticker).dividends = PropertyMock(return_value=series)
        mock_yf.Ticker.return_value = mock_ticker

        result = loader.fetch_dividends("HGLG11", "2024-06-01", "2024-06-30", force_refresh=True)
        mock_yf.Ticker.assert_called_once()
        assert result[0]["dividend"] == 0.2

    def test_empty_dividends(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "HAS_YFINANCE", True)
        monkeypatch.setattr(loader, "PRICES_DIR", str(tmp_path / "p"))
        monkeypatch.setattr(loader, "DIVIDENDS_DIR", str(tmp_path / "d"))
        mock_yf = _inject_yf(monkeypatch)

        series = _make_dividends_series([])
        mock_ticker = MagicMock()
        type(mock_ticker).dividends = PropertyMock(return_value=series)
        mock_yf.Ticker.return_value = mock_ticker

        result = loader.fetch_dividends("HGLG11", "2024-06-01", "2024-06-30")
        assert result == []

    def test_raises_on_exception(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "HAS_YFINANCE", True)
        monkeypatch.setattr(loader, "PRICES_DIR", str(tmp_path / "p"))
        monkeypatch.setattr(loader, "DIVIDENDS_DIR", str(tmp_path / "d"))
        mock_yf = _inject_yf(monkeypatch)

        mock_yf.Ticker.side_effect = Exception("API down")
        with pytest.raises(ValueError, match="Erro ao buscar dividendos"):
            loader.fetch_dividends("HGLG11", "2024-06-01", "2024-06-30")

    def test_adds_sa_suffix(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "HAS_YFINANCE", True)
        monkeypatch.setattr(loader, "PRICES_DIR", str(tmp_path / "p"))
        monkeypatch.setattr(loader, "DIVIDENDS_DIR", str(tmp_path / "d"))
        mock_yf = _inject_yf(monkeypatch)

        series = _make_dividends_series([])
        mock_ticker = MagicMock()
        type(mock_ticker).dividends = PropertyMock(return_value=series)
        mock_yf.Ticker.return_value = mock_ticker

        loader.fetch_dividends("MXRF11", "2024-06-01", "2024-06-30")
        mock_yf.Ticker.assert_called_with("MXRF11.SA")

    def test_filters_by_date_range(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "HAS_YFINANCE", True)
        monkeypatch.setattr(loader, "PRICES_DIR", str(tmp_path / "p"))
        monkeypatch.setattr(loader, "DIVIDENDS_DIR", str(tmp_path / "d"))
        mock_yf = _inject_yf(monkeypatch)

        series = _make_dividends_series(
            [
                ("2024-05-15", 0.08),
                ("2024-06-15", 0.10),
                ("2024-07-15", 0.12),
                ("2024-08-15", 0.09),
            ]
        )
        mock_ticker = MagicMock()
        type(mock_ticker).dividends = PropertyMock(return_value=series)
        mock_yf.Ticker.return_value = mock_ticker

        result = loader.fetch_dividends("HGLG11", "2024-06-01", "2024-07-31")
        assert len(result) == 2
        assert result[0]["dividend"] == 0.1
        assert result[1]["dividend"] == 0.12
