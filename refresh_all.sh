#!/bin/bash
# refresh_all.sh
# ----------------
# Corre el ciclo completo: descarga datos reales, recalcula el modelo,
# corre el backtest, y regenera el dashboard — con manejo de errores real:
# si algo falla, queda registrado en data/run_status.json y NO se toca
# el dashboard.html anterior (que sigue siendo válido).
#
# Uso manual:   bash refresh_all.sh
# Uso automático: ver AUTOMATIZACION.md para configurar launchd (Mac).

cd "$(dirname "$0")"
STATUS_FILE="data/run_status.json"
LOG_FILE="refresh_log.txt"
START_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

notify() {
  # Notificación nativa de macOS (silenciosa si no es Mac o si falla, no rompe el script)
  osascript -e "display notification \"$2\" with title \"DealScope\" subtitle \"$1\"" 2>/dev/null || true
}

write_status() {
  # $1 = status ("success" | "failed"), $2 = mensaje, $3 = paso que falló (o "")
  mkdir -p data
  cat > "$STATUS_FILE" << EOF
{
  "status": "$1",
  "message": "$2",
  "failed_step": "$3",
  "started_at": "$START_TIME",
  "finished_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF
}

fail_and_exit() {
  local step="$1"
  echo "ERROR en: $step"
  write_status "failed" "Falló en: $step. Revisa $LOG_FILE para más detalle." "$step"
  notify "Actualización falló ⚠️" "Falló en: $step — revisa refresh_log.txt"
  exit 1
}

source .venv/bin/activate 2>/dev/null || {
  echo "No se encontró el entorno virtual (.venv). Corre primero:"
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  write_status "failed" "Entorno virtual no encontrado" "setup"
  exit 1
}

echo "[1/4] Descargando datos financieros reales de empresas públicas..."
cd src
python3 live_data_fetch.py || { cd ..; fail_and_exit "descarga de datos (live_data_fetch.py)"; }

echo "[2/4] Recalculando Deal Score, comparables, LBO y sensitivity..."
python3 pipeline.py --no-ai || { cd ..; fail_and_exit "cálculo del modelo (pipeline.py)"; }

echo "[3/4] Corriendo backtest (score histórico vs. retorno real)..."
python3 backtest.py || echo "  Aviso: backtest no se pudo correr (no bloquea el resto)."

echo "[4/4] Regenerando dashboard.html con los datos actualizados..."
python3 build_dashboard.py || { cd ..; fail_and_exit "generación del dashboard (build_dashboard.py)"; }

cd ..
N_COMPANIES=$(python3 -c "import json; print(len(json.load(open('outputs/deal_screening_results.json'))['companies']))" 2>/dev/null || echo "?")

write_status "success" "Actualización completada: $N_COMPANIES empresas procesadas." ""
notify "Actualización completada ✅" "$N_COMPANIES empresas procesadas — dashboard listo."

echo ""
echo "Listo. Última actualización: $(date)"
echo "Abre dashboard.html para ver los resultados."
