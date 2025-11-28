import pandas as pd
import streamlit as st
import requests

API_BASE = "http://localhost:8000"  # FastAPI backend


st.set_page_config(
    page_title="Revenue Project Copilot",
    layout="wide",
    page_icon="📋",
)


@st.cache_data
def load_projects(path: str = "projects.csv") -> pd.DataFrame:
    df = pd.read_csv(path)

    # Normalize types
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


def call_ai_scoring(description: str, systems: str):
    """
    Call FastAPI backend /ai/score_project
    """
    url = f"{API_BASE}/ai/score_project"
    payload = {"description": description, "systems": systems}
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def call_project_charter(
    name: str,
    project_type: str,
    pain_points: str,
    systems_touched: str,
    revenue_flow_impacted: str,
    audit_critical: str,
):
    """
    Call FastAPI backend /ai/project_charter
    """
    url = f"{API_BASE}/ai/project_charter"
    payload = {
        "name": name,
        "project_type": project_type,
        "pain_points": pain_points,
        "systems_touched": systems_touched,
        "revenue_flow_impacted": revenue_flow_impacted,
        "audit_critical": audit_critical,
    }
    resp = requests.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()


# ---------------------------
# Load data
# ---------------------------
df = load_projects()

st.title("Revenue Transformation Backlog")

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

# Sort by priority_score desc
filtered = filtered.sort_values("priority_score", ascending=False)

st.subheader(f"Backlog ({len(filtered)} of {len(df)} projects)")
st.dataframe(
    filtered[
        [
            "id",
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

st.markdown("---")
st.subheader("Project Detail & AI Insights")

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

        st.markdown("#### Current Scores (Human-Set)")
        score_cols = st.columns(6)
        score_cols[0].metric("BI", project.get("bi", None))
        score_cols[1].metric("Risk", project.get("risk", None))
        score_cols[2].metric("Align", project.get("align", None))
        score_cols[3].metric("Urgency", project.get("urgency", None))
        score_cols[4].metric("Cmplx", project.get("complexity", None))
        score_cols[5].metric("Cost", project.get("cost", None))

        st.metric("Priority Score", project.get("priority_score", None))

        # Project Charter display area
        st.markdown("#### 📄 Project Charter")

        charter_text = st.session_state.get("charter_text", "")
        charter_project_id = st.session_state.get("charter_project_id", None)

        if charter_text and charter_project_id == project["id"]:
            st.markdown(charter_text)

            # Download as .md
            st.download_button(
                "⬇️ Download Charter (.md)",
                data=charter_text,
                file_name=f"{str(project['name']).replace(' ', '_')}_charter.md",
                mime="text/markdown",
            )
        else:
            st.info("No charter generated yet for this project.")

    # ---------- Right: AI Insights & Charter Trigger ----------
    with col_right:
        st.markdown("#### 🤖 AI Score Suggestion")

        if st.button("✨ Generate AI Suggestion"):
            with st.spinner("Calling Copilot API (scoring)..."):
                try:
                    ai_result = call_ai_scoring(
                        description=str(project["pain_points"]),
                        systems=str(project["systems_touched"]),
                    )

                    ai_bi = ai_result["bi"]
                    ai_risk = ai_result["risk"]
                    ai_align = ai_result["align"]
                    ai_urgency = ai_result["urgency"]
                    ai_cmplx = ai_result["complexity"]
                    ai_cost = ai_result["cost"]
                    ai_priority = ai_result["priority_score"]

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

        st.markdown("---")
        st.markdown("#### 📄 Project Charter Creation")

        if st.button("📄 Generate Project Charter"):
            with st.spinner("Calling Copilot API (charter)..."):
                try:
                    charter_resp = call_project_charter(
                        name=str(project["name"]),
                        project_type=str(project["type"]),
                        pain_points=str(project["pain_points"]),
                        systems_touched=str(project["systems_touched"]),
                        revenue_flow_impacted=str(project["revenue_flow_impacted"]),
                        audit_critical=str(project["audit_critical"]),
                    )
                    charter_md = charter_resp.get("charter_markdown", "")
                    if charter_md:
                        st.session_state["charter_text"] = charter_md
                        st.session_state["charter_project_id"] = project["id"]
                        st.success("Project charter generated and shown on the left.")

                        st.markdown("##### Preview")
                        st.markdown(charter_md)
                    else:
                        st.warning("No charter content returned.")

                except Exception as e:
                    st.error(f"Project charter generation failed: {e}")
