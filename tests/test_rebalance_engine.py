"""Tests for services/rebalance_engine.py — Drift detection and rebalancing triggers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from services.rebalance_engine import (
    calculate_weight_drift,
    should_rebalance,
    detect_universe_change,
    run_rebalance_check,
)


class TestCalculateWeightDrift:
    def test_no_drift(self):
        current = {"HGLG11": 0.50, "XPML11": 0.50}
        target = {"HGLG11": 0.50, "XPML11": 0.50}
        drift = calculate_weight_drift(current, target)
        assert drift["HGLG11"] == pytest.approx(0.0)
        assert drift["XPML11"] == pytest.approx(0.0)

    def test_positive_drift(self):
        current = {"HGLG11": 0.60, "XPML11": 0.40}
        target = {"HGLG11": 0.50, "XPML11": 0.50}
        drift = calculate_weight_drift(current, target)
        assert drift["HGLG11"] == pytest.approx(0.10)
        assert drift["XPML11"] == pytest.approx(0.10)

    def test_missing_in_current(self):
        current = {"HGLG11": 1.0}
        target = {"HGLG11": 0.50, "XPML11": 0.50}
        drift = calculate_weight_drift(current, target)
        assert drift["XPML11"] == pytest.approx(0.50)

    def test_missing_in_target(self):
        current = {"HGLG11": 0.50, "OLD11": 0.50}
        target = {"HGLG11": 1.0}
        drift = calculate_weight_drift(current, target)
        assert drift["OLD11"] == pytest.approx(0.50)


class TestShouldRebalance:
    def test_within_threshold(self):
        drift = {"HGLG11": 0.03, "XPML11": 0.02}
        assert should_rebalance(drift, 0.05) is False

    def test_exceeds_threshold(self):
        drift = {"HGLG11": 0.06, "XPML11": 0.02}
        assert should_rebalance(drift, 0.05) is True

    def test_exact_threshold_not_triggered(self):
        drift = {"HGLG11": 0.05}
        assert should_rebalance(drift, 0.05) is False

    def test_custom_threshold(self):
        drift = {"HGLG11": 0.08}
        assert should_rebalance(drift, 0.10) is False
        assert should_rebalance(drift, 0.07) is True


class TestDetectUniverseChange:
    def test_same_universe(self):
        assert detect_universe_change({"A", "B"}, {"A", "B"}) is False

    def test_added_asset(self):
        assert detect_universe_change({"A", "B"}, {"A", "B", "C"}) is True

    def test_removed_asset(self):
        assert detect_universe_change({"A", "B"}, {"A"}) is True


class TestRunRebalanceCheck:
    def test_no_rebalance_needed(self):
        current = {"HGLG11": 0.50, "XPML11": 0.50}
        target = {"HGLG11": 0.50, "XPML11": 0.50}
        universe = {"HGLG11", "XPML11"}
        assert run_rebalance_check(current, target, universe, universe) is False

    def test_drift_triggers_rebalance(self):
        current = {"HGLG11": 0.70, "XPML11": 0.30}
        target = {"HGLG11": 0.50, "XPML11": 0.50}
        universe = {"HGLG11", "XPML11"}
        assert run_rebalance_check(current, target, universe, universe) is True

    def test_universe_change_triggers_rebalance(self):
        current = {"HGLG11": 0.50, "XPML11": 0.50}
        target = {"HGLG11": 0.50, "XPML11": 0.50}
        old_u = {"HGLG11", "XPML11"}
        new_u = {"HGLG11", "VISC11"}
        assert run_rebalance_check(current, target, old_u, new_u) is True
