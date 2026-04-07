"""
core/cluster_engine.py

Clustering de FIIs por perfil de retorno histórico.

Implementa K-Means em Python puro (sem sklearn) para agrupar ativos
com comportamento similar. Útil para:
- Identificar grupos com alta correlação implícita
- Evitar tickers do mesmo cluster no Markowitz
- Visualizar perfis de risco/retorno no dashboard

Funções puras, sem dependências externas.
"""

import math
import random
import statistics

# ---------------------------------------------------------------------------
# Extração de features
# ---------------------------------------------------------------------------


def extract_features(monthly_returns: list[float]) -> dict[str, float]:
    """
    Extrai features quantitativas de uma série de retornos mensais.

    Features:
        - retorno_medio: Média dos retornos mensais
        - volatilidade: Desvio padrão dos retornos
        - retorno_12m: Retorno acumulado dos últimos 12 meses
        - max_drawdown: Maior queda acumulada
        - skewness: Assimetria da distribuição (positiva = mais ganhos extremos)

    Args:
        monthly_returns: Série de retornos mensais decimais.

    Returns:
        dict com as 5 features numéricas.
    """
    if not monthly_returns:
        return {"retorno_medio": 0, "volatilidade": 0, "retorno_12m": 0, "max_drawdown": 0, "skewness": 0}

    # Retorno médio
    avg = sum(monthly_returns) / len(monthly_returns)

    # Volatilidade
    vol = statistics.stdev(monthly_returns) if len(monthly_returns) > 1 else 0.0

    # Retorno acumulado 12m
    window = monthly_returns[-12:] if len(monthly_returns) >= 12 else monthly_returns
    r12m = 1.0
    for r in window:
        r12m *= 1 + r
    r12m -= 1.0

    # Max drawdown
    peak = 1.0
    wealth = 1.0
    worst = 0.0
    for r in monthly_returns:
        wealth *= 1 + r
        if wealth > peak:
            peak = wealth
        dd = (wealth - peak) / peak
        if dd < worst:
            worst = dd

    # Skewness
    if vol > 0 and len(monthly_returns) >= 3:
        n = len(monthly_returns)
        skew = sum(((x - avg) / vol) ** 3 for x in monthly_returns) / n
    else:
        skew = 0.0

    return {
        "retorno_medio": round(avg, 6),
        "volatilidade": round(vol, 6),
        "retorno_12m": round(r12m, 6),
        "max_drawdown": round(worst, 6),
        "skewness": round(skew, 4),
    }


def extract_feature_matrix(
    return_series: dict[str, list[float]],
) -> tuple[list[str], list[list[float]]]:
    """
    Extrai a matriz de features de todos os ativos.

    Args:
        return_series: Mapa ticker → lista de retornos.

    Returns:
        tuple: (lista de tickers, matriz de features [[f1, f2, ...], ...])
    """
    tickers = list(return_series.keys())
    features_keys = ["retorno_medio", "volatilidade", "retorno_12m", "max_drawdown", "skewness"]
    matrix = []
    for t in tickers:
        feats = extract_features(return_series[t])
        matrix.append([feats[k] for k in features_keys])
    return tickers, matrix


# ---------------------------------------------------------------------------
# Normalização (min-max)
# ---------------------------------------------------------------------------


def normalize_matrix(matrix: list[list[float]]) -> list[list[float]]:
    """
    Normaliza cada coluna da matriz no intervalo [0, 1].

    Args:
        matrix: Matriz de features (n_ativos × n_features).

    Returns:
        list[list[float]]: Matriz normalizada.
    """
    if not matrix or not matrix[0]:
        return matrix

    n_cols = len(matrix[0])
    col_mins = [min(row[c] for row in matrix) for c in range(n_cols)]
    col_maxs = [max(row[c] for row in matrix) for c in range(n_cols)]

    result = []
    for row in matrix:
        norm_row = []
        for c in range(n_cols):
            rng = col_maxs[c] - col_mins[c]
            val = (row[c] - col_mins[c]) / rng if rng > 1e-10 else 0.0
            norm_row.append(val)
        result.append(norm_row)
    return result


# ---------------------------------------------------------------------------
# K-Means
# ---------------------------------------------------------------------------


def _euclidean(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _centroid(points: list[list[float]]) -> list[float]:
    if not points:
        return [0.0]
    n = len(points[0])
    return [sum(p[i] for p in points) / len(points) for i in range(n)]


def kmeans(
    matrix: list[list[float]],
    k: int,
    max_iter: int = 100,
    seed: int = 42,
) -> list[int]:
    """
    K-Means em Python puro.

    Args:
        matrix: Matriz de features (n_ativos × n_features).
        k: Número de clusters.
        max_iter: Máximo de iterações.
        seed: Semente aleatória para reprodutibilidade.

    Returns:
        list[int]: Lista de labels de cluster para cada ativo (0-indexed).
    """
    if len(matrix) <= k:
        return list(range(len(matrix)))

    rng = random.Random(seed)
    # Inicialização: escolhe k pontos aleatórios como centroids
    centroids = [matrix[i] for i in rng.sample(range(len(matrix)), k)]

    labels = [0] * len(matrix)

    for _ in range(max_iter):
        # Atribuição
        new_labels = []
        for point in matrix:
            dists = [_euclidean(point, c) for c in centroids]
            new_labels.append(dists.index(min(dists)))

        # Verificar convergência
        if new_labels == labels:
            break
        labels = new_labels

        # Atualização dos centroids
        for ci in range(k):
            cluster_points = [matrix[i] for i, l in enumerate(labels) if l == ci]
            if cluster_points:
                centroids[ci] = _centroid(cluster_points)

    return labels


def auto_k(n_ativos: int) -> int:
    """
    Sugestão automática de K baseada no número de ativos.
    Regra: sqrt(n/2) arredondado, mínimo 2, máximo 6.
    """
    k = max(2, min(6, round(math.sqrt(n_ativos / 2))))
    return k


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def cluster_portfolio(
    return_series: dict[str, list[float]],
    k: int | None = None,
    seed: int = 42,
) -> dict:
    """
    Clusteriza os ativos da carteira por perfil de retorno.

    Args:
        return_series: Mapa ticker → retornos mensais.
        k: Número de clusters. Se None, calculado automaticamente.
        seed: Semente aleatória.

    Returns:
        dict com:
            - clusters: dict label → lista de tickers
            - labels: dict ticker → label de cluster
            - features: dict ticker → features extraídas
            - k: número de clusters usado
    """
    tickers, matrix = extract_feature_matrix(return_series)

    if len(tickers) < 2:
        return {
            "clusters": {0: tickers},
            "labels": {t: 0 for t in tickers},
            "features": {t: extract_features(return_series[t]) for t in tickers},
            "k": 1,
        }

    k_used = k or auto_k(len(tickers))
    k_used = min(k_used, len(tickers))

    norm_matrix = normalize_matrix(matrix)
    raw_labels = kmeans(norm_matrix, k_used, seed=seed)

    # Organizar resultado
    clusters: dict[int, list[str]] = {}
    labels_map: dict[str, int] = {}

    for i, ticker in enumerate(tickers):
        lbl = raw_labels[i]
        labels_map[ticker] = lbl
        clusters.setdefault(lbl, []).append(ticker)

    # Nomear clusters com base no perfil dominante
    cluster_names = _name_clusters(clusters, return_series)

    features_map = {t: extract_features(return_series[t]) for t in tickers}

    return {
        "clusters": clusters,
        "cluster_names": cluster_names,
        "labels": labels_map,
        "features": features_map,
        "k": k_used,
    }


def _name_clusters(
    clusters: dict[int, list[str]],
    return_series: dict[str, list[float]],
) -> dict[int, str]:
    """Nomeia clusters automaticamente com base no perfil de retorno/risco médio."""
    names = {}
    for lbl, tickers in clusters.items():
        avgs = []
        vols = []
        for t in tickers:
            feats = extract_features(return_series[t])
            avgs.append(feats["retorno_medio"])
            vols.append(feats["volatilidade"])

        avg_ret = sum(avgs) / len(avgs) if avgs else 0
        avg_vol = sum(vols) / len(vols) if vols else 0

        if avg_ret > 0.008 and avg_vol < 0.025:
            name = f"Cluster {lbl+1} — Alto Retorno / Baixo Risco 🟢"
        elif avg_ret > 0.006 and avg_vol < 0.035:
            name = f"Cluster {lbl+1} — Retorno Moderado 🟡"
        elif avg_vol >= 0.035:
            name = f"Cluster {lbl+1} — Alta Volatilidade 🔴"
        else:
            name = f"Cluster {lbl+1} — Perfil Defensivo 🔵"
        names[lbl] = name
    return names


def tickers_same_cluster(cluster_result: dict, ticker: str) -> list[str]:
    """
    Retorna todos os ativos no mesmo cluster que um ticker específico
    (excluindo o próprio ticker).
    """
    lbl = cluster_result["labels"].get(ticker)
    if lbl is None:
        return []
    return [t for t in cluster_result["clusters"].get(lbl, []) if t != ticker]


def suggest_diversification(cluster_result: dict) -> list[str]:
    """
    Sugere remover de cada cluster todos menos 1-2 ativos
    (escolhe o de melhor retorno médio por cluster).

    Returns:
        list[str]: Tickers que formam a carteira mais diversificada entre clusters.
    """
    selected = []
    features_map = cluster_result.get("features", {})

    for lbl, tickers in cluster_result["clusters"].items():
        # Ordenar por retorno médio desc dentro do cluster
        by_return = sorted(
            tickers,
            key=lambda t: features_map.get(t, {}).get("retorno_medio", 0),
            reverse=True,
        )
        # Selecionar top 1 ou 2 por cluster
        n_pick = 2 if len(tickers) >= 4 else 1
        selected.extend(by_return[:n_pick])

    return selected
