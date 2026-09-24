# Changelog — DealScope

## v16 — Automatización en la nube (100% público)
- GitHub Actions: workflow que corre el modelo automáticamente todos los
  días, en los servidores de GitHub — sin depender de que la computadora
  del usuario esté encendida.
- Guía completa (`DEPLOY.md`) para publicar en Vercel con un link real,
  encadenado a la actualización automática (cada corrida re-publica el
  sitio solo).
- Soporte para activar la IA real en la nube vía GitHub Secrets, sin
  tocar código.

## v15 — Automatización de nivel producción
- `refresh_all.sh` reescrito con manejo de errores robusto: cada paso se
  valida, y si algo falla, se registra en `data/run_status.json` sin
  tocar el dashboard existente.
- Notificaciones nativas de macOS al terminar cada actualización
  (éxito o fallo).
- `build_dashboard.py` se auto-valida antes de publicar: escribe a un
  archivo temporal, confirma que el JSON embebido es válido, y solo
  entonces reemplaza el dashboard real (swap atómico). Nunca se publica
  una versión rota.
- Indicador de salud del sistema visible en el dashboard (punto verde/rojo
  + fecha de la última corrida automática).
- Automatización vía `launchd` (nativo de macOS) en vez de `cron`, con
  guía completa en `AUTOMATIZACION.md`.

## v14 — Monte Carlo a escala institucional
- Simulación Monte Carlo subida de 2,000 a 10,000 escenarios por empresa.
- Nueva métrica: probabilidad de que el LBO supere el retorno anualizado
  real del benchmark (S&P SmallCap 600), con explicación automática del
  resultado.

## v13 — Vista de gráficas y glosario integrado
- Pestañas "Ranking" / "Gráficas": galería con tendencia financiera,
  historial de score, y distribución Monte Carlo por empresa.
- Glosario completo embebido en el dashboard (30+ términos).

## v12 — Historial, PDF, y peer groups por ML
- Historial del Deal Score en el tiempo (cada corrida guarda un punto).
- Descarga de investment memo en PDF por empresa.
- Peer groups calculados con clustering (k-means) sobre métricas
  financieras reales, en vez de industria asignada manualmente.
- Fix: Monte Carlo ahora corre en todas las empresas con EBITDA positivo
  (antes limitado al top 10).

## v11 — Validación avanzada del modelo
- Simulación Monte Carlo (primera versión, 2,000 escenarios).
- Backtest comparado contra un índice de mercado real (benchmark).
- Pesos del Deal Score ajustables en vivo desde el dashboard (sliders).

## v10 — Backtest de validación
- Módulo de backtest: recalcula un score simplificado con datos
  históricos reales y lo compara contra el retorno de precio real,
  para probar si el modelo predice desempeño.

## v9 — Historial financiero real y countdowns en vivo
- Historial de revenue/EBITDA/precio de acción por empresa (datos reales).
- Countdowns en tiempo real (segundos corriendo) para próxima
  actualización y próximo reporte trimestral por empresa.
- Universo de empresas ampliado a 55 tickers reales.

## v8 — Funciones de herramienta de trabajo
- Comparar empresas lado a lado (selección múltiple).
- Exportar ranking a CSV y PDF.
- Gráfica de dispersión Growth vs. Valuation coloreada por tier.

## v7 — Corrección de integridad de datos
- Fix de un bug de extracción de datos que corrompía el dashboard.

## v6 — Motor de datos en vivo
- Conexión automática a datos financieros reales vía Yahoo Finance.
- Script `refresh_all.sh` para correr el ciclo completo en un comando.

## v1-v5 — Fundamentos
- Motor cuantitativo completo: métricas financieras, comparables,
  Deal Score (5 pilares), modelo LBO, análisis de sensibilidad.
- Integración con LLM para investment memo (con fallback local).
- Dashboard web con landing page, buscador, y empresas destacadas.
