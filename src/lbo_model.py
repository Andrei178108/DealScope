"""
lbo_model.py
------------
Simula una compra apalancada (LBO) a 5 años sobre cada empresa:
  - Entry: EV, deuda, equity del sponsor
  - Proyección de revenue/EBITDA
  - Amortización simple de deuda con flujo de caja libre
  - Exit a un múltiplo de EBITDA
  - IRR y MOIC del sponsor
"""

from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from scipy.optimize import brentq


@dataclass
class LBOAssumptions:
    entry_multiple: float | None = None   # si None, se usa el EV/EBITDA actual de la empresa
    exit_multiple: float | None = None    # si None, se asume igual al entry multiple
    debt_pct_of_ev: float = 0.55          # % del EV financiado con deuda
    revenue_growth_rate: float | None = None  # si None, se usa el growth histórico de la empresa
    ebitda_margin: float | None = None    # si None, se mantiene el margen actual
    hold_period_years: int = 5
    debt_interest_rate: float = 0.09
    cash_sweep_pct: float = 0.75          # % del FCF anual usado para pagar deuda


def _irr(cashflows: list[float]) -> float | None:
    """IRR vía búsqueda de raíz de NPV(r)=0. cashflows[0] es negativo (inversión inicial)."""
    def npv(rate):
        return sum(cf / (1 + rate) ** i for i, cf in enumerate(cashflows))

    try:
        return brentq(npv, -0.99, 10.0)
    except ValueError:
        return None  # no hay cambio de signo -> IRR no definido con estos flujos


def run_lbo(row: pd.Series, assumptions: LBOAssumptions | None = None) -> dict:
    a = assumptions or LBOAssumptions()

    entry_ebitda = row["ebitda"]

    if entry_ebitda <= 0:
        # LBO no es un modelo apropiado para empresas con EBITDA negativo:
        # no hay flujo de caja para pagar deuda. Se marca explícitamente en vez
        # de producir un IRR/MOIC engañoso.
        return {
            "company": row["company"], "entry_multiple": None, "exit_multiple": None,
            "entry_ev": None, "entry_debt": None, "sponsor_equity": None,
            "exit_ev": None, "exit_debt": None, "exit_equity": None,
            "irr": None, "moic": None, "yearly_projection": [],
            "note": "LBO not applicable: entry EBITDA is negative or zero.",
        }

    entry_multiple = a.entry_multiple or row["ev_ebitda"]
    exit_multiple = a.exit_multiple or entry_multiple
    # Default conservador: se asume deceleración vs. el crecimiento histórico,
    # con un techo de 15% anual sostenido durante el hold period (supuesto típico
    # de underwriting de PE, que rara vez proyecta crecimiento histórico "as-is").
    growth_rate = (
        a.revenue_growth_rate
        if a.revenue_growth_rate is not None
        else min(max(row["revenue_growth"], 0.0), 0.15)
    )
    ebitda_margin = a.ebitda_margin if a.ebitda_margin is not None else row["ebitda_margin"]
    entry_ev = entry_multiple * entry_ebitda
    entry_debt = a.debt_pct_of_ev * entry_ev
    sponsor_equity = entry_ev - entry_debt

    revenue = row["revenue"]
    debt_balance = entry_debt
    yearly = []

    for year in range(1, a.hold_period_years + 1):
        revenue = revenue * (1 + growth_rate)
        ebitda = revenue * ebitda_margin
        interest = debt_balance * a.debt_interest_rate
        # FCF simplificado: EBITDA - intereses - impuesto estimado (25% sobre EBT) - capex proxy 3% revenue
        ebt = max(ebitda - interest, 0)
        taxes = 0.25 * ebt
        capex = 0.03 * revenue
        fcf = ebitda - interest - taxes - capex

        paydown = min(max(fcf, 0) * a.cash_sweep_pct, debt_balance)
        debt_balance = max(debt_balance - paydown, 0)

        yearly.append({
            "year": year, "revenue": revenue, "ebitda": ebitda,
            "interest": interest, "fcf": fcf, "debt_paydown": paydown,
            "ending_debt": debt_balance,
        })

    exit_ebitda = yearly[-1]["ebitda"]
    exit_ev = exit_multiple * exit_ebitda
    exit_debt = yearly[-1]["ending_debt"]
    exit_equity = max(exit_ev - exit_debt, 0)

    cashflows = [-sponsor_equity] + [0.0] * (a.hold_period_years - 1) + [exit_equity]
    irr = _irr(cashflows)
    moic = exit_equity / sponsor_equity if sponsor_equity > 0 else None

    return {
        "company": row["company"],
        "entry_multiple": round(entry_multiple, 2),
        "exit_multiple": round(exit_multiple, 2),
        "entry_ev": round(entry_ev, 0),
        "entry_debt": round(entry_debt, 0),
        "sponsor_equity": round(sponsor_equity, 0),
        "exit_ev": round(exit_ev, 0),
        "exit_debt": round(exit_debt, 0),
        "exit_equity": round(exit_equity, 0),
        "irr": round(irr, 4) if irr is not None else None,
        "moic": round(moic, 2) if moic is not None else None,
        "yearly_projection": yearly,
    }


def run_monte_carlo(row: pd.Series, n_sims: int = 10000, seed: int = 42, benchmark_cagr: float | None = None) -> dict | None:
    """
    Corre n_sims simulaciones del LBO variando aleatoriamente el growth rate
    y el exit multiple (las dos asunciones más inciertas del modelo), para
    dar un RANGO de resultados probables en vez de un solo número.

    - Growth rate: distribución triangular alrededor del growth histórico
      (min: 0%, moda: growth histórico capado a 15%, max: growth histórico + 10pp)
    - Exit multiple: distribución normal alrededor del entry multiple actual,
      con desviación estándar de ~15% (refleja incertidumbre de mercado a 5 años)

    Devuelve percentiles (p10/p50/p90) de IRR y MOIC, y la probabilidad de
    que el IRR supere ciertos umbrales — la forma estándar en que un fondo
    presenta riesgo, en vez de un único número optimista.
    """
    if row["ebitda"] <= 0:
        return None

    rng = np.random.default_rng(seed)
    entry_multiple = row["ev_ebitda"]
    base_growth = min(max(row["revenue_growth"], 0.0), 0.15)

    irr_results, moic_results = [], []
    for _ in range(n_sims):
        growth_sample = rng.triangular(left=0.0, mode=base_growth, right=min(base_growth + 0.10, 0.35))
        multiple_sample = max(rng.normal(loc=entry_multiple, scale=entry_multiple * 0.15), 3.0)

        assumptions = LBOAssumptions(
            entry_multiple=entry_multiple,
            exit_multiple=multiple_sample,
            revenue_growth_rate=growth_sample,
        )
        result = run_lbo(row, assumptions)
        if result["irr"] is not None:
            irr_results.append(result["irr"])
        if result["moic"] is not None:
            moic_results.append(result["moic"])

    if len(irr_results) < n_sims * 0.5:
        return None  # demasiadas simulaciones fallidas, no es confiable

    irr_arr = np.array(irr_results)
    moic_arr = np.array(moic_results)

    return {
        "n_sims": len(irr_results),
        "irr_p10": round(float(np.percentile(irr_arr, 10)), 4),
        "irr_p50": round(float(np.percentile(irr_arr, 50)), 4),
        "irr_p90": round(float(np.percentile(irr_arr, 90)), 4),
        "moic_p10": round(float(np.percentile(moic_arr, 10)), 2),
        "moic_p50": round(float(np.percentile(moic_arr, 50)), 2),
        "moic_p90": round(float(np.percentile(moic_arr, 90)), 2),
        "prob_irr_above_15pct": round(float(np.mean(irr_arr > 0.15)), 3),
        "prob_irr_above_20pct": round(float(np.mean(irr_arr > 0.20)), 3),
        "prob_loss": round(float(np.mean(irr_arr < 0)), 3),
        "benchmark_cagr": round(benchmark_cagr, 4) if benchmark_cagr is not None else None,
        "prob_beat_benchmark": round(float(np.mean(irr_arr > benchmark_cagr)), 3) if benchmark_cagr is not None else None,
        "histogram": _build_histogram(irr_arr),
    }


def _build_histogram(irr_arr, n_bins: int = 12) -> dict:
    """Histograma simple del IRR simulado, para graficar la distribución."""
    counts, edges = np.histogram(irr_arr, bins=n_bins)
    return {
        "bin_edges": [round(float(e), 4) for e in edges],
        "counts": [int(c) for c in counts],
    }


def run_lbo_for_all(df: pd.DataFrame, assumptions: LBOAssumptions | None = None) -> pd.DataFrame:
    results = [run_lbo(row, assumptions) for _, row in df.iterrows()]
    flat = [{k: v for k, v in r.items() if k != "yearly_projection"} for r in results]
    return pd.DataFrame(flat)


if __name__ == "__main__":
    from data_loader import load_companies
    from financial_metrics import compute_metrics

    df = load_companies("data/companies.csv")
    metrics = compute_metrics(df)
    lbo = run_lbo_for_all(metrics)
    print(lbo[["company", "sponsor_equity", "exit_equity", "irr", "moic"]])
