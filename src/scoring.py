"""
scoring.py
----------
Convierte las métricas financieras en un Deal Score 0-100, 100% determinístico
(sin IA), basado en un framework de 5 pilares ponderados:

    Financial Quality   25 pts
    Growth              20 pts
    Risk                20 pts
    Valuation           20 pts
    Strategic Fit       15 pts
    -----------------------------
    TOTAL              100 pts

La metodología es intencionalmente transparente: cada componente se puede
explicar con una fórmula concreta, no con un "el modelo lo decidió".
"""

from __future__ import annotations
import pandas as pd
import numpy as np


def _clip01(x):
    return np.clip(x, 0.0, 1.0)


def _scale(value, lo, hi):
    """Escala linealmente `value` al rango [0,1] entre lo y hi (clip a los extremos)."""
    if pd.isna(value):
        return 0.0
    if hi == lo:
        return 0.0
    return float(_clip01((value - lo) / (hi - lo)))


def score_financial_quality(row: pd.Series) -> float:
    """25 pts: EBITDA margin, FCF margin, ROIC proxy."""
    ebitda_score = _scale(row["ebitda_margin"], 0.00, 0.35)
    fcf_score = _scale(row["fcf_margin"], -0.05, 0.25)
    roic_score = _scale(row["roic_proxy"], 0.00, 0.25)
    composite = (ebitda_score * 0.4 + fcf_score * 0.3 + roic_score * 0.3)
    return round(composite * 25, 1)


def score_growth(row: pd.Series) -> float:
    """20 pts: revenue growth vs. banda de referencia 0%-40%."""
    growth_score = _scale(row["revenue_growth"], 0.00, 0.40)
    return round(growth_score * 20, 1)


def score_risk(row: pd.Series) -> float:
    """20 pts: apalancamiento, cobertura de intereses, concentración de clientes."""
    # Menos deuda / EBITDA es mejor -> invertir escala
    leverage_score = 1 - _scale(row["debt_ebitda"], 1.0, 6.0)
    coverage_score = _scale(row["interest_coverage"], 1.5, 8.0)
    concentration_score = 1 - _scale(row["largest_customer_pct"], 0.10, 0.50)
    composite = (leverage_score * 0.4 + coverage_score * 0.3 + concentration_score * 0.3)
    return round(_clip01(composite) * 20, 1)


def score_valuation(row: pd.Series) -> float:
    """20 pts: descuento/premium frente a la mediana de peers en EV/EBITDA."""
    disc = row.get("ev_ebitda_discount", np.nan)
    if pd.isna(disc):
        return 10.0  # neutral si no hay peers suficientes
    # -30% descuento -> score máximo; +30% premium -> score mínimo
    valuation_score = _scale(-disc, -0.30, 0.30)
    return round(valuation_score * 20, 1)


def score_strategic_fit(row: pd.Series) -> float:
    """15 pts: % de revenue recurrente como proxy de calidad/escalabilidad del negocio."""
    recurring_score = _scale(row["recurring_revenue_pct"], 0.10, 0.95)
    return round(recurring_score * 15, 1)


def compute_deal_scores(df_with_comparables: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica el framework de scoring a cada fila y agrega:
      financial_quality_score, growth_score, risk_score,
      valuation_score, strategic_fit_score, deal_score, priority_tier
    """
    d = df_with_comparables.copy()

    d["financial_quality_score"] = d.apply(score_financial_quality, axis=1)
    d["growth_score"] = d.apply(score_growth, axis=1)
    d["risk_score"] = d.apply(score_risk, axis=1)
    d["valuation_score"] = d.apply(score_valuation, axis=1)
    d["strategic_fit_score"] = d.apply(score_strategic_fit, axis=1)

    d["deal_score"] = (
        d["financial_quality_score"]
        + d["growth_score"]
        + d["risk_score"]
        + d["valuation_score"]
        + d["strategic_fit_score"]
    ).round(1)

    d["priority_tier"] = pd.cut(
        d["deal_score"],
        bins=[-0.1, 40, 65, 80, 100],
        labels=["Rejected", "Watchlist", "Priority", "High Priority"],
    )

    return d.sort_values("deal_score", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    from data_loader import load_companies
    from financial_metrics import compute_metrics
    from comparables import add_peer_comparables

    df = load_companies("data/companies.csv")
    metrics = compute_metrics(df)
    comp = add_peer_comparables(metrics)
    scored = compute_deal_scores(comp)
    print(scored[["company", "deal_score", "priority_tier"]])
