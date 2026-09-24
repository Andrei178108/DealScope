"""
comparables.py
---------------
Compara a cada empresa contra sus "peers" usando múltiplos de valuación, y
calcula el descuento/premium frente a la mediana del grupo.

El grupo de comparables se calcula con clustering (k-means sobre métricas
financieras reales — ver clustering.py) en vez de solo agrupar por la
industria asignada manualmente. Esto da peer groups más precisos: dos
empresas de industrias distintas pero con perfil financiero parecido
(mismo growth, mismo apalancamiento) sí se comparan entre sí.
"""

from __future__ import annotations
import pandas as pd
from clustering import assign_peer_clusters


def add_peer_comparables(metrics: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega, por peer group (cluster de similitud financiera):
      - peer_cluster
      - peer_median_ev_ebitda
      - peer_median_ev_revenue
      - ev_ebitda_discount  (negativo = trading a descuento vs peers)
    """
    m = metrics.copy()
    m["peer_cluster"] = assign_peer_clusters(m)

    peer_medians = (
        m.groupby("peer_cluster")[["ev_ebitda", "ev_revenue"]]
        .median()
        .rename(columns={"ev_ebitda": "peer_median_ev_ebitda",
                          "ev_revenue": "peer_median_ev_revenue"})
    )
    peer_counts = m.groupby("peer_cluster").size().rename("peer_cluster_size")

    m = m.merge(peer_medians, on="peer_cluster", how="left")
    m = m.merge(peer_counts, on="peer_cluster", how="left")

    m["ev_ebitda_discount"] = (
        m["ev_ebitda"] / m["peer_median_ev_ebitda"] - 1
    )
    m["ev_revenue_discount"] = (
        m["ev_revenue"] / m["peer_median_ev_revenue"] - 1
    )

    return m


def comparable_commentary(row: pd.Series) -> str:
    """Genera una frase corta y determinística (sin IA) sobre la valuación relativa."""
    disc = row["ev_ebitda_discount"]
    if pd.isna(disc):
        return "Peer set insuficiente para comparar."
    pct = abs(disc) * 100
    if disc < -0.03:
        return f"Trades at approximately a {pct:.0f}% discount to the peer median EV/EBITDA."
    elif disc > 0.03:
        return f"Trades at approximately a {pct:.0f}% premium to the peer median EV/EBITDA."
    return "Trades roughly in line with the peer median EV/EBITDA."


if __name__ == "__main__":
    from data_loader import load_companies
    from financial_metrics import compute_metrics

    df = load_companies("data/companies.csv")
    metrics = compute_metrics(df)
    comp = add_peer_comparables(metrics)
    for _, row in comp.iterrows():
        print(row["company"], f"(cluster {row['peer_cluster']}, {row['peer_cluster_size']} peers) ->", comparable_commentary(row))
