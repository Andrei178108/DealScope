"""
financial_metrics.py
---------------------
Calcula métricas financieras estándar a partir de los datos crudos:
márgenes, crecimiento, apalancamiento, cobertura y múltiplos de valuación.
"""

from __future__ import annotations
import pandas as pd


def compute_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Recibe el DataFrame crudo (ver data_loader) y devuelve un nuevo
    DataFrame con columnas de métricas financieras calculadas.
    """
    m = df.copy()

    # --- Crecimiento ---
    m["revenue_growth"] = (m["revenue"] - m["revenue_prior_year"]) / m["revenue_prior_year"]

    # --- Márgenes ---
    m["ebitda_margin"] = m["ebitda"] / m["revenue"]
    m["fcf_margin"] = m["fcf"] / m["revenue"]

    # --- Apalancamiento y cobertura ---
    m["net_debt"] = m["total_debt"] - m["cash"]
    m["debt_ebitda"] = m["total_debt"] / m["ebitda"].replace(0, pd.NA)
    m["net_debt_ebitda"] = m["net_debt"] / m["ebitda"].replace(0, pd.NA)
    m["interest_coverage"] = m["ebitda"] / m["interest_expense"].replace(0, pd.NA)

    # --- Valuación ---
    m["ev_revenue"] = m["enterprise_value"] / m["revenue"]
    m["ev_ebitda"] = m["enterprise_value"] / m["ebitda"].replace(0, pd.NA)

    # --- Eficiencia de capital (proxy simple de ROIC) ---
    invested_capital = m["total_debt"] + (m["enterprise_value"] - m["total_debt"] + m["cash"])
    m["roic_proxy"] = m["ebitda"] / invested_capital.replace(0, pd.NA)

    return m


if __name__ == "__main__":
    from data_loader import load_companies

    df = load_companies("data/companies.csv")
    metrics = compute_metrics(df)
    cols = [
        "company", "revenue_growth", "ebitda_margin", "fcf_margin",
        "debt_ebitda", "interest_coverage", "ev_revenue", "ev_ebitda",
    ]
    print(metrics[cols].round(3))
