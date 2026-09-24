import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lbo_model import run_lbo, LBOAssumptions


def _row(**overrides):
    base = dict(
        company="TestCo", revenue=100_000_000, ebitda=20_000_000,
        ev_ebitda=10.0, revenue_growth=0.15, ebitda_margin=0.20,
    )
    base.update(overrides)
    return pd.Series(base)


def test_moic_positive_for_healthy_company():
    result = run_lbo(_row())
    assert result["moic"] is not None
    assert result["moic"] > 1.0


def test_irr_reasonable_range():
    result = run_lbo(_row())
    assert result["irr"] is not None
    assert -0.5 < result["irr"] < 2.0


def test_negative_ebitda_not_applicable():
    result = run_lbo(_row(ebitda=-1_000_000, ev_ebitda=-10.0))
    assert result["irr"] is None
    assert result["moic"] is None
    assert "note" in result


def test_higher_exit_multiple_increases_moic():
    base = run_lbo(_row(), LBOAssumptions(entry_multiple=10, exit_multiple=10))
    higher_exit = run_lbo(_row(), LBOAssumptions(entry_multiple=10, exit_multiple=14))
    assert higher_exit["moic"] > base["moic"]


if __name__ == "__main__":
    test_moic_positive_for_healthy_company()
    test_irr_reasonable_range()
    test_negative_ebitda_not_applicable()
    test_higher_exit_multiple_increases_moic()
    print("Todos los tests de LBO pasaron.")
