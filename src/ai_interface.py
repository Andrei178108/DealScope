"""
ai_interface.py
-----------------
Toma los resultados 100% cuantitativos (Python) de una empresa y se los
entrega a un LLM para que actúe como "junior investment analyst":
redacta el Investment Thesis, Risks, Catalysts y Due Diligence Questions.

La IA NUNCA calcula el Deal Score, el IRR ni el MOIC — solo interpreta
números que Python ya calculó. Esto es clave para poder defender la
metodología ("el score es determinístico, la IA solo lo redacta").

Funciona con cualquier API compatible con el formato de mensajes de
Anthropic (role/content). Por default apunta a la API de Anthropic,
pero basta con cambiar API_URL y MODEL si quieres usar otro proveedor
(por ejemplo un endpoint compatible con OpenAI/Grok).
"""

from __future__ import annotations
import os
import json
import requests

API_URL = os.environ.get("LLM_API_URL", "https://api.anthropic.com/v1/messages")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-6")

SYSTEM_PROMPT = """You are a private equity investment analyst.
You will be given ONLY pre-computed quantitative outputs (deal score,
growth, margins, leverage, valuation vs. peers, LBO IRR/MOIC, and
detected risk flags) for a single target company. You do not recalculate
any numbers. Your job is to interpret them like a junior analyst writing
the qualitative section of an investment memo.

Return ONLY valid JSON with this exact schema, no markdown, no preamble:
{
  "investment_thesis": "2-4 sentences",
  "strengths": ["...", "..."],
  "risks": ["...", "..."],
  "catalysts": ["...", "..."],
  "red_flags": ["...", "..."],
  "due_diligence_questions": ["...", "...", "..."],
  "recommendation": "one of: Advance to preliminary due diligence | Monitor / Watchlist | Pass"
}
"""


class AIInterfaceError(Exception):
    pass


def build_payload(company_summary: dict) -> str:
    """Convierte el resumen cuantitativo de una empresa a un JSON compacto para el prompt."""
    return json.dumps(company_summary, indent=2, default=str)


def generate_investment_memo(company_summary: dict, timeout: int = 60) -> dict:
    """
    company_summary: dict con las métricas ya calculadas por Python, p.ej.:
        {
          "company": "Alpha Software",
          "deal_score": 91,
          "priority_tier": "High Priority",
          "revenue_growth": 0.38,
          "ebitda_margin": 0.24,
          "debt_ebitda": 1.8,
          "interest_coverage": 7.4,
          "peer_median_ev_ebitda": 19.8,
          "target_ev_ebitda": 17.1,
          "ev_ebitda_discount": -0.136,
          "largest_customer_pct": 0.12,
          "recurring_revenue_pct": 0.86,
          "irr": 0.251,
          "moic": 2.9,
          "risk_flags": ["Customer concentration"]
        }

    Devuelve el dict parseado con investment_thesis / strengths / risks / etc.
    Si no hay API key configurada, devuelve un memo generado localmente
    (fallback determinístico) para que el pipeline nunca se rompa.
    """
    if not API_KEY:
        return _fallback_memo(company_summary)

    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": MODEL,
        "max_tokens": 1000,
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": build_payload(company_summary)}
        ],
    }

    try:
        resp = requests.post(API_URL, headers=headers, json=body, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise AIInterfaceError(f"Fallo al llamar al LLM: {e}") from e

    data = resp.json()
    text_blocks = [c["text"] for c in data.get("content", []) if c.get("type") == "text"]
    raw_text = "\n".join(text_blocks).strip()

    # Limpieza por si el modelo agrega ```json ... ```
    raw_text = raw_text.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise AIInterfaceError(f"El LLM no devolvió JSON válido: {raw_text[:300]}") from e


def _fallback_memo(s: dict) -> dict:
    """Memo simple sin llamar a ningún LLM (para poder probar el pipeline offline)."""
    strengths, risks = [], []

    if s.get("revenue_growth", 0) > 0.20:
        strengths.append("Revenue growth is well above typical peer benchmarks.")
    if s.get("ebitda_margin", 0) > 0.15:
        strengths.append("EBITDA margin indicates a healthy underlying business model.")
    if s.get("ev_ebitda_discount", 0) < -0.05:
        strengths.append("Trades at a discount to peer median valuation multiples.")

    if s.get("largest_customer_pct", 0) > 0.25:
        risks.append("Meaningful customer concentration risk.")
    if s.get("debt_ebitda", 0) > 4:
        risks.append("Elevated leverage relative to EBITDA.")
    if not risks:
        risks.append("No major quantitative red flags detected; qualitative diligence still required.")

    tier = s.get("priority_tier", "Watchlist")
    recommendation = {
        "High Priority": "Advance to preliminary due diligence",
        "Priority": "Advance to preliminary due diligence",
        "Watchlist": "Monitor / Watchlist",
        "Rejected": "Pass",
    }.get(tier, "Monitor / Watchlist")

    return {
        "investment_thesis": (
            f"{s.get('company', 'The company')} scores {s.get('deal_score', 'N/A')}/100 on the "
            "internal screening model, driven by its growth and margin profile relative to peers."
        ),
        "strengths": strengths or ["Solid fundamentals relative to the peer set."],
        "risks": risks,
        "catalysts": ["Multiple expansion if growth persists.", "Margin improvement from operating leverage."],
        "red_flags": risks if s.get("deal_score", 100) < 50 else [],
        "due_diligence_questions": [
            "What explains the recent revenue growth trajectory?",
            "How concentrated is the customer base and what are churn dynamics?",
            "What assumptions underpin the exit multiple used in the LBO?",
        ],
        "recommendation": recommendation,
        "_note": "Generated by local fallback (no ANTHROPIC_API_KEY set) — not by the LLM.",
    }


if __name__ == "__main__":
    sample = {
        "company": "Alpha Software",
        "deal_score": 91,
        "priority_tier": "High Priority",
        "revenue_growth": 0.38,
        "ebitda_margin": 0.24,
        "debt_ebitda": 1.8,
        "interest_coverage": 7.4,
        "ev_ebitda_discount": -0.136,
        "largest_customer_pct": 0.12,
        "recurring_revenue_pct": 0.86,
        "irr": 0.251,
        "moic": 2.9,
    }
    memo = generate_investment_memo(sample)
    print(json.dumps(memo, indent=2))
