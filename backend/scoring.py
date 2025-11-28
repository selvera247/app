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


def _call_ollama(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Helper to call Ollama and return parsed JSON.
    """
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
    return data


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

    data = _call_ollama(payload)

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


def generate_project_charter_ai(
    name: str,
    project_type: str,
    pain_points: str,
    systems_touched: str,
    revenue_flow_impacted: str,
    audit_critical: str,
) -> str:
    """
    Generate a standardized project charter in Markdown for the given project.
    Returns a markdown string (no JSON).
    """

    system_msg = (
        "You are a senior Finance Transformation leader creating clear, "
        "concise project charters for revenue-impacting initiatives."
    )

    user_prompt = f"""
Create a standardized project charter in clear Markdown for the following project.

Project Name: {name}
Project Type: {project_type}
Revenue Flow Impacted: {revenue_flow_impacted}
Audit Critical: {audit_critical}

Systems Touched:
{systems_touched}

Pain Points / Problem Description:
{pain_points}

The charter must use the following sections as Markdown headings:

# Project Charter – (use the project name in the title)

## 1. Problem Statement
- Summarize the core problem in 2–4 bullet points.

## 2. Objectives & Success Metrics
- List 3–5 concrete objectives.
- Include 3–5 example KPIs with directional targets (e.g. "Reduce revenue reclass volume by 40–60%").

## 3. Scope
- In-Scope: bullets.
- Out-of-Scope: bullets (call out what this project will NOT do).

## 4. Systems & Data Impact
- List the main systems and typical objects/tables impacted.
- Note any key data lineage considerations.

## 5. Risks, Dependencies & Assumptions
- Risks: bullets (especially if Audit Critical = Yes).
- Dependencies: bullets (e.g. other projects, teams, or data readiness).
- Assumptions: bullets.

## 6. Timeline & Phasing (High-Level)
- Phase 1: name + 1–2 bullets.
- Phase 2: name + 1–2 bullets.
- Phase 3: name + 1–2 bullets.

## 7. Stakeholders & RACI (Lite)
- List key roles (e.g. RevRec Lead, Billing PM, Data Engineering, FP&A).
- For each, indicate R/A/C/I in a simple text-friendly way (no tables required, a bullet list is fine).

Write in a professional but concise tone. Do NOT add any extra commentary outside of the Markdown charter.
"""

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_prompt},
        ],
        # We want plain text/markdown, not JSON here
        "stream": False,
    }

    data = _call_ollama(payload)
    message = data.get("message", {})
    content = message.get("content", "")

    # content should already be markdown text
    if not isinstance(content, str):
        content = str(content)

    return content
