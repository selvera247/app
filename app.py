import streamlit as st
import pandas as pd

st.set_page_config(page_title="Revenue Project Copilot — Backlog", layout="wide")

@st.cache_data
def load_projects(path: str = "projects.csv") -> pd.DataFrame:
    df = pd.read_csv(path)
    # Ensure correct dtypes
    df["audit_critical"] = df["audit_critical"].astype(str)
    df["priority_score"] = pd.to_numeric(df["priority_score"], errors="coerce")
    return df

df = load_projects()

st.title("📋 Revenue Transformation Backlog")

# --- Filters ---
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
