"""
clustering.py
--------------
Agrupa empresas en "peer groups" usando k-means sobre sus métricas financieras
reales (growth, márgenes, apalancamiento, valuación) — en vez de solo la
industria que se les asignó manualmente. Dos empresas de industrias distintas
pero con perfil financiero parecido (mismo crecimiento, mismo apalancamiento)
terminan en el mismo cluster, lo cual da un grupo de comparables más preciso
para calcular el descuento/premium de valuación.

Implementado con numpy puro (sin scikit-learn) para no agregar una dependencia
pesada al proyecto.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

FEATURE_COLUMNS = ["revenue_growth", "ebitda_margin", "debt_ebitda", "ev_ebitda"]


def _standardize(X: np.ndarray) -> np.ndarray:
    """Escala cada columna a media 0 / desviación estándar 1, para que ninguna
    métrica domine solo por tener números más grandes (ej. ev_ebitda vs. growth)."""
    mean = np.nanmean(X, axis=0)
    std = np.nanstd(X, axis=0)
    std[std == 0] = 1.0
    return (X - mean) / std


def _kmeans(X: np.ndarray, k: int, n_iter: int = 100, seed: int = 42) -> np.ndarray:
    """K-means básico: asigna cada punto al centroide más cercano, recalcula
    centroides, repite hasta que no cambien (o se acaben las iteraciones)."""
    rng = np.random.default_rng(seed)
    n = X.shape[0]
    k = min(k, n)  # no puede haber más clusters que empresas

    # Inicialización: elegir k puntos reales al azar como centroides iniciales
    init_idx = rng.choice(n, size=k, replace=False)
    centroids = X[init_idx].copy()

    labels = np.zeros(n, dtype=int)
    for _ in range(n_iter):
        distances = np.linalg.norm(X[:, None, :] - centroids[None, :, :], axis=2)
        new_labels = np.argmin(distances, axis=1)

        if np.array_equal(new_labels, labels) and _ > 0:
            break
        labels = new_labels

        for c in range(k):
            members = X[labels == c]
            if len(members) > 0:
                centroids[c] = members.mean(axis=0)

    return labels


def assign_peer_clusters(df: pd.DataFrame, companies_per_cluster: int = 6) -> pd.Series:
    """
    Devuelve una Serie con el número de cluster asignado a cada empresa.
    El número de clusters se elige automáticamente para que cada uno tenga,
    en promedio, ~companies_per_cluster empresas (grupos de comparables
    útiles no son ni de 1 empresa ni de 50).
    """
    available_cols = [c for c in FEATURE_COLUMNS if c in df.columns]
    X = df[available_cols].to_numpy(dtype=float).copy()

    # Rellenar NaN con la mediana de esa columna (para no romper el clustering
    # por un solo valor faltante)
    col_medians = np.nanmedian(X, axis=0)
    inds = np.where(np.isnan(X))
    X[inds] = np.take(col_medians, inds[1])

    X_scaled = _standardize(X)

    n = len(df)
    k = max(2, round(n / companies_per_cluster))
    labels = _kmeans(X_scaled, k=k)

    return pd.Series(labels, index=df.index, name="peer_cluster")


if __name__ == "__main__":
    from data_loader import load_companies
    from financial_metrics import compute_metrics

    df = load_companies("../data/companies.csv")
    metrics = compute_metrics(df)
    clusters = assign_peer_clusters(metrics)
    metrics["peer_cluster"] = clusters
    print(metrics[["company", "industry", "peer_cluster"]].sort_values("peer_cluster"))
