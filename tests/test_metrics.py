import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from financial_metrics import compute_metrics


def _sample_df():
    return pd.DataFrame([{
        "company": "TestCo", "industry": "B2B SaaS",
        "revenue": 100, "revenue_prior_year": 80, "ebitda": 20, "fcf": 10,
        "total_debt": 40, "cash": 10, "enterprise_value": 200,
        "employees": 50, "recurring_revenue_pct": 0.8,
        "largest_customer_pct": 0.1, "interest_expense": 4,
    }])


def test_revenue_growth():
    m = compute_metrics(_sample_df())
    assert abs(m.loc[0, "revenue_growth"] - 0.25) < 1e-9


def test_ebitda_margin():
    m = compute_metrics(_sample_df())
    assert abs(m.loc[0, "ebitda_margin"] - 0.20) < 1e-9


def test_debt_ebitda():
    m = compute_metrics(_sample_df())
    assert abs(m.loc[0, "debt_ebitda"] - 2.0) < 1e-9


def test_interest_coverage():
    m = compute_metrics(_sample_df())
    assert abs(m.loc[0, "interest_coverage"] - 5.0) < 1e-9


def test_ev_ebitda():
    m = compute_metrics(_sample_df())
    assert abs(m.loc[0, "ev_ebitda"] - 10.0) < 1e-9


if __name__ == "__main__":
    test_revenue_growth()
    test_ebitda_margin()
    test_debt_ebitda()
    test_interest_coverage()
    test_ev_ebitda()
    print("Todos los tests de financial_metrics pasaron.")
