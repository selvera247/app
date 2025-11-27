import os
import json
from datetime import datetime

import streamlit as st
import pandas as pd
from openai import OpenAI

# ---------------------------
# Config
# ---------------------------
st.set_page_config(
    page_title="Revenue Project Copilot",
    layout="wide",
    page_icon="📋",
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ---------------------------
# Data Loading
# ---------------------------
@st.cache_data
def load_projects(path: str = "projects.csv") -> pd.DataFrame:
    df = pd.read_csv(path)

    # Normalize dtypes
    if "audit_critical" in df.columns:
        df["audit_critical"] = df["audit_critical"].astype(str)

    numeric_cols = [
        "bi",
        "risk",
        "align",
        "urgency",
        "complexity",
        "cost",
        "priority_score",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


df = load_projects()

st.title("📋 Revenue Transformation Backlog")

# ---------------------------
# Sidebar Filters
# ---------------------------
with st.sidebar:
    st.header("Filters")

    type_options = ["All"] + sorted(df["type"].dropna().unique().tolist())
    selected_type = st.selectbox("Project Type", type_options, index=0)

    flow_options = ["All"] + sorted(df["revenue_flow_impacted"].dropna().unique().tolist())
    selected_flow = st.selectbox("Revenue Flow Impacted", flow_options, index=0)

    audit_options = ["All", "Yes", "No"]
    selected_audit = st.selectbox("Audit Critical?", audit_options, index=0)

# Apply filters
filtered = df.copy()

if selected_type != "All":
    filtered = filtered[filtered["type"] == selected_type]

if selected_flow != "All":
    filtered = filtered[filtered["revenue_flow_impacted"] == selected_flow]

if selected_audit != "All":
    filtered = filtered[filtered["audit_critical"].astype(str) == selected_audit]

filtered = filtered.sort_values("priority_score", ascending=False)

st.subheader(f"Backlog ({len(filtered)} of {len(df)} projects)")
st.dataframe(
    filtered[
        [
            "name",
            "source",
            "type",
            "status",
            "revenue_flow_impacted",
            "audit_critical",
            "priority_score",
            "systems_touched",
            "pain_points",
        ]
    ],
    use_container_width=True,
)

# ---------------------------
# Project Detail Selection
# ---------------------------
st.markdown("---")
st.subheader("🔍 Project Detail & AI Insights")

if filtered.empty:
    st.info("No projects match the current filters.")
else:
    project_names = filtered["name"].tolist()
    selected_project_name = st.selectbox("Select a project", project_names)

    project = filtered[filtered["name"] == selected_project_name].iloc[0]

    col_left, col_right = st.columns([2, 1])

    # ---------- Left: Detail ----------
    with col_left:
        st.markdown(f"### {project['name']}")

        meta_cols = st.columns(3)
        meta_cols[0].metric("Type", project["type"])
        meta_cols[1].metric("Source", project["source"])
        meta_cols[2].metric("Status", project["status"])

        st.markdown("**Revenue Flow Impacted:** " + str(project["revenue_flow_impacted"]))
        st.markdown("**Audit Critical:** " + str(project["audit_critical"]))

        st.markdown("**Systems Touched:**")
        st.code(str(project["systems_touched"]), language="text")

        st.markdown("**Pain Points:**")
        st.write(str(project["pain_points"]))

        # Existing scores
        st.markdown("#### Current Scores (Human-Set)")
        score_cols = st.columns(6)
        score_cols[0].metric("BI", project.get("bi", None))
        score_cols[1].metric("Risk", project.get("risk", None))
        score_cols[2].metric("Align", project.get("align", None))
        score_cols[3].metric("Urgency", project.get("urgency", None))
        score_cols[4].metric("Cmplx", project.get("complexity", None))
        score_cols[5].metric("Cost", project.get("cost", None))

        st.metric("Priority Score", project.get("priority_score", None))

    # ---------- Right: AI Insights ----------
    with col_right:
        st.markdown("#### 🤖 AI Score Suggestion")

        if OPENAI_API_KEY is None:
            st.warning(
                "Set OPENAI_API_KEY in your environment to enable AI scoring."
            )
        else:
            client = OpenAI(api_key=OPENAI_API_KEY)

            def score_project_ai(description: str, systems: str) -> dict:
                """
                Call OpenAI to suggest scores + rationale.
                Returns a Python dict.
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
"""

                completion = client.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                )

                content = completion.choices[0].message.content
                return json.loads(content)

            if st.button("✨ Generate AI Suggestion"):
                with st.spinner("Thinking..."):
                    try:
                        ai_result = score_project_ai(
                            description=str(project["pain_points"]),
                            systems=str(project["systems_touched"]),
                        )

                        # Extract scores safely
                        ai_bi = int(ai_result.get("bi", 0))
                        ai_risk = int(ai_result.get("risk", 0))
                        ai_align = int(ai_result.get("align", 0))
                        ai_urgency = int(ai_result.get("urgency", 0))
                        ai_cmplx = int(ai_result.get("complexity", 0))
                        ai_cost = int(ai_result.get("cost", 0))

                        # Compute AI-based priority
                        ai_priority = (
                            ai_bi
                            + ai_risk
                            + ai_align
                            + ai_urgency
                            + (6 - ai_cmplx)
                            + (6 - ai_cost)
                        )

                        st.markdown("##### Suggested Scores")
                        scols = st.columns(6)
                        sc_map = [
                            ("BI", ai_bi),
                            ("Risk", ai_risk),
                            ("Align", ai_align),
                            ("Urgency", ai_urgency),
                            ("Cmplx", ai_cmplx),
                            ("Cost", ai_cost),
                        ]
                        for col, (label, value) in zip(scols, sc_map):
                            col.metric(label, value)

                        st.metric("AI Priority (computed)", ai_priority)

                        st.markdown("##### Rationale")
                        st.write(ai_result.get("rationale", ""))

                        lenses = ai_result.get("lenses", [])
                        if lenses:
                            st.markdown("##### Lenses")
                            st.write(", ".join(lenses))

                        st.caption(
                            "Note: This does not overwrite your CSV yet — "
                            "it’s a decision-support suggestion."
                        )

                    except Exception as e:
                        st.error(f"AI scoring failed: {e}")