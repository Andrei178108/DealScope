"""
backtest.py
------------
Prueba si el Deal Score realmente predice buen desempeño, usando datos
históricos reales:

  1. Para cada empresa, toma el año MÁS ANTIGUO disponible en su historial
     (normalmente ~3-4 años atrás — es el límite real de la fuente gratuita).
  2. Recalcula un score SIMPLIFICADO usando SOLO los datos que existían en
     ese momento (no los de hoy) — Growth, Financial Quality (EBITDA margin)
     y Risk (Debt/EBITDA). Valuation y Strategic Fit NO se pueden recrear
     retroactivamente con esta fuente de datos (no hay múltiplos de peers
     históricos ni % de revenue recurrente histórico), así que este score
     es intencionalmente más simple que el Deal Score completo del dashboard.
  3. Calcula el retorno REAL de precio de esa empresa desde ese año hasta hoy.
  4. Compara: ¿las empresas con score histórico alto tuvieron, en promedio,
     mejor retorno real que las de score bajo?

IMPORTANTE — limitaciones de este backtest (léelas antes de citar resultados):
  - Muestra pequeña (depende de cuántas empresas tengan suficiente historial).
  - Solo compara PRECIO DE ACCIÓN, no el retorno real que habría tenido un
    LBO (que depende de múltiplos de entrada/salida no disponibles históricamente).
  - Un solo punto de backtest (un año de referencia por empresa) no es
    estadísticamente tan robusto como probar en muchos períodos distintos.
  - Este es un ejercicio educativo de validación, no un backtest de grado
    institucional.
"""

from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
HISTORICAL_PATH = ROOT / "data" / "historical.json"
BENCHMARK_PATH = ROOT / "data" / "benchmark.json"
OUTPUT_PATH = ROOT / "outputs" / "backtest_results.json"


def _scale(value, lo, hi):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return float(np.clip((value - lo) / (hi - lo), 0.0, 1.0))


def simplified_historical_score(revenue_t0, revenue_t1, ebitda_t0, debt_t0) -> float | None:
    """Score simplificado (0-100) reconstruido con datos disponibles en el año t0.
    t0 = año más antiguo disponible, t1 = el año siguiente (para calcular growth)."""
    if revenue_t0 is None or revenue_t0 <= 0:
        return None

    # Growth (35 pts del score simplificado)
    growth_score = 0.0
    if revenue_t1 is not None and revenue_t1 > 0:
        growth_rate = (revenue_t1 - revenue_t0) / revenue_t0
        g = _scale(growth_rate, 0.0, 0.40)
        growth_score = (g or 0) * 35

    # Financial Quality vía EBITDA margin (35 pts)
    quality_score = 0.0
    if ebitda_t0 is not None:
        margin = ebitda_t0 / revenue_t0
        q = _scale(margin, 0.0, 0.30)
        quality_score = (q or 0) * 35

    # Risk vía Debt/EBITDA (30 pts) — solo si hay deuda y EBITDA positivo
    risk_score = 15.0  # neutral si no hay dato
    if debt_t0 is not None and ebitda_t0 is not None and ebitda_t0 > 0:
        leverage = debt_t0 / ebitda_t0
        r = _scale(leverage, 1.0, 6.0)
        risk_score = (1 - (r or 0)) * 30

    return round(growth_score + quality_score + risk_score, 1)


def _benchmark_return() -> float | None:
    """Retorno del índice de referencia en el mismo período aproximado del backtest."""
    if not BENCHMARK_PATH.exists():
        return None
    with open(BENCHMARK_PATH, encoding="utf-8") as f:
        bench = json.load(f)
    prices = bench.get("price_history", [])
    if len(prices) < 2:
        return None
    start, end = prices[0]["close"], prices[-1]["close"]
    if start <= 0:
        return None
    return (end - start) / start


def run_backtest() -> dict:
    if not HISTORICAL_PATH.exists():
        raise SystemExit(
            f"No existe {HISTORICAL_PATH}. Corre primero: python3 live_data_fetch.py"
        )

    with open(HISTORICAL_PATH, encoding="utf-8") as f:
        historical = json.load(f)

    results = []
    for ticker, h in historical.items():
        years = h.get("years", [])
        revenue = h.get("revenue", [])
        ebitda = h.get("ebitda", [])
        debt = h.get("debt", [])
        price_history = h.get("price_history", [])

        if len(years) < 2 or len(price_history) < 2:
            continue  # no hay suficiente historial para hacer backtest de esta empresa

        # t0 = año más antiguo disponible de fundamentales
        score = simplified_historical_score(
            revenue_t0=revenue[0], revenue_t1=revenue[1] if len(revenue) > 1 else None,
            ebitda_t0=ebitda[0], debt_t0=debt[0] if debt else None,
        )
        if score is None:
            continue

        # Retorno real de precio desde el año más viejo del historial hasta el más nuevo
        price_start = price_history[0]["close"]
        price_end = price_history[-1]["close"]
        if price_start <= 0:
            continue
        forward_return = (price_end - price_start) / price_start

        results.append({
            "ticker": ticker,
            "backtest_year": years[0],
            "current_year": price_history[-1]["year"],
            "historical_score": score,
            "forward_return": round(forward_return, 4),
        })

    if len(results) < 5:
        return {
            "n": len(results),
            "warning": "Muestra insuficiente para conclusiones estadísticas (se recomiendan al menos 10-15 empresas).",
            "results": results,
        }

    scores = [r["historical_score"] for r in results]
    returns = [r["forward_return"] for r in results]
    correlation, p_value = stats.spearmanr(scores, returns)

    ranked = sorted(results, key=lambda r: r["historical_score"], reverse=True)
    n_top = max(1, len(ranked) // 3)
    top_third = ranked[:n_top]
    bottom_third = ranked[-n_top:]

    avg_top_return = sum(r["forward_return"] for r in top_third) / len(top_third)
    avg_bottom_return = sum(r["forward_return"] for r in bottom_third) / len(bottom_third)
    benchmark_return = _benchmark_return()

    summary = {
        "n": len(results),
        "spearman_correlation": round(float(correlation), 3),
        "p_value": round(float(p_value), 4),
        "interpretation": _interpret(correlation, p_value),
        "avg_return_top_third": round(avg_top_return, 4),
        "avg_return_bottom_third": round(avg_bottom_return, 4),
        "benchmark_ticker": "^SP600 (S&P SmallCap 600)",
        "benchmark_return": round(benchmark_return, 4) if benchmark_return is not None else None,
        "beat_benchmark": (avg_top_return > benchmark_return) if benchmark_return is not None else None,
        "results": sorted(results, key=lambda r: r["historical_score"], reverse=True),
    }
    return summary


def _interpret(corr, p_value) -> str:
    if p_value > 0.10:
        return "Sin relación estadísticamente significativa en esta muestra (muestra pequeña / período único)."
    if corr > 0.3:
        return "Correlación positiva: las empresas con score histórico alto tendieron a tener mejor retorno real."
    if corr < -0.3:
        return "Correlación negativa: en esta muestra, score alto no se asoció con mejor retorno — señal a investigar."
    return "Correlación débil: relación poco concluyente con esta muestra."


if __name__ == "__main__":
    summary = run_backtest()
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"Backtest corrido sobre {summary['n']} empresas.")
    if "spearman_correlation" in summary:
        print(f"Correlación (score histórico vs. retorno real): {summary['spearman_correlation']}")
        print(f"p-value: {summary['p_value']}")
        print(f"Interpretación: {summary['interpretation']}")
        print(f"Retorno promedio del tercio TOP (por score): {summary['avg_return_top_third']*100:.1f}%")
        print(f"Retorno promedio del tercio BOTTOM (por score): {summary['avg_return_bottom_third']*100:.1f}%")
        if summary.get("benchmark_return") is not None:
            print(f"Retorno del benchmark ({summary['benchmark_ticker']}): {summary['benchmark_return']*100:.1f}%")
            print(f"¿El tercio top le ganó al mercado?: {'Sí' if summary['beat_benchmark'] else 'No'}")
    else:
        print(summary.get("warning"))
    print(f"\nResultados guardados en {OUTPUT_PATH}")
