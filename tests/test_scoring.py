import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from scoring import compute_deal_scores


def _row(**overrides):
    base = dict(
        company="TestCo", industry="B2B SaaS",
        revenue_growth=0.30, ebitda_margin=0.20, fcf_margin=0.10, roic_proxy=0.15,
        debt_ebitda=2.0, interest_coverage=5.0, largest_customer_pct=0.10,
        recurring_revenue_pct=0.80, ev_ebitda_discount=-0.10,
    )
    base.update(overrides)
    return pd.DataFrame([base])


def test_deal_score_in_bounds():
    scored = compute_deal_scores(_row())
    score = scored.loc[0, "deal_score"]
    assert 0 <= score <= 100


def test_high_risk_lowers_score():
    good = compute_deal_scores(_row())["deal_score"].iloc[0]
    bad = compute_deal_scores(
        _row(debt_ebitda=8.0, interest_coverage=1.0, largest_customer_pct=0.6)
    )["deal_score"].iloc[0]
    assert bad < good


def test_priority_tier_assignment():
    scored = compute_deal_scores(_row(
        revenue_growth=0.40, ebitda_margin=0.30, fcf_margin=0.20, roic_proxy=0.22,
        debt_ebitda=1.0, interest_coverage=8.0, largest_customer_pct=0.05,
        recurring_revenue_pct=0.9, ev_ebitda_discount=-0.25,
    ))
    assert scored.loc[0, "priority_tier"] == "High Priority"


if __name__ == "__main__":
    test_deal_score_in_bounds()
    test_high_risk_lowers_score()
    test_priority_tier_assignment()
    print("Todos los tests de scoring pasaron.")
