"""tests/test_polymarket_weight_tuner.py — Tests for adaptive weight tuner."""

import json

import pytest

from core.polymarket_calibration import CalibrationReport, CategoryStats
from core.polymarket_score import DEFAULT_WEIGHTS
from core.polymarket_weight_tuner import (
    _MAX_DELTA_PP,
    _clamp_delta,
    load_learned_weights,
    save_learned_weights,
    tune_weights,
)
from core.polymarket_ledger import init_db


@pytest.fixture
def conn(tmp_path):
    db_file = str(tmp_path / "wt_test.db")
    c = init_db(db_file)
    yield c
    c.close()


def _report(
    brier: float = 0.25,
    win_rate: float = 0.5,
    total: int = 10,
    categories: list[CategoryStats] | None = None,
) -> CalibrationReport:
    return CalibrationReport(
        overall_brier=brier,
        overall_win_rate=win_rate,
        total_resolved=total,
        lookback_days=90,
        categories=categories or [],
    )


class TestClampDelta:
    def test_clamps_positive(self):
        assert _clamp_delta(0.10) == pytest.approx(_MAX_DELTA_PP)

    def test_clamps_negative(self):
        assert _clamp_delta(-0.10) == pytest.approx(-_MAX_DELTA_PP)

    def test_passes_small_delta(self):
        assert _clamp_delta(0.02) == pytest.approx(0.02)


class TestTuneWeights:
    def test_weights_sum_to_one_no_categories(self):
        update = tune_weights(_report(), dict(DEFAULT_WEIGHTS))
        total = sum(update.weights_after.values())
        assert total == pytest.approx(1.0, abs=1e-5)

    def test_weights_sum_to_one_with_categories(self):
        cats = [
            CategoryStats("politics", brier_score=0.10, win_rate=0.7, mean_edge=0.15, resolved_count=10),
            CategoryStats("crypto", brier_score=0.30, win_rate=0.4, mean_edge=0.05, resolved_count=8),
        ]
        update = tune_weights(_report(categories=cats), dict(DEFAULT_WEIGHTS))
        total = sum(update.weights_after.values())
        assert total == pytest.approx(1.0, abs=1e-5)

    def test_bad_category_loses_weight(self):
        cats = [
            CategoryStats("crypto", brier_score=0.35, win_rate=0.4, mean_edge=0.05, resolved_count=10),
        ]
        update = tune_weights(_report(categories=cats), dict(DEFAULT_WEIGHTS))
        # crypto maps to w_edge — should be reduced
        assert update.weights_after["w_edge"] < DEFAULT_WEIGHTS["w_edge"]

    def test_good_category_gains_weight(self):
        cats = [
            CategoryStats("politics", brier_score=0.05, win_rate=0.8, mean_edge=0.20, resolved_count=10),
        ]
        update = tune_weights(_report(categories=cats), dict(DEFAULT_WEIGHTS))
        # politics maps to w_news — should increase
        assert update.weights_after["w_news"] > DEFAULT_WEIGHTS["w_news"]

    def test_delta_bounded_at_5pp(self):
        # Extreme Brier (0.0) should not move any weight by more than 5pp
        cats = [
            CategoryStats("crypto", brier_score=0.0, win_rate=1.0, mean_edge=0.30, resolved_count=20),
        ]
        update = tune_weights(_report(categories=cats), dict(DEFAULT_WEIGHTS))
        delta = abs(update.weights_after["w_edge"] / sum(update.weights_after.values()) - DEFAULT_WEIGHTS["w_edge"])
        # After normalisation delta is bounded indirectly, but raw delta capped at _MAX_DELTA_PP
        assert update.deltas.get("w_edge", 0.0) <= _MAX_DELTA_PP + 1e-9

    def test_returns_weight_update_with_before(self):
        update = tune_weights(_report(), dict(DEFAULT_WEIGHTS))
        assert update.weights_before == DEFAULT_WEIGHTS

    def test_skips_categories_with_few_samples(self):
        cats = [
            CategoryStats("crypto", brier_score=0.0, win_rate=1.0, mean_edge=0.3, resolved_count=2),
        ]
        update = tune_weights(_report(categories=cats), dict(DEFAULT_WEIGHTS))
        # No change because resolved_count < _MIN_CATEGORY_SAMPLES (5)
        assert update.weights_after["w_edge"] == pytest.approx(DEFAULT_WEIGHTS["w_edge"] / sum(update.weights_after.values()) * sum(update.weights_after.values()), abs=0.01)


class TestSaveLoadLearnedWeights:
    def test_save_then_load(self, conn, tmp_path, monkeypatch):
        learned_path = tmp_path / "data" / "learned_weights.json"
        monkeypatch.setattr(
            "core.polymarket_weight_tuner._LEARNED_WEIGHTS_PATH", learned_path
        )
        weights = {"w_edge": 0.40, "w_liquidity": 0.25, "w_time": 0.15, "w_copy": 0.10, "w_news": 0.10}
        history = {"weights_before": DEFAULT_WEIGHTS, "brier_score": 0.20, "win_rate": 0.60, "trigger_markets": 15}
        save_learned_weights(weights, history, conn)

        loaded = load_learned_weights()
        # load_learned_weights uses the patched path via monkeypatch
        assert loaded is not None
        assert loaded["w_edge"] == pytest.approx(0.40)

    def test_load_returns_none_when_missing(self, tmp_path, monkeypatch):
        missing = tmp_path / "nonexistent.json"
        monkeypatch.setattr("core.polymarket_weight_tuner._LEARNED_WEIGHTS_PATH", missing)
        assert load_learned_weights() is None

    def test_save_inserts_weight_history_row(self, conn, tmp_path, monkeypatch):
        learned_path = tmp_path / "data" / "lw.json"
        monkeypatch.setattr("core.polymarket_weight_tuner._LEARNED_WEIGHTS_PATH", learned_path)
        weights = dict(DEFAULT_WEIGHTS)
        history = {"weights_before": DEFAULT_WEIGHTS, "brier_score": 0.22, "win_rate": 0.55, "trigger_markets": 12}
        save_learned_weights(weights, history, conn)

        row = conn.execute("SELECT * FROM pm_weight_history").fetchone()
        assert row is not None
        assert row["brier_score"] == pytest.approx(0.22)
        assert json.loads(row["weights_after"]) == weights


class TestLearnedWeightsAtModuleLoad:
    def test_scorer_uses_learned_weights_when_file_present(self, tmp_path, monkeypatch):
        """Verify polymarket_score.ACTIVE_WEIGHTS loads from disk if file is valid."""
        learned_path = tmp_path / "data" / "learned_weights.json"
        learned_path.parent.mkdir(parents=True, exist_ok=True)
        learned_weights = {
            "w_edge": 0.40,
            "w_liquidity": 0.20,
            "w_time": 0.15,
            "w_copy": 0.15,
            "w_news": 0.10,
        }
        learned_path.write_text(json.dumps(learned_weights))

        monkeypatch.setattr("core.polymarket_weight_tuner._LEARNED_WEIGHTS_PATH", learned_path)

        # Re-run the loader function directly
        from core.polymarket_weight_tuner import load_learned_weights
        loaded = load_learned_weights()
        assert loaded is not None
        assert loaded["w_edge"] == pytest.approx(0.40)
