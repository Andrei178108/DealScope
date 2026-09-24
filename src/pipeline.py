"""
pipeline.py
-----------
Orquesta el flujo completo:

    CSV/Excel
       -> data_loader
       -> financial_metrics
       -> comparables
       -> scoring (Deal Score)
       -> risk_engine
       -> lbo_model
       -> ai_interface (Investment Memo)
       -> outputs/ (JSON para consumir desde un dashboard tipo R0Y)
"""

from __future__ import annotations
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd


def _sanitize(obj):
    """Reemplaza NaN/Infinity (inválidos en JSON estándar) por None recursivamente."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj

from data_loader import load_companies
from financial_metrics import compute_metrics
from comparables import add_peer_comparables
from scoring import compute_deal_scores
from risk_engine import add_risk_flags
from lbo_model import run_lbo, LBOAssumptions, run_monte_carlo
from sensitivity import sensitivity_matrix
from ai_interface import generate_investment_memo, AIInterfaceError

# A cuántas empresas top se les calcula la matriz de sensibilidad completa
# (correr esto para todas sería lento e innecesario para las de bajo score)
SENSITIVITY_TOP_N = 10
SENSITIVITY_EXIT_MULTIPLES = [7, 8, 9, 10, 11]
SENSITIVITY_GROWTH_RATES = [0.05, 0.10, 0.15, 0.20]

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "companies.csv"
HISTORICAL_PATH = ROOT / "data" / "historical.json"
BENCHMARK_PATH = ROOT / "data" / "benchmark.json"
SCORE_HISTORY_PATH = ROOT / "data" / "score_history.json"
OUTPUT_DIR = ROOT / "outputs"


def build_company_summary(row: pd.Series, lbo_result: dict, historical_data: dict, score_history: dict) -> dict:
    """Arma el JSON compacto que se le manda a la IA y que también sirve para el dashboard."""
    return {
        "company": row["company"],
        "industry": row["industry"],
        "deal_score": row["deal_score"],
        "priority_tier": str(row["priority_tier"]),
        "score_breakdown": {
            "financial_quality": row["financial_quality_score"],
            "growth": row["growth_score"],
            "risk": row["risk_score"],
            "valuation": row["valuation_score"],
            "strategic_fit": row["strategic_fit_score"],
        },
        "revenue_growth": round(row["revenue_growth"], 4),
        "ebitda_margin": round(row["ebitda_margin"], 4),
        "fcf_margin": round(row["fcf_margin"], 4),
        "debt_ebitda": round(row["debt_ebitda"], 2),
        "interest_coverage": round(row["interest_coverage"], 2),
        "ev_ebitda": round(row["ev_ebitda"], 2),
        "peer_median_ev_ebitda": round(row.get("peer_median_ev_ebitda", float("nan")), 2),
        "ev_ebitda_discount": round(row.get("ev_ebitda_discount", 0.0), 4),
        "peer_cluster": int(row["peer_cluster"]) if pd.notna(row.get("peer_cluster")) else None,
        "peer_cluster_size": int(row["peer_cluster_size"]) if pd.notna(row.get("peer_cluster_size")) else None,
        "largest_customer_pct": round(row["largest_customer_pct"], 3),
        "recurring_revenue_pct": round(row["recurring_revenue_pct"], 3),
        "risk_flags": [f["flag"] for f in row["risk_flags"]],
        "irr": lbo_result["irr"],
        "moic": lbo_result["moic"],
        "sponsor_equity": lbo_result["sponsor_equity"],
        "exit_equity": lbo_result["exit_equity"],
        "next_earnings_date": row.get("next_earnings_date", None),
        "ticker": row.get("ticker", None),
        "historical": historical_data.get(row.get("ticker"), None),
        "score_history": score_history.get(_score_history_key(row), []),
    }


def _score_history_key(row: pd.Series) -> str:
    """Usa el ticker si existe (empresas reales); si no, el nombre (empresas de ejemplo)."""
    ticker = row.get("ticker")
    if ticker and isinstance(ticker, str) and ticker.strip():
        return ticker
    return row["company"]


def update_score_history(df_with_scores: pd.DataFrame) -> dict:
    """
    Guarda el Deal Score de HOY para cada empresa en un archivo persistente,
    para poder armar una línea de tiempo de cómo cambia el score con cada
    actualización (cada vez que corre refresh_all.sh, normalmente cada 3 días).
    Si ya existe una entrada de HOY para una empresa, la reemplaza (para que
    correr el pipeline varias veces el mismo día no duplique puntos).
    """
    history: dict[str, list[dict]] = {}
    if SCORE_HISTORY_PATH.exists():
        with open(SCORE_HISTORY_PATH, encoding="utf-8") as f:
            history = json.load(f)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for _, row in df_with_scores.iterrows():
        key = _score_history_key(row)
        entries = history.get(key, [])
        entries = [e for e in entries if e["date"] != today]  # evita duplicar si corre 2x el mismo día
        entries.append({"date": today, "score": float(row["deal_score"])})
        entries = entries[-60:]  # conserva máximo ~60 puntos (varios meses a cadencia de 3 días)
        history[key] = entries

    with open(SCORE_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    return history


def _benchmark_cagr() -> float | None:
    """Calcula el retorno ANUALIZADO real del índice de referencia (CAGR),
    para poder comparar cada escenario de IRR simulado contra 'lo que el
    mercado realmente rindió por año' en el mismo período, no solo el
    retorno total acumulado."""
    if not BENCHMARK_PATH.exists():
        return None
    with open(BENCHMARK_PATH, encoding="utf-8") as f:
        bench = json.load(f)
    prices = bench.get("price_history", [])
    if len(prices) < 2:
        return None
    start_price, end_price = prices[0]["close"], prices[-1]["close"]
    n_years = len(prices) - 1
    if start_price <= 0 or n_years <= 0:
        return None
    return (end_price / start_price) ** (1 / n_years) - 1


def run_pipeline(data_path: Path = DATA_PATH, use_ai: bool = True, limit: int | None = None) -> list[dict]:
    print("[1/6] Cargando datos desde {} ...".format(data_path))
    df = load_companies(data_path)

    historical = {}
    if HISTORICAL_PATH.exists():
        with open(HISTORICAL_PATH, encoding="utf-8") as f:
            historical = json.load(f)

    print("[2/6] Calculando métricas financieras ...")
    metrics = compute_metrics(df)

    print("[3/6] Calculando comparables de industria ...")
    comp = add_peer_comparables(metrics)

    print("[4/6] Calculando Deal Score ...")
    scored = compute_deal_scores(comp)

    print("[5/6] Detectando banderas de riesgo y corriendo LBO ...")
    risked = add_risk_flags(scored)

    if limit:
        risked = risked.head(limit)

    print("      Actualizando historial de scores ...")
    score_history = update_score_history(risked)

    benchmark_cagr = _benchmark_cagr()
    if benchmark_cagr is not None:
        print(f"      Benchmark (S&P SmallCap 600) CAGR real: {benchmark_cagr*100:.1f}% anual")

    results = []
    for i, (_, row) in enumerate(risked.iterrows(), start=1):
        lbo_result = run_lbo(row, LBOAssumptions())
        summary = build_company_summary(row, lbo_result, historical, score_history)

        # Sensitivity matrix: solo top N (es una tabla fija, no aporta mostrarla
        # para 55 empresas). Monte Carlo: en TODAS las que tengan EBITDA positivo,
        # ya que computacionalmente es barato y da más valor tenerlo siempre disponible.
        if i <= SENSITIVITY_TOP_N and row["ebitda"] > 0:
            irr_matrix = sensitivity_matrix(
                row, SENSITIVITY_EXIT_MULTIPLES, SENSITIVITY_GROWTH_RATES, metric="irr"
            )
            moic_matrix = sensitivity_matrix(
                row, SENSITIVITY_EXIT_MULTIPLES, SENSITIVITY_GROWTH_RATES, metric="moic"
            )
            summary["sensitivity"] = {
                "exit_multiples": SENSITIVITY_EXIT_MULTIPLES,
                "growth_rates": SENSITIVITY_GROWTH_RATES,
                "irr_matrix": irr_matrix.values.tolist(),
                "moic_matrix": moic_matrix.values.tolist(),
            }
        else:
            summary["sensitivity"] = None

        summary["monte_carlo"] = run_monte_carlo(row, n_sims=10000, benchmark_cagr=benchmark_cagr) if row["ebitda"] > 0 else None

        if use_ai:
            try:
                memo = generate_investment_memo(summary)
            except AIInterfaceError as e:
                memo = {"error": str(e)}
        else:
            memo = None

        summary["ai_memo"] = memo
        results.append(summary)
        print(f"      -> ({i}/{len(risked)}) {summary['company']}: score={summary['deal_score']}")

    print("[6/6] Guardando resultados ...")
    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / "deal_screening_results.json"

    generated_at = datetime.now(timezone.utc)
    next_refresh_due = generated_at + timedelta(days=3)

    payload = {
        "generated_at": generated_at.isoformat(),
        "next_refresh_due": next_refresh_due.isoformat(),
        "companies": results,
    }
    clean_payload = _sanitize(json.loads(json.dumps(payload, default=str)))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(clean_payload, f, indent=2, ensure_ascii=False)

    print(f"Listo. {len(results)} empresas procesadas -> {out_path}")
    return results


if __name__ == "__main__":
    use_ai = "--no-ai" not in sys.argv
    run_pipeline(use_ai=use_ai)
