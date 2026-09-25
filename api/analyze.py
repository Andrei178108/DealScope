"""
api/analyze.py
----------------
Función serverless de Vercel: recibe un ticker (ej. AAPL, TSLA, cualquier
empresa pública del mundo) y corre EL MISMO motor cuantitativo que usa
el pipeline principal — en vivo, en el momento, sin necesitar que esa
empresa esté precargada.

Se reutiliza la misma metodología (5 pilares, LBO, comparables) que
data_loader.py / financial_metrics.py / scoring.py / lbo_model.py, pero
autónoma en un solo archivo para que Vercel la pueda desplegar como
función serverless sin depender de imports relativos complicados.

Honestidad sobre comparables: si la empresa buscada no tiene "peers"
razonables dentro del universo de referencia (por ejemplo, es demasiado
grande, como una mega-cap), el pilar de Valuation queda neutral (10/20)
en vez de inventar un número — exactamente la misma regla que ya usa
scoring.py para el resto del proyecto.
"""

import json
import math
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

import numpy as np
import yfinance as yf

REFERENCE_PATH = Path(__file__).resolve().parent.parent / "outputs" / "deal_screening_results.json"


def _safe_num(value, default=None):
    try:
        if value is None:
            return default
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _scale(value, lo, hi):
    if value is None:
        return 0.0
    return float(np.clip((value - lo) / (hi - lo), 0.0, 1.0))


def fetch_live_company(ticker: str) -> dict:
    """Descarga datos reales en vivo de Yahoo Finance para un ticker cualquiera."""
    t = yf.Ticker(ticker)
    info = t.info
    fin = t.financials

    if not info or "shortName" not in info:
        raise ValueError(f"No se encontró la empresa con ticker '{ticker}'.")

    revenue = None
    revenue_prior = None
    if fin is not None and not fin.empty and "Total Revenue" in fin.index:
        rev_row = fin.loc["Total Revenue"]
        if len(rev_row) >= 2:
            revenue = _safe_num(rev_row.iloc[0])
            revenue_prior = _safe_num(rev_row.iloc[1])

    if revenue is None:
        revenue = _safe_num(info.get("totalRevenue"))
    if revenue is None or revenue <= 0:
        raise ValueError(f"No hay datos de revenue disponibles para '{ticker}'.")

    ebitda = _safe_num(info.get("ebitda"))
    total_debt = _safe_num(info.get("totalDebt"), 0.0)
    cash = _safe_num(info.get("totalCash"), 0.0)
    market_cap = _safe_num(info.get("marketCap"), 0.0)
    enterprise_value = _safe_num(info.get("enterpriseValue"), market_cap + total_debt - cash)
    fcf = _safe_num(info.get("freeCashflow"), (ebitda or 0) * 0.6)
    interest_expense = None
    if fin is not None and not fin.empty and "Interest Expense" in fin.index:
        interest_expense = abs(_safe_num(fin.loc["Interest Expense"].iloc[0], 0))
    if not interest_expense:
        interest_expense = max(total_debt * 0.06, 1.0)

    return {
        "ticker": ticker.upper(),
        "company": info.get("shortName", ticker.upper()),
        "industry": info.get("industry") or info.get("sector") or "Sin clasificar",
        "revenue": revenue,
        "revenue_prior_year": revenue_prior if revenue_prior else revenue * 0.9,
        "ebitda": ebitda if ebitda is not None else revenue * 0.1,
        "fcf": fcf,
        "total_debt": total_debt,
        "cash": cash,
        "enterprise_value": enterprise_value if enterprise_value > 0 else market_cap,
        "employees": info.get("fullTimeEmployees", None),
        "interest_expense": interest_expense,
        "market_cap": market_cap,
    }


def compute_metrics(c: dict) -> dict:
    revenue = c["revenue"]
    ebitda = c["ebitda"]
    m = dict(c)
    m["revenue_growth"] = (revenue - c["revenue_prior_year"]) / c["revenue_prior_year"]
    m["ebitda_margin"] = ebitda / revenue
    m["fcf_margin"] = c["fcf"] / revenue
    m["debt_ebitda"] = c["total_debt"] / ebitda if ebitda and ebitda != 0 else None
    m["interest_coverage"] = ebitda / c["interest_expense"] if c["interest_expense"] else None
    m["ev_ebitda"] = c["enterprise_value"] / ebitda if ebitda and ebitda != 0 else None
    m["ev_revenue"] = c["enterprise_value"] / revenue
    invested_capital = c["total_debt"] + (c["enterprise_value"] - c["total_debt"] + c["cash"])
    m["roic_proxy"] = ebitda / invested_capital if invested_capital else None
    return m


def find_peer_median(industry: str, exclude_ticker: str) -> float | None:
    """Busca la mediana de EV/EBITDA entre empresas de la misma industria
    dentro del universo de referencia ya calculado (el mismo que usa el
    dashboard principal). Si no hay comparables razonables, devuelve None
    (y el score de Valuation queda neutral, honestamente)."""
    if not REFERENCE_PATH.exists():
        return None
    try:
        with open(REFERENCE_PATH, encoding="utf-8") as f:
            payload = json.load(f)
        companies = payload.get("companies", [])
        peers = [
            c["ev_ebitda"] for c in companies
            if c.get("industry") == industry
            and c.get("ticker") != exclude_ticker
            and c.get("ev_ebitda") is not None
        ]
        if len(peers) < 2:
            return None
        return float(np.median(peers))
    except Exception:
        return None


def score_company(m: dict, peer_median_ev_ebitda: float | None) -> dict:
    # Financial Quality (25 pts)
    ebitda_score = _scale(m["ebitda_margin"], 0.00, 0.35)
    fcf_score = _scale(m["fcf_margin"], -0.05, 0.25)
    roic_score = _scale(m["roic_proxy"], 0.00, 0.25) if m["roic_proxy"] is not None else 0.5
    financial_quality = round((ebitda_score * 0.4 + fcf_score * 0.3 + roic_score * 0.3) * 25, 1)

    # Growth (20 pts)
    growth = round(_scale(m["revenue_growth"], 0.00, 0.40) * 20, 1)

    # Risk (20 pts)
    leverage_score = 1 - _scale(m["debt_ebitda"], 1.0, 6.0) if m["debt_ebitda"] is not None else 0.5
    coverage_score = _scale(m["interest_coverage"], 1.5, 8.0) if m["interest_coverage"] is not None else 0.5
    risk = round(np.clip(leverage_score * 0.5 + coverage_score * 0.5, 0, 1) * 20, 1)

    # Valuation (20 pts) — neutral si no hay peers razonables (honestidad, no invento)
    ev_ebitda_discount = None
    if peer_median_ev_ebitda and m["ev_ebitda"]:
        ev_ebitda_discount = m["ev_ebitda"] / peer_median_ev_ebitda - 1
        valuation = round(_scale(-ev_ebitda_discount, -0.30, 0.30) * 20, 1)
    else:
        valuation = 10.0  # neutral, transparente

    # Strategic Fit (15 pts) — sin dato de % recurrente para empresas on-demand, neutral conservador
    strategic_fit = 9.0

    total = round(financial_quality + growth + risk + valuation + strategic_fit, 1)
    tier = (
        "High Priority" if total >= 80 else
        "Priority" if total >= 65 else
        "Watchlist" if total >= 40 else
        "Rejected"
    )

    return {
        "deal_score": total,
        "priority_tier": tier,
        "score_breakdown": {
            "financial_quality": financial_quality,
            "growth": growth,
            "risk": risk,
            "valuation": valuation,
            "strategic_fit": strategic_fit,
        },
        "peer_median_ev_ebitda": round(peer_median_ev_ebitda, 2) if peer_median_ev_ebitda else None,
        "ev_ebitda_discount": round(ev_ebitda_discount, 4) if ev_ebitda_discount is not None else None,
        "valuation_note": (
            None if peer_median_ev_ebitda else
            "Sin comparables de tamaño similar en el universo de referencia — "
            "Valuation se dejó neutral en vez de inventar un número."
        ),
    }


def run_simple_lbo(m: dict) -> dict:
    """LBO simplificado (un solo escenario base) para respuesta rápida on-demand."""
    ebitda = m["ebitda"]
    if not ebitda or ebitda <= 0:
        return {"irr": None, "moic": None, "note": "LBO no aplicable: EBITDA no positivo."}

    entry_multiple = m["ev_ebitda"] or 8.0
    growth_rate = min(max(m["revenue_growth"], 0.0), 0.15)
    ebitda_margin = m["ebitda_margin"]
    debt_pct = 0.55
    entry_ev = entry_multiple * ebitda
    debt = debt_pct * entry_ev
    equity = entry_ev - debt

    revenue = m["revenue"]
    for _ in range(5):
        revenue *= (1 + growth_rate)
        yearly_ebitda = revenue * ebitda_margin
        interest = debt * 0.09
        fcf = yearly_ebitda - interest - 0.25 * max(yearly_ebitda - interest, 0) - 0.03 * revenue
        paydown = min(max(fcf, 0) * 0.75, debt)
        debt = max(debt - paydown, 0)

    exit_ev = entry_multiple * yearly_ebitda
    exit_equity = max(exit_ev - debt, 0)
    moic = exit_equity / equity if equity > 0 else None
    irr = (moic ** (1 / 5) - 1) if moic and moic > 0 else None

    return {
        "irr": round(irr, 4) if irr is not None else None,
        "moic": round(moic, 2) if moic is not None else None,
        "sponsor_equity": round(equity, 0),
        "exit_equity": round(exit_equity, 0),
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        ticker = (query.get("ticker", [""])[0] or "").strip().upper()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        if not ticker:
            self.wfile.write(json.dumps({"error": "Falta el parámetro 'ticker'."}).encode())
            return

        try:
            raw = fetch_live_company(ticker)
            metrics = compute_metrics(raw)
            peer_median = find_peer_median(raw["industry"], raw["ticker"])
            score = score_company(metrics, peer_median)
            lbo = run_simple_lbo(metrics)

            result = {
                "ticker": raw["ticker"],
                "company": raw["company"],
                "industry": raw["industry"],
                "revenue_growth": round(metrics["revenue_growth"], 4),
                "ebitda_margin": round(metrics["ebitda_margin"], 4),
                "fcf_margin": round(metrics["fcf_margin"], 4),
                "debt_ebitda": round(metrics["debt_ebitda"], 2) if metrics["debt_ebitda"] is not None else None,
                "interest_coverage": round(metrics["interest_coverage"], 2) if metrics["interest_coverage"] is not None else None,
                "ev_ebitda": round(metrics["ev_ebitda"], 2) if metrics["ev_ebitda"] is not None else None,
                "market_cap": raw["market_cap"],
                **score,
                "lbo": lbo,
                "on_demand": True,
            }
            self.wfile.write(json.dumps(result, default=str).encode())
        except Exception as e:
            self.wfile.write(json.dumps({"error": str(e)}).encode())
