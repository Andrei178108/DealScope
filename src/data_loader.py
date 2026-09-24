"""
data_loader.py
--------------
Carga la información cruda de las empresas (CSV/Excel) y valida
que las columnas requeridas existan y sean numéricas donde corresponde.
"""

from __future__ import annotations
import pandas as pd
from pathlib import Path

REQUIRED_COLUMNS = [
    "company",
    "industry",
    "revenue",
    "revenue_prior_year",
    "ebitda",
    "fcf",
    "total_debt",
    "cash",
    "enterprise_value",
    "employees",
    "recurring_revenue_pct",
    "largest_customer_pct",
    "interest_expense",
]

NUMERIC_COLUMNS = [c for c in REQUIRED_COLUMNS if c not in ("company", "industry")]


class DataValidationError(Exception):
    """Se lanza cuando el dataset de entrada no cumple el esquema esperado."""


def load_companies(path: str | Path) -> pd.DataFrame:
    """
    Carga un archivo CSV o Excel con datos financieros de empresas privadas.

    Parameters
    ----------
    path : str | Path
        Ruta al archivo .csv, .xlsx o .xls

    Returns
    -------
    pd.DataFrame
        DataFrame validado y con tipos correctos.
    """
    path = Path(path)

    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    elif path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        raise DataValidationError(f"Formato no soportado: {path.suffix}")

    _validate_schema(df)
    df = _coerce_types(df)
    df = _validate_values(df)

    return df.reset_index(drop=True)


def _validate_schema(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DataValidationError(f"Faltan columnas requeridas: {missing}")


def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _validate_values(df: pd.DataFrame) -> pd.DataFrame:
    """Elimina filas con valores faltantes/no numéricos en vez de tronar todo el pipeline
    por una sola empresa problemática (común con datos en vivo de fuentes externas)."""
    bad_mask = df[NUMERIC_COLUMNS].isnull().any(axis=1)
    if bad_mask.any():
        dropped = df.loc[bad_mask, "company"].tolist()
        print(f"  Aviso: se omiten {len(dropped)} empresas con datos incompletos: {dropped}")
        df = df.loc[~bad_mask].copy()

    bad_revenue = df["revenue"] <= 0
    if bad_revenue.any():
        dropped = df.loc[bad_revenue, "company"].tolist()
        print(f"  Aviso: se omiten {len(dropped)} empresas con revenue <= 0: {dropped}")
        df = df.loc[~bad_revenue].copy()

    if df.empty:
        raise DataValidationError("Ninguna empresa quedó con datos válidos después de la limpieza.")

    return df


if __name__ == "__main__":
    df = load_companies("data/companies.csv")
    print(f"Cargadas {len(df)} empresas")
    print(df.head())
