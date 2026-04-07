"""
tests/test_momentum_engine.py

Testes unitários para core/momentum_engine.py e core/cluster_engine.py.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.momentum_engine import (
    cumulative_return,
    annualized_return,
    momentum_score,
    rank_by_momentum,
    top_momentum,
    filter_positive_momentum,
    momentum_vs_benchmark,
)
from core.cluster_engine import (
    extract_features,
    extract_feature_matrix,
    normalize_matrix,
    kmeans,
    cluster_portfolio,
    tickers_same_cluster,
    suggest_diversification,
)


def assert_close(a: float, b: float, tol: float = 0.005, label: str = "") -> None:
    if abs(a - b) > tol:
        raise AssertionError(f"{'['+label+'] ' if label else ''}Esperado ~{b:.4f}, obtido {a:.4f}")


def run_test(name: str, fn) -> bool:
    try:
        fn()
        print(f"  ✅ {name}")
        return True
    except AssertionError as e:
        print(f"  ❌ {name}: {e}")
        return False
    except Exception as e:
        print(f"  !! {name}: {type(e).__name__}: {e}")
        return False


# --- Dados de teste ---
RETURNS_ALTA = [0.012, 0.015, 0.010, 0.018, 0.011, 0.014, 0.009, 0.016, 0.013, 0.012, 0.015, 0.014]
RETURNS_QUEDA = [-0.020, -0.015, -0.018, -0.022, -0.010, -0.012, -0.009, -0.015, -0.014, -0.011, -0.013, -0.016]
RETURNS_NEUTRO = [0.001, -0.001, 0.002, -0.002, 0.001, 0.000, -0.001, 0.001, 0.000, 0.002, -0.001, 0.001]

RETURN_SERIES = {
    "MXRF11": RETURNS_ALTA,
    "HGLG11": [0.009, 0.011, 0.008, 0.010, 0.012, 0.009, 0.013, 0.010, 0.009, 0.011, 0.010, 0.012],
    "XPML11": RETURNS_QUEDA,
    "KNCR11": RETURNS_NEUTRO,
    "BRCR11": [-0.005, 0.003, -0.002, 0.004, -0.003, 0.002, -0.001, 0.003, 0.002, -0.002, 0.004, 0.001],
}


# ===========================================================================
# MOMENTUM ENGINE
# ===========================================================================


def test_cumulative_return_positivo():
    r = cumulative_return([0.01, 0.01, 0.01], 3)
    assert_close(r, 0.0303, label="cum_return 3×1%")


def test_cumulative_return_n_menor():
    """Se n_months > len, usa tudo."""
    r = cumulative_return([0.01, 0.02], 12)
    assert r > 0


def test_cumulative_return_vazio():
    assert cumulative_return([], 6) == 0.0


def test_annualized_return_positivo():
    r = annualized_return(RETURNS_ALTA)
    assert r > 0.10, f"Esperado > 10% anual, obtido {r*100:.2f}%"


def test_annualized_return_vazio():
    assert annualized_return([]) == 0.0


def test_momentum_score_chaves():
    ms = momentum_score(RETURNS_ALTA)
    for k in ("retorno_1m", "retorno_3m", "retorno_6m", "retorno_12m", "score", "classificacao"):
        assert k in ms, f"Chave '{k}' ausente"


def test_momentum_score_alta():
    ms = momentum_score(RETURNS_ALTA)
    assert ms["score"] > 0, f"Score deveria ser positivo: {ms['score']}"


def test_momentum_score_queda():
    ms = momentum_score(RETURNS_QUEDA)
    assert ms["score"] < 0, f"Score deveria ser negativo: {ms['score']}"


def test_momentum_score_classificacao_forte_alta():
    ms = momentum_score(RETURNS_ALTA)
    assert "Alta" in ms["classificacao"], f"Esperado 'Alta': {ms['classificacao']}"


def test_momentum_score_classificacao_forte_alta_branch():
    """Score >= 0.12 must produce 'Forte Alta' classification (line 93)."""
    # Monthly returns of ~2.5% yield 12m ≈ 34%, 6m ≈ 16%, score well above 0.12
    very_high = [0.025] * 12
    ms = momentum_score(very_high)
    assert ms["classificacao"] == "🔥 Forte Alta", f"Esperado Forte Alta, obtido: {ms['classificacao']}"
    assert ms["score"] >= 0.12


def test_momentum_score_classificacao_queda_moderada():
    """Score between -0.06 and 0.0 must produce 'Queda Moderada' (line 99)."""
    # Monthly returns of -0.4% yield score in the -0.06 to 0.0 band
    mild_negative = [-0.004] * 12
    ms = momentum_score(mild_negative)
    assert ms["classificacao"] == "📉 Queda Moderada", f"Esperado Queda Moderada, obtido: {ms['classificacao']}"
    assert -6.0 <= ms["score"] < 0.0


def test_rank_by_momentum_ordenado():
    ranking = rank_by_momentum(RETURN_SERIES)
    for i in range(len(ranking) - 1):
        assert ranking[i]["score"] >= ranking[i + 1]["score"], "Ranking não está ordenado"


def test_rank_by_momentum_todos_tickers():
    ranking = rank_by_momentum(RETURN_SERIES)
    assert len(ranking) == len(RETURN_SERIES)


def test_top_momentum_n():
    top = top_momentum(RETURN_SERIES, n=3)
    assert len(top) == 3


def test_filter_positive_momentum():
    positivos = filter_positive_momentum(RETURN_SERIES)
    assert all(r in RETURN_SERIES for r in positivos)
    # Pelo menos MXRF11 (RETURNS_ALTA) deve estar
    assert "MXRF11" in positivos or len(positivos) > 0


def test_momentum_vs_benchmark():
    r = momentum_vs_benchmark(RETURNS_ALTA, RETURNS_QUEDA, n_months=12)
    for k in ("retorno_ativo_%", "retorno_benchmark_%", "alpha_%", "result"):
        assert k in r
    assert r["alpha_%"] > 0, "RETURNS_ALTA deve superar RETURNS_QUEDA"


# ===========================================================================
# CLUSTER ENGINE
# ===========================================================================


def test_extract_features_chaves():
    feats = extract_features(RETURNS_ALTA)
    for k in ("retorno_medio", "volatilidade", "retorno_12m", "max_drawdown", "skewness"):
        assert k in feats


def test_extract_features_vol_positiva():
    feats = extract_features(RETURNS_ALTA)
    assert feats["volatilidade"] > 0


def test_extract_features_drawdown_negativo():
    feats = extract_features(RETURNS_QUEDA)
    assert feats["max_drawdown"] < 0


def test_extract_feature_matrix():
    tickers, matrix = extract_feature_matrix(RETURN_SERIES)
    assert len(tickers) == len(RETURN_SERIES)
    assert len(matrix) == len(RETURN_SERIES)
    assert len(matrix[0]) == 5  # 5 features


def test_normalize_matrix_bounds():
    matrix = [[1.0, 2.0], [3.0, 4.0], [2.0, 3.0]]
    norm = normalize_matrix(matrix)
    for row in norm:
        for v in row:
            assert -0.01 <= v <= 1.01, f"Valor fora de [0,1]: {v}"


def test_kmeans_labels_count():
    matrix = [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.1, 0.9], [0.5, 0.5], [0.6, 0.4]]
    labels = kmeans(matrix, k=2)
    assert len(labels) == len(matrix)


def test_kmeans_k_valido():
    matrix = [[i * 0.1, i * 0.05] for i in range(10)]
    labels = kmeans(matrix, k=3)
    assert len(set(labels)) <= 3


def test_cluster_portfolio_chaves():
    result = cluster_portfolio(RETURN_SERIES)
    for k in ("clusters", "labels", "features", "k"):
        assert k in result


def test_cluster_portfolio_todos_tickers():
    result = cluster_portfolio(RETURN_SERIES)
    assert set(result["labels"].keys()) == set(RETURN_SERIES.keys())


def test_cluster_portfolio_k_auto():
    result = cluster_portfolio(RETURN_SERIES)
    assert 1 <= result["k"] <= 6


def test_tickers_same_cluster():
    result = cluster_portfolio(RETURN_SERIES)
    same = tickers_same_cluster(result, "MXRF11")
    assert "MXRF11" not in same  # não inclui o próprio ticker


def test_suggest_diversification():
    result = cluster_portfolio(RETURN_SERIES)
    sugestao = suggest_diversification(result)
    assert len(sugestao) >= 1
    assert len(sugestao) <= len(RETURN_SERIES)


# ---------------------------------------------------------------------------
# cluster_engine — edge case tests to cover remaining branches
# ---------------------------------------------------------------------------


def test_extract_features_empty_returns_zeros():
    """extract_features([]) must return the zero-dict (line 42)."""
    feats = extract_features([])
    assert feats["retorno_medio"] == 0
    assert feats["volatilidade"] == 0
    assert feats["retorno_12m"] == 0
    assert feats["max_drawdown"] == 0
    assert feats["skewness"] == 0


def test_extract_features_single_element_skewness_zero():
    """Single element: vol==0, skewness must be 0.0 (else branch at line 74)."""
    feats = extract_features([0.05])
    assert feats["skewness"] == 0.0
    assert feats["volatilidade"] == 0.0


def test_extract_features_two_elements_skewness_zero():
    """Two elements: len < 3, skewness must be 0.0 (else branch at line 74)."""
    feats = extract_features([0.01, 0.02])
    assert feats["skewness"] == 0.0


def test_normalize_matrix_empty_returns_unchanged():
    """normalize_matrix([]) must return the input unchanged (line 122)."""
    assert normalize_matrix([]) == []


def test_normalize_matrix_row_with_empty_cols():
    """normalize_matrix([[]] triggers the not matrix[0] guard (line 122)."""
    result = normalize_matrix([[]])
    assert result == [[]]


def test_centroid_empty_points():
    """_centroid([]) must return [0.0] (line 150)."""
    from core.cluster_engine import _centroid
    assert _centroid([]) == [0.0]


def test_kmeans_matrix_smaller_than_k():
    """When len(matrix) <= k, return range labels without running k-means (line 174)."""
    matrix = [[1.0, 0.0], [0.0, 1.0]]
    labels = kmeans(matrix, k=5)
    assert labels == [0, 1]


def test_cluster_portfolio_single_ticker():
    """cluster_portfolio with <2 tickers returns k=1 early (line 240)."""
    series = {"MXRF11": RETURNS_ALTA}
    result = cluster_portfolio(series)
    assert result["k"] == 1
    assert "MXRF11" in result["labels"]
    assert result["labels"]["MXRF11"] == 0


def test_tickers_same_cluster_unknown_ticker_returns_empty():
    """tickers_same_cluster with unknown ticker returns [] (line 312)."""
    result = cluster_portfolio(RETURN_SERIES)
    same = tickers_same_cluster(result, "ZZZZ11")
    assert same == []


def test_cluster_name_moderate_profile():
    """Force cluster whose avg_ret is in the Retorno Moderado band (line 296)."""
    # avg_ret=0.007 (>0.006), avg_vol=0.020 (<0.035) → Retorno Moderado
    moderate_returns = [0.007] * 24
    series = {"A11": moderate_returns, "B11": moderate_returns, "C11": moderate_returns}
    result = cluster_portfolio(series, k=1)
    names = result.get("cluster_names", {})
    assert any("Moderado" in v for v in names.values())


def test_cluster_name_high_volatility_profile():
    """Force cluster whose avg_vol >= 0.035 → Alta Volatilidade (line 298)."""
    # alternating 0 and 0.10 gives high standard deviation
    high_vol = [0.0 if i % 2 == 0 else 0.10 for i in range(24)]
    series = {"X11": high_vol, "Y11": high_vol, "Z11": high_vol}
    result = cluster_portfolio(series, k=1)
    names = result.get("cluster_names", {})
    assert any("Volatilidade" in v for v in names.values())


# ===========================================================================
# Runner
# ===========================================================================


def main() -> bool:
    tests_momentum = [
        ("Retorno acumulado positivo", test_cumulative_return_positivo),
        ("Retorno acumulado n < len", test_cumulative_return_n_menor),
        ("Retorno acumulado vazio", test_cumulative_return_vazio),
        ("Retorno anualizado positivo", test_annualized_return_positivo),
        ("Retorno anualizado vazio", test_annualized_return_vazio),
        ("Momentum score: chaves", test_momentum_score_chaves),
        ("Momentum score: alta positivo", test_momentum_score_alta),
        ("Momentum score: queda negativo", test_momentum_score_queda),
        ("Momentum score: classificação Forte Alta", test_momentum_score_classificacao_forte_alta),
        ("Rank ordenado decrescente", test_rank_by_momentum_ordenado),
        ("Rank: todos tickers", test_rank_by_momentum_todos_tickers),
        ("Top N momentum", test_top_momentum_n),
        ("Filtro momentum positivo", test_filter_positive_momentum),
        ("Momentum vs benchmark", test_momentum_vs_benchmark),
    ]

    tests_cluster = [
        ("Extract features: chaves", test_extract_features_chaves),
        ("Extract features: vol > 0", test_extract_features_vol_positiva),
        ("Extract features: drawdown < 0", test_extract_features_drawdown_negativo),
        ("Feature matrix: dimensões", test_extract_feature_matrix),
        ("Normalização: [0,1]", test_normalize_matrix_bounds),
        ("K-Means: quantidade de labels", test_kmeans_labels_count),
        ("K-Means: clusters <= k", test_kmeans_k_valido),
        ("Cluster portfolio: chaves", test_cluster_portfolio_chaves),
        ("Cluster portfolio: todos tickers", test_cluster_portfolio_todos_tickers),
        ("Cluster portfolio: k automático", test_cluster_portfolio_k_auto),
        ("Same cluster: exclui próprio ticker", test_tickers_same_cluster),
        ("Suggest diversification: não vazio", test_suggest_diversification),
    ]

    print("\n" + "=" * 58)
    print("  ALPHACOTA — TEST SUITE: Momentum Engine")
    print("=" * 58)
    passed_m = sum(run_test(n, f) for n, f in tests_momentum)

    print("\n" + "=" * 58)
    print("  ALPHACOTA — TEST SUITE: Cluster Engine")
    print("=" * 58)
    passed_c = sum(run_test(n, f) for n, f in tests_cluster)

    total = len(tests_momentum) + len(tests_cluster)
    passed = passed_m + passed_c
    failed = total - passed

    print("=" * 58)
    print(f"  Resultado: {passed}/{total} testes passaram")
    print("  🎉 TODOS PASSARAM!" if failed == 0 else f"  ⚠️  {failed} falhas.")
    print("=" * 58 + "\n")
    return failed == 0


if __name__ == "__main__":
    import sys

    sys.exit(0 if main() else 1)
