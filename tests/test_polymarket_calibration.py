"""tests/test_polymarket_calibration.py — Tests for calibration engine."""

import pytest

from core.polymarket_calibration import (
    CalibrationReport,
    ReliabilityPoint,
    _brier_score,
    compute_calibration_stats,
    record_outcome,
    reliability_bins,
)
from core.polymarket_ledger import init_db


@pytest.fixture
def conn(tmp_path):
    db_file = str(tmp_path / "calib_test.db")
    c = init_db(db_file)
    yield c
    c.close()


class TestBrierScore:
    def test_perfect_forecast_is_zero(self):
        # Forecast = outcome → Brier = 0
        assert _brier_score([1.0, 0.0, 1.0], [1.0, 0.0, 1.0]) == pytest.approx(0.0)

    def test_random_50_50_is_baseline(self):
        # All forecasts 0.5, half correct — Brier ≈ 0.25
        forecasts = [0.5] * 100
        outcomes = [1.0 if i % 2 == 0 else 0.0 for i in range(100)]
        score = _brier_score(forecasts, outcomes)
        assert score == pytest.approx(0.25, abs=0.01)

    def test_completely_wrong_is_one(self):
        # Forecast YES with certainty when outcome is NO
        assert _brier_score([1.0], [0.0]) == pytest.approx(1.0)

    def test_empty_returns_baseline(self):
        assert _brier_score([], []) == pytest.approx(0.25)


class TestRecordOutcome:
    def test_inserts_new_record(self, conn):
        result = record_outcome(
            condition_id="cid1",
            entry_prob=0.45,
            ai_estimate=0.70,
            resolved_yes=True,
            conn=conn,
        )
        assert result is True
        row = conn.execute("SELECT * FROM pm_calibration WHERE condition_id='cid1'").fetchone()
        assert row is not None
        assert row["resolved_yes"] == 1
        assert row["entry_prob"] == pytest.approx(0.45)
        assert row["ai_estimate"] == pytest.approx(0.70)

    def test_idempotent_second_insert(self, conn):
        record_outcome("cid1", 0.45, 0.70, True, conn)
        result2 = record_outcome("cid1", 0.50, 0.60, False, conn)
        assert result2 is False
        # First record should be unchanged
        row = conn.execute("SELECT * FROM pm_calibration WHERE condition_id='cid1'").fetchone()
        assert row["entry_prob"] == pytest.approx(0.45)

    def test_accepts_none_ai_estimate(self, conn):
        result = record_outcome("cid2", 0.50, None, False, conn)
        assert result is True
        row = conn.execute("SELECT * FROM pm_calibration WHERE condition_id='cid2'").fetchone()
        assert row["ai_estimate"] is None


class TestComputeCalibrationStats:
    def test_empty_db_returns_defaults(self, conn):
        report = compute_calibration_stats(conn)
        assert report.total_resolved == 0
        assert report.overall_brier == pytest.approx(0.25)
        assert report.categories == []

    def test_perfect_forecasts_yield_zero_brier(self, conn):
        for i in range(5):
            record_outcome(f"cid{i}", 0.9, 1.0, True, conn, category="politics")
        report = compute_calibration_stats(conn)
        assert report.overall_brier == pytest.approx(0.0, abs=0.001)
        assert report.overall_win_rate == pytest.approx(1.0)

    def test_category_breakdown(self, conn):
        record_outcome("cid1", 0.6, 0.8, True, conn, category="sports")
        record_outcome("cid2", 0.4, 0.2, False, conn, category="crypto")
        report = compute_calibration_stats(conn)
        cats = {c.category for c in report.categories}
        assert "sports" in cats
        assert "crypto" in cats

    def test_total_resolved_count(self, conn):
        for i in range(7):
            record_outcome(f"c{i}", 0.55, 0.70, i % 2 == 0, conn)
        report = compute_calibration_stats(conn)
        assert report.total_resolved == 7


class TestReliabilityBins:
    def test_returns_ten_bins(self, conn):
        bins = reliability_bins(conn)
        assert len(bins) == 10

    def test_bins_cover_zero_to_one(self, conn):
        bins = reliability_bins(conn)
        assert bins[0].bin_low == pytest.approx(0.0)
        assert bins[-1].bin_high == pytest.approx(1.0)

    def test_bin_count_matches_inserted_records(self, conn):
        # Insert 3 forecasts all in the 0.6–0.7 bin
        for i in range(3):
            record_outcome(f"c{i}", 0.5, 0.65, True, conn)
        bins = reliability_bins(conn)
        bin_60_70 = next(b for b in bins if b.bin_low == pytest.approx(0.6))
        assert bin_60_70.count == 3

    def test_empty_bins_have_zero_count(self, conn):
        bins = reliability_bins(conn)
        assert all(b.count == 0 for b in bins)
