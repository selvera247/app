import json
import os
from typing import Dict, Any

import requests
from dotenv import load_dotenv

# Load .env if present (optional, for custom config like OLLAMA_MODEL)
load_dotenv()

# Defaults for Ollama
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")


def score_project_ai(description: str, systems: str = "") -> Dict[str, Any]:
    """
    Calls a local Ollama model and returns:
    bi, risk, align, urgency, complexity, cost, priority_score,
    rationale, lenses, recommended_priority
    """

    system_msg = (
        "You are a senior Finance Transformation PMO helping score "
        "revenue-impacting projects. You ALWAYS respond in valid JSON."
    )

    user_prompt = f"""
Score this project from 1-5 in six areas:
- bi: Business Impact
- risk: Risk Exposure
- align: Strategic Alignment
- urgency: Time sensitivity
- complexity: Implementation Complexity
- cost: Effort/Cost

Rules of thumb:
- High revenue, DSO, or margin impact ⇒ bi 4-5.
- Regulatory / ASC 606 / tax risk ⇒ risk 4-5.
- Data foundation and scaling enablers ⇒ align 4-5.
- Needs to land this or next quarter ⇒ urgency 4-5.
- Multi-system or heavy migration ⇒ complexity 4-5.
- Requires significant Eng + PM + testing ⇒ cost 4-5.

Also return:
- rationale: short explanation string
- lenses: list of transformation lenses (e.g. ["Revenue Leakage Prevention", "Audit & Compliance"])
- recommended_priority: integer 1–5 (1 = highest priority)

Project description:
{description}

Systems touched:
{systems}

Respond ONLY with a JSON object, no extra text.
"""

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_prompt},
        ],
        "format": "json",   # ask Ollama for JSON
        "stream": False,
    }

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Error calling Ollama at {OLLAMA_URL}: {e}")

    data = resp.json()

    # For format=json, message.content is JSON-compatible
    message = data.get("message", {})
    content = message.get("content", "")

    if isinstance(content, dict):
        raw = content
    else:
        # content might be a JSON string
        raw = json.loads(content)

    def to_int(x, default=0):
        try:
            return int(x)
        except Exception:
            return default

    bi = to_int(raw.get("bi", 0))
    risk = to_int(raw.get("risk", 0))
    align = to_int(raw.get("align", 0))
    urgency = to_int(raw.get("urgency", 0))
    complexity = to_int(raw.get("complexity", 0))
    cost = to_int(raw.get("cost", 0))

    # priority = BI + Risk + Align + Urgency + (6 - Complexity) + (6 - Cost)
    priority_score = bi + risk + align + urgency + (6 - complexity) + (6 - cost)

    return {
        "bi": bi,
        "risk": risk,
        "align": align,
        "urgency": urgency,
        "complexity": complexity,
        "cost": cost,
        "priority_score": priority_score,
        "rationale": raw.get("rationale", ""),
        "lenses": raw.get("lenses", []),
        "recommended_priority": raw.get("recommended_priority", 1),
    }
