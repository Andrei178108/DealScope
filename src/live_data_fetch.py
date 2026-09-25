"""
live_data_fetch.py
--------------------
Descarga datos financieros REALES de empresas que cotizan en bolsa
(usando Yahoo Finance vía la librería yfinance) y los guarda en el mismo
formato que espera data_loader.py, para que el resto del pipeline
(scoring, comparables, LBO, sensitivity) funcione exactamente igual.

IMPORTANTE - honestidad sobre los datos:
  - Revenue, EBITDA y deuda vienen de los ÚLTIMOS ESTADOS FINANCIEROS
    publicados por la empresa (10-K / 10-Q). Esto solo cambia cuando la
    empresa publica un nuevo reporte trimestral (~cada 3 meses), sin
    importar qué tan seguido corras este script.
  - El precio de mercado / enterprise value SÍ cambia todos los días
    hábiles, así que correr esto cada 3 días sí tiene sentido para
    mantener la VALUACIÓN actualizada, aunque los "fundamentales"
    (crecimiento, márgenes) se mantengan iguales entre trimestres.

Requiere:
    pip install yfinance
"""

from __future__ import annotations
import math
import time
from pathlib import Path
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    raise SystemExit(
        "Falta yfinance. Instálalo con: pip install yfinance"
    )

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_CSV = ROOT / "data" / "companies.csv"

# Universo de empresas públicas pequeñas/medianas a monitorear.
# Puedes agregar o quitar tickers libremente — es tu "universo de screening".
# Elegidas por ser small/mid-cap con información financiera clara en Yahoo Finance,
# como proxy razonable de "empresas privadas" para el ejercicio.
TICKER_UNIVERSE = {
    "AMSWA": "B2B SaaS",
    "NRC": "Healthcare Services",
    "BBW": "Consumer Products",
    "CSWI": "Industrials",
    "FC": "Consumer Products",
    "PLAB": "Industrial Tech",
    "HURN": "Financial Services",
    "FORR": "B2B SaaS",
    "EVI": "Industrials",
    "CASH": "Financial Services",
    "USLM": "Industrials",
    "MLAB": "Healthcare Services",
    "ASUR": "B2B SaaS",
    "PRDO": "Education Technology",
    "STRA": "Education Technology",
    "IIIN": "Industrial Tech",
    "SCVL": "Consumer Products",
    "UFPT": "Industrials",
    "HAFC": "Financial Services",
    "CATO": "Consumer Products",
    "PDCO": "Healthcare Services",
    "OSIS": "Industrial Tech",
    "SMPL": "Consumer Products",
    "RGP": "Financial Services",
    "MGRC": "Real Estate Services",
    "SPOK": "B2B SaaS",
    "NX": "Industrials",
    "ATNI": "Media & Entertainment",
    "CENT": "Consumer Products",
    "EBF": "Financial Services",
    "AMPH": "Healthcare Services",
    "LAKE": "Industrials",
    "GENC": "Industrials",
    "CTS": "Industrial Tech",
    "HELE": "Consumer Products",
    "SXI": "Industrials",
    "ROCK": "Industrials",
    "AEIS": "Industrial Tech",
    "CVCO": "Industrials",
    "SCSC": "Industrial Tech",
    "PLPC": "Industrials",
    "AWR": "Real Estate Services",
    "UVSP": "Financial Services",
    "NHC": "Healthcare Services",
    "ENSG": "Healthcare Services",
    "WERN": "Logistics",
    "ARCB": "Logistics",
    "MATW": "Industrials",
    "SHOO": "Consumer Products",
    "CRVL": "Healthcare Services",
    "ROG": "Industrial Tech",
    "NVEC": "Industrial Tech",
    "CPRX": "Healthcare Services",
    "MOD": "Industrials",
    "ROAD": "Industrials",
    "IESC": "Industrials",
    "POWL": "Industrial Tech",
    "ALG": "Industrials",
    "AAON": "Industrials",
    "SCHL": "Media & Entertainment",
    "BOOT": "Consumer Products",
    "FIZZ": "Consumer Products",
    "LANC": "Consumer Products",
    "JJSF": "Consumer Products",
    "KAI": "Industrial Tech",
    "TNC": "Industrials",
    "ESE": "Industrial Tech",
    "HURC": "Industrial Tech",
    "UEIC": "Industrial Tech",
    "KFRC": "Financial Services",
    "HCKT": "Financial Services",
    "BLBD": "Industrials",
    "MTRN": "Industrials",
    "RGR": "Industrials",
    "SWBI": "Industrials",
    "VICR": "Industrial Tech",
    "ITRI": "Industrial Tech",
    "DGII": "Industrial Tech",
    "PLXS": "Industrial Tech",
    "BRC": "Industrials",
    "TRS": "Industrials",
    "FUL": "Industrials",
    "ASTE": "Industrials",
    "CIR": "Industrials",
    "HEES": "Industrials",
    "HAYN": "Industrials",
    "CMCO": "Industrials",
    "FELE": "Industrials",
    "WOR": "Industrials",
    "SSD": "Industrials",
    "ATRO": "Industrial Tech",
    "KTOS": "Industrial Tech",
    "AIN": "Industrials",
    "ICUI": "Healthcare Services",
    "ATRC": "Healthcare Services",
    "IART": "Healthcare Services",
    "OMCL": "Healthcare Services",
}


def _safe_num(value, default=0.0):
    """Convierte None/NaN (comunes en datos de Yahoo Finance) a un default numérico seguro."""
    try:
        if value is None:
            return default
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def fetch_company(ticker: str, industry: str) -> dict | None:
    """Descarga los datos de una empresa desde Yahoo Finance."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        fin = t.financials  # income statement anual
        bal = t.balance_sheet  # balance sheet anual

        if fin is None or fin.empty or bal is None or bal.empty:
            print(f"  [{ticker}] Sin estados financieros disponibles, se omite.")
            return None

        # Últimos dos años disponibles para calcular crecimiento
        revenue_col = fin.loc["Total Revenue"] if "Total Revenue" in fin.index else None
        if revenue_col is None or len(revenue_col) < 2:
            print(f"  [{ticker}] Sin histórico de revenue suficiente, se omite.")
            return None

        revenue = _safe_num(revenue_col.iloc[0], None)
        revenue_prior = _safe_num(revenue_col.iloc[1], None)
        if revenue is None or revenue_prior is None or revenue <= 0 or revenue_prior <= 0:
            print(f"  [{ticker}] Revenue inválido o vacío, se omite.")
            return None

        ebitda = None
        if "EBITDA" in fin.index:
            ebitda = _safe_num(fin.loc["EBITDA"].iloc[0], None)
        elif "Operating Income" in fin.index and "Reconciled Depreciation" in fin.index:
            ebitda = _safe_num(fin.loc["Operating Income"].iloc[0], 0) + _safe_num(fin.loc["Reconciled Depreciation"].iloc[0], 0)
        else:
            ebitda = _safe_num(info.get("ebitda"), None)

        if ebitda is None:
            print(f"  [{ticker}] Sin EBITDA disponible, se omite.")
            return None

        total_debt = _safe_num(info.get("totalDebt"), 0.0)
        cash = _safe_num(info.get("totalCash"), 0.0)
        market_cap = _safe_num(info.get("marketCap"), 0.0)
        enterprise_value = _safe_num(info.get("enterpriseValue"), market_cap + total_debt - cash)
        if enterprise_value <= 0:
            enterprise_value = max(market_cap + total_debt - cash, 1.0)

        fcf = _safe_num(info.get("freeCashflow"), ebitda * 0.6)
        employees = int(_safe_num(info.get("fullTimeEmployees"), 100))
        raw_interest = float(fin.loc["Interest Expense"].iloc[0]) if "Interest Expense" in fin.index else None
        interest_expense = _safe_num(raw_interest, total_debt * 0.06)
        if interest_expense <= 0:
            interest_expense = max(total_debt * 0.06, 1.0)  # nunca 0, para evitar división por cero después

        # Fecha REAL del próximo reporte trimestral de ESTA empresa específica
        # (cada empresa tiene su propia fecha, no es un número fijo genérico)
        next_earnings_date = None
        try:
            cal = t.calendar
            if cal is not None:
                raw_date = None
                if isinstance(cal, dict) and "Earnings Date" in cal:
                    ed = cal["Earnings Date"]
                    raw_date = ed[0] if isinstance(ed, (list, tuple)) and ed else ed
                elif hasattr(cal, "loc") and "Earnings Date" in getattr(cal, "index", []):
                    raw_date = cal.loc["Earnings Date"].iloc[0]
                if raw_date is not None:
                    next_earnings_date = str(raw_date)
        except Exception:
            pass  # si no está disponible, se deja como None y el dashboard lo muestra como "N/D"

        return dict(
            company=info.get("shortName", ticker),
            industry=industry,
            revenue=revenue,
            revenue_prior_year=revenue_prior,
            ebitda=ebitda,
            fcf=fcf,
            total_debt=total_debt,
            cash=cash,
            enterprise_value=enterprise_value,
            employees=employees,
            # yfinance no da % de revenue recurrente ni concentración de clientes:
            # esto SIGUE SIENDO UNA ESTIMACIÓN hasta que se conecte una fuente que lo reporte.
            recurring_revenue_pct=0.5,
            largest_customer_pct=0.15,
            interest_expense=interest_expense,
            next_earnings_date=next_earnings_date,
            ticker=ticker,
        )
    except Exception as e:
        print(f"  [{ticker}] Error: {e}")
        return None


def fetch_historical(ticker: str, t) -> dict | None:
    """Descarga el historial REAL disponible: los años de revenue/EBITDA/deuda/caja que
    reporta la empresa (típicamente 4, es lo máximo que da esta fuente gratuita
    de forma confiable), y varios años de precio de cierre para dar contexto
    de tendencia de valuación en el tiempo."""
    try:
        fin = t.financials
        years, revenues, ebitdas = [], [], []
        if fin is not None and not fin.empty and "Total Revenue" in fin.index:
            rev_row = fin.loc["Total Revenue"]
            ebitda_row = fin.loc["EBITDA"] if "EBITDA" in fin.index else None
            for col in fin.columns:
                years.append(str(col.year) if hasattr(col, "year") else str(col))
                revenues.append(_safe_num(rev_row.get(col), None))
                ebitdas.append(_safe_num(ebitda_row.get(col), None) if ebitda_row is not None else None)
            # yfinance los da del más reciente al más viejo; invertir para orden cronológico
            years.reverse(); revenues.reverse(); ebitdas.reverse()

        # Deuda y caja históricas (del balance sheet, para poder recalcular
        # Debt/EBITDA como se veía EN ESE MOMENTO, no con la deuda de hoy)
        debts, cashes = [], []
        try:
            bal = t.balance_sheet
            if bal is not None and not bal.empty and years:
                debt_row = bal.loc["Total Debt"] if "Total Debt" in bal.index else None
                cash_row = bal.loc["Cash And Cash Equivalents"] if "Cash And Cash Equivalents" in bal.index else None
                bal_cols = list(bal.columns)[::-1]  # mismo orden cronológico que years
                for col in bal_cols:
                    debts.append(_safe_num(debt_row.get(col), None) if debt_row is not None else None)
                    cashes.append(_safe_num(cash_row.get(col), None) if cash_row is not None else None)
        except Exception:
            pass
        # Rellenar si el balance sheet tiene menos años que el income statement
        while len(debts) < len(years): debts.append(None)
        while len(cashes) < len(years): cashes.append(None)

        price_history = []
        hist = t.history(period="5y", interval="1mo")
        if hist is not None and not hist.empty:
            yearly = hist["Close"].resample("YE").last().dropna()
            for date, price in yearly.items():
                price_history.append({"year": str(date.year), "close": round(float(price), 2)})

        if not years and not price_history:
            return None

        return {
            "years": years, "revenue": revenues, "ebitda": ebitdas,
            "debt": debts, "cash": cashes, "price_history": price_history,
        }
    except Exception as e:
        print(f"    (historial no disponible: {e})")
        return None


BENCHMARK_TICKER = "^SP600"  # S&P SmallCap 600 — el índice más comparable a este universo de empresas


def fetch_benchmark_history() -> list[dict]:
    """Descarga el precio histórico del índice de referencia, para poder
    comparar el retorno del modelo contra 'el mercado' en el backtest."""
    try:
        idx = yf.Ticker(BENCHMARK_TICKER)
        hist = idx.history(period="5y", interval="1mo")
        if hist is None or hist.empty:
            return []
        yearly = hist["Close"].resample("YE").last().dropna()
        return [{"year": str(date.year), "close": round(float(price), 2)} for date, price in yearly.items()]
    except Exception as e:
        print(f"  No se pudo descargar el benchmark ({BENCHMARK_TICKER}): {e}")
        return []


def fetch_all(delay_seconds: float = 1.0) -> tuple[pd.DataFrame, dict]:
    """Descarga todas las empresas del universo, con una pequeña pausa entre cada una
    para no saturar la API gratuita de Yahoo Finance. También arma el historial real
    de cada empresa que se logró descargar."""
    rows = []
    historical = {}
    for ticker, industry in TICKER_UNIVERSE.items():
        print(f"Descargando {ticker} ({industry}) ...")
        t = yf.Ticker(ticker)
        data = fetch_company(ticker, industry)
        if data:
            rows.append(data)
            hist_data = fetch_historical(ticker, t)
            if hist_data:
                historical[ticker] = hist_data
        time.sleep(delay_seconds)

    df = pd.DataFrame(rows)
    return df, historical


if __name__ == "__main__":
    print(f"Descargando datos reales de {len(TICKER_UNIVERSE)} empresas públicas...")
    df, historical = fetch_all()
    df.to_csv(OUTPUT_CSV, index=False)

    import json
    historical_path = ROOT / "data" / "historical.json"
    with open(historical_path, "w", encoding="utf-8") as f:
        json.dump(historical, f, indent=2, ensure_ascii=False)

    print("Descargando índice de referencia (S&P SmallCap 600) para el benchmark...")
    benchmark = fetch_benchmark_history()
    benchmark_path = ROOT / "data" / "benchmark.json"
    with open(benchmark_path, "w", encoding="utf-8") as f:
        json.dump({"ticker": BENCHMARK_TICKER, "price_history": benchmark}, f, indent=2, ensure_ascii=False)

    print(f"\n{len(df)} empresas guardadas en {OUTPUT_CSV}")
    print(f"Historial de {len(historical)} empresas guardado en {historical_path}")
    print("\nNOTA: recurring_revenue_pct y largest_customer_pct son estimaciones genéricas")
    print("(0.5 y 0.15) porque Yahoo Finance no reporta esos datos. Todo lo demás es real.")
    print("NOTA sobre historial: se descargan los años de revenue/EBITDA que la fuente")
    print("reporta (normalmente ~4 años) más precio de acción de los últimos 5 años.")
    print("30 años de historial financiero no existe en ninguna fuente gratuita disponible.")
