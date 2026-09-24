# AI-Powered Private Company Deal Screener

Plataforma de screening de oportunidades de inversión en empresas privadas.
Combina un motor financiero 100% determinístico en Python (métricas,
comparables, Deal Score, LBO, sensibilidad) con un LLM que actúa como
analista junior para redactar el investment memo cualitativo.

```
CSV/Excel → data_loader → financial_metrics → comparables → scoring
          → risk_engine → lbo_model → ai_interface → outputs/*.json → dashboard
```

## Instalación

```bash
cd deal_screener
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Uso rápido

```bash
cd src
python3 pipeline.py            # corre todo el pipeline incluyendo la IA
python3 pipeline.py --no-ai    # corre solo la parte cuantitativa (sin llamar al LLM)
```

El resultado se guarda en `outputs/deal_screening_results.json`: una lista
con un objeto por empresa, listo para alimentar un dashboard (R0Y u otro).

## Automatización (recomendado)

Hay 2 niveles de automatización, según lo que necesites:

- **Local (tu Mac):** ver `AUTOMATIZACION.md` — se actualiza solo cada 3
  días usando `launchd`, pero solo tú lo ves, y requiere que tu Mac esté
  encendida.
- **En la nube (público, recomendado):** ver `DEPLOY.md` — se publica en
  internet con un link real, se actualiza solo todos los días en los
  servidores de GitHub (sin depender de tu computadora), y cualquier
  persona con el link lo puede ver siempre actualizado.

```bash
bash refresh_all.sh   # corre el ciclo completo manualmente: datos → modelo → backtest → dashboard
```

## Conectar la IA (investment memo)

`ai_interface.py` llama por default a la API de Anthropic (Claude) usando
el formato estándar `/v1/messages`. Para activarlo:

```bash
export ANTHROPIC_API_KEY="tu_api_key"
python3 src/pipeline.py
```

Si no defines `ANTHROPIC_API_KEY`, el pipeline **no se rompe**: usa un
memo generado localmente (`_fallback_memo` en `ai_interface.py`) para que
puedas probar todo el flujo sin gastar tokens.

Si en vez de Claude quieres usar otro proveedor (por ejemplo un endpoint
compatible tipo OpenAI/Grok), solo cambia las variables de entorno:

```bash
export LLM_API_URL="https://tu-endpoint/v1/chat/completions"
export LLM_MODEL="nombre-del-modelo"
```
y ajusta el formato del `body` en `ai_interface.py` si el proveedor no usa
el esquema `role/content` de Anthropic (por ejemplo OpenAI-style usa
`messages` + `choices[0].message.content` en la respuesta en vez de
`content` con bloques `type: text`).

## Estructura

```
deal_screener/
├── data/companies.csv        # dataset de ejemplo (10 empresas)
├── src/
│   ├── data_loader.py        # carga y valida CSV/Excel
│   ├── financial_metrics.py  # márgenes, crecimiento, apalancamiento, múltiplos
│   ├── comparables.py        # peer median, descuento/premium de valuación
│   ├── scoring.py            # Deal Score 0-100 (5 pilares ponderados)
│   ├── risk_engine.py        # banderas de riesgo basadas en reglas
│   ├── lbo_model.py          # LBO a 5 años, IRR (Newton/Brent), MOIC
│   ├── sensitivity.py        # matriz IRR/MOIC vs. exit multiple y growth
│   ├── ai_interface.py       # arma el JSON y llama al LLM (Investment Memo)
│   └── pipeline.py           # orquesta todo el flujo
├── tests/                    # pytest-style tests (métricas, scoring, LBO)
├── outputs/                  # JSON con los resultados finales
└── requirements.txt
```

## Metodología del Deal Score (importante para explicar en entrevista)

El score **no lo decide la IA**. Es una fórmula determinística de 5 pilares:

| Pilar               | Puntos | Basado en |
|---------------------|--------|-----------|
| Financial Quality    | 25 | EBITDA margin, FCF margin, ROIC proxy |
| Growth               | 20 | Revenue growth YoY |
| Risk                 | 20 | Debt/EBITDA, interest coverage, concentración de clientes |
| Valuation            | 20 | Descuento/premium vs. mediana de peers (EV/EBITDA) |
| Strategic Fit        | 15 | % de revenue recurrente |

La IA solo interpreta esos números ya calculados para redactar el
investment thesis, riesgos, catalizadores y preguntas de due diligence —
nunca recalcula el score, el IRR ni el MOIC.

## Siguientes pasos (roadmap sugerido)

1. **V1 — Financial Engine** ✅ (`data_loader`, `financial_metrics`)
2. **V2 — Deal Screener** ✅ (`scoring`, ranking)
3. **V3 — PE Analysis** ✅ (`comparables`, `lbo_model`, `sensitivity`)
4. **V4 — AI Analyst** ✅ (`ai_interface`)
5. **V5 — Dashboard (R0Y)**: consumir `outputs/deal_screening_results.json`
   desde el frontend para el ranking, la ficha por empresa y la matriz de
   sensibilidad interactiva.
