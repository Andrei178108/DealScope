"""
risk_engine.py
--------------
Detecta banderas de riesgo cuantitativas de forma determinística
(reglas explícitas, no IA). La IA (ai_interface.py) luego puede
añadir contexto narrativo, pero las banderas en sí se generan aquí.
"""

from __future__ import annotations
import pandas as pd

# (nombre, condición_lambda, severidad, descripción)
RULES = [
    (
        "High Customer Concentration",
        lambda r: r["largest_customer_pct"] > 0.25,
        "High",
        "Largest customer represents more than 25% of revenue.",
    ),
    (
        "High Leverage",
        lambda r: r["debt_ebitda"] > 4.0,
        "High",
        "Debt/EBITDA exceeds 4.0x.",
    ),
    (
        "Weak Interest Coverage",
        lambda r: r["interest_coverage"] < 2.5,
        "High",
        "EBITDA covers interest expense less than 2.5x.",
    ),
    (
        "Negative Free Cash Flow",
        lambda r: r["fcf"] < 0,
        "Medium",
        "Company is currently FCF-negative.",
    ),
    (
        "Low Revenue Quality",
        lambda r: r["recurring_revenue_pct"] < 0.30,
        "Medium",
        "Less than 30% of revenue is recurring.",
    ),
    (
        "Decelerating / Weak Growth",
        lambda r: r["revenue_growth"] < 0.05,
        "Medium",
        "Revenue growth is below 5% year-over-year.",
    ),
    (
        "Valuation Premium to Peers",
        lambda r: r.get("ev_ebitda_discount", 0) > 0.15,
        "Low",
        "Trades at more than a 15% premium to peer median EV/EBITDA.",
    ),
]


def flag_risks(row: pd.Series) -> list[dict]:
    flags = []
    for name, condition, severity, description in RULES:
        try:
            if condition(row):
                flags.append({"flag": name, "severity": severity, "description": description})
        except (KeyError, TypeError, ZeroDivisionError):
            continue
    return flags


def add_risk_flags(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["risk_flags"] = d.apply(flag_risks, axis=1)
    d["risk_flag_count"] = d["risk_flags"].apply(len)
    return d


if __name__ == "__main__":
    from data_loader import load_companies
    from financial_metrics import compute_metrics
    from comparables import add_peer_comparables

    df = load_companies("data/companies.csv")
    metrics = compute_metrics(df)
    comp = add_peer_comparables(metrics)
    risked = add_risk_flags(comp)
    for _, row in risked.iterrows():
        print(row["company"], "->", [f["flag"] for f in row["risk_flags"]])
