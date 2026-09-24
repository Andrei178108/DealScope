"""
sensitivity.py
--------------
Genera matrices de sensibilidad de IRR y MOIC variando el exit multiple
y la tasa de crecimiento de revenue asumida, para una empresa puntual.
"""

from __future__ import annotations
import pandas as pd
from lbo_model import LBOAssumptions, run_lbo


def sensitivity_matrix(
    row: pd.Series,
    exit_multiples: list[float],
    growth_rates: list[float],
    metric: str = "irr",
) -> pd.DataFrame:
    """
    Devuelve un DataFrame donde el índice son exit_multiples y las columnas
    son growth_rates, con el valor de `metric` ('irr' o 'moic') en cada celda.
    """
    base_multiple = row["ev_ebitda"]
    data = {}
    for g in growth_rates:
        col = []
        for ex in exit_multiples:
            assumptions = LBOAssumptions(
                entry_multiple=base_multiple,
                exit_multiple=ex,
                revenue_growth_rate=g,
            )
            result = run_lbo(row, assumptions)
            col.append(result[metric])
        data[f"{g:.0%} growth"] = col

    return pd.DataFrame(data, index=[f"{ex:.1f}x exit" for ex in exit_multiples])


if __name__ == "__main__":
    from data_loader import load_companies
    from financial_metrics import compute_metrics

    df = load_companies("data/companies.csv")
    metrics = compute_metrics(df)
    target = metrics[metrics["company"] == "Alpha Software"].iloc[0]

    matrix = sensitivity_matrix(
        target,
        exit_multiples=[7, 8, 9, 10],
        growth_rates=[0.20, 0.25, 0.30],
        metric="irr",
    )
    print((matrix * 100).round(1))
