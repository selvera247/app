from pathlib import Path
from typing import List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .scoring import score_project_ai, generate_project_charter_ai

app = FastAPI(title="Revenue Project Copilot API")

# Path to projects.csv (assumes you run uvicorn from repo root)
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECTS_PATH = BASE_DIR / "projects.csv"


# ---------- Pydantic models ----------
class ScoreRequest(BaseModel):
    description: str
    systems: Optional[str] = ""


class ScoreResponse(BaseModel):
    bi: int
    risk: int
    align: int
    urgency: int
    complexity: int
    cost: int
    priority_score: int
    rationale: str
    lenses: List[str] = []
    recommended_priority: int


class ProjectScoreRequest(BaseModel):
    project_id: int  # must match the 'id' column in projects.csv
    description_override: Optional[str] = None
    systems_override: Optional[str] = None


class CharterRequest(BaseModel):
    name: str
    project_type: str
    pain_points: str
    systems_touched: str
    revenue_flow_impacted: str
    audit_critical: str


class CharterResponse(BaseModel):
    charter_markdown: str


# ---------- Health ----------
@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Raw AI scoring endpoint ----------
@app.post("/ai/score_project", response_model=ScoreResponse)
def ai_score_project(req: ScoreRequest):
    result = score_project_ai(req.description, req.systems)
    return ScoreResponse(**result)


# ---------- Score a known project from projects.csv ----------
@app.post("/ai/score_project_by_id", response_model=ScoreResponse)
def ai_score_project_by_id(req: ProjectScoreRequest):
    if not PROJECTS_PATH.exists():
        raise HTTPException(status_code=500, detail=f"{PROJECTS_PATH} not found")

    df = pd.read_csv(PROJECTS_PATH)

    row = df[df["id"] == req.project_id]
    if row.empty:
        raise HTTPException(status_code=404, detail="Project not found")

    project = row.iloc[0]

    description = req.description_override or str(project.get("pain_points", ""))
    systems = req.systems_override or str(project.get("systems_touched", ""))

    result = score_project_ai(description, systems)
    return ScoreResponse(**result)


# ---------- Project charter generation ----------
@app.post("/ai/project_charter", response_model=CharterResponse)
def ai_project_charter(req: CharterRequest):
    charter = generate_project_charter_ai(
        name=req.name,
        project_type=req.project_type,
        pain_points=req.pain_points,
        systems_touched=req.systems_touched,
        revenue_flow_impacted=req.revenue_flow_impacted,
        audit_critical=req.audit_critical,
    )
    return CharterResponse(charter_markdown=charter)
