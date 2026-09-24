"""
build_dashboard.py
--------------------
Toma templates/dashboard_template.html (el diseño del dashboard, con un
placeholder donde van los datos) y outputs/deal_screening_results.json
(los resultados más recientes del pipeline), y genera dashboard.html
listo para abrir en el navegador — sin tener que tocar el HTML a mano
cada vez que se corre el modelo con datos nuevos.

Auto-validación: antes de publicar, se verifica que el JSON embebido
sea válido y que la estructura no haya quedado corrupta. Si algo falla,
el dashboard.html anterior (válido) NO se toca — nunca se publica una
versión rota.
"""

from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "templates" / "dashboard_template.html"
RESULTS_PATH = ROOT / "outputs" / "deal_screening_results.json"
BACKTEST_PATH = ROOT / "outputs" / "backtest_results.json"
STATUS_PATH = ROOT / "data" / "run_status.json"
OUTPUT_PATH = ROOT / "dashboard.html"
TEMP_OUTPUT_PATH = ROOT / "dashboard.html.tmp"

PLACEHOLDER = "__DEAL_DATA_PLACEHOLDER__"
BACKTEST_PLACEHOLDER = "__BACKTEST_DATA_PLACEHOLDER__"
STATUS_PLACEHOLDER = "__RUN_STATUS_PLACEHOLDER__"


def _validate_embedded_json(html: str, marker: str, expect_after: str) -> None:
    """Confirma que el bloque de datos embebido después de `marker` es JSON
    válido y que justo después viene lo que se espera (sin texto sobrante
    de una corrupción). Usa el parser real de JSON, no conteo de caracteres."""
    start = html.index(marker) + len(marker)
    decoder = json.JSONDecoder()
    _, end_idx = decoder.raw_decode(html, start)  # lanza ValueError si no es JSON válido
    tail = html[end_idx:end_idx + len(expect_after)]
    if not tail.startswith(expect_after):
        raise ValueError(
            f"Validación falló después de '{marker.strip()}': "
            f"se esperaba que empezara con {expect_after!r}, pero siguió con {tail!r}"
        )


def build_dashboard() -> None:
    if not RESULTS_PATH.exists():
        raise SystemExit(
            f"No existe {RESULTS_PATH}. Corre primero: python3 pipeline.py"
        )

    with open(RESULTS_PATH, encoding="utf-8") as f:
        payload = json.load(f)  # {"generated_at":..., "next_refresh_due":..., "companies":[...]}

    backtest_payload = None
    if BACKTEST_PATH.exists():
        with open(BACKTEST_PATH, encoding="utf-8") as f:
            backtest_payload = json.load(f)

    status_payload = None
    if STATUS_PATH.exists():
        with open(STATUS_PATH, encoding="utf-8") as f:
            status_payload = json.load(f)

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    data_json = json.dumps(payload, ensure_ascii=False)
    backtest_json = json.dumps(backtest_payload, ensure_ascii=False)
    status_json = json.dumps(status_payload, ensure_ascii=False)

    for placeholder in (PLACEHOLDER, BACKTEST_PLACEHOLDER, STATUS_PLACEHOLDER):
        if placeholder not in template:
            raise SystemExit(f"No se encontró el placeholder {placeholder} en la plantilla.")

    final_html = (
        template
        .replace(PLACEHOLDER, data_json)
        .replace(BACKTEST_PLACEHOLDER, backtest_json)
        .replace(STATUS_PLACEHOLDER, status_json)
    )

    # Escribir a un archivo temporal primero, y solo reemplazar el dashboard
    # real si la validación pasa. Así nunca se publica una versión rota.
    TEMP_OUTPUT_PATH.write_text(final_html, encoding="utf-8")

    try:
        check_html = TEMP_OUTPUT_PATH.read_text(encoding="utf-8")
        _validate_embedded_json(check_html, "const SCREEN_DATA = ", ";\nconst DEAL_DATA")
        _validate_embedded_json(check_html, "const BACKTEST_DATA = ", ";")
        _validate_embedded_json(check_html, "const RUN_STATUS = ", ";")
    except Exception as e:
        TEMP_OUTPUT_PATH.unlink(missing_ok=True)
        raise SystemExit(
            f"VALIDACIÓN FALLÓ — no se publicó el dashboard nuevo, se conserva el anterior.\n"
            f"Detalle: {e}"
        )

    TEMP_OUTPUT_PATH.replace(OUTPUT_PATH)  # swap atómico

    n = len(payload.get("companies", []))
    print(f"dashboard.html regenerado y validado con {n} empresas -> {OUTPUT_PATH}")


if __name__ == "__main__":
    build_dashboard()
