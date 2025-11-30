import pandas as pd
import streamlit as st
import requests

# ✅ Cloudflare Pages APIs
BACKLOG_API = "https://revenue-intake-app.pages.dev/api/backlog"
STATUS_API = "https://revenue-intake-app.pages.dev/api/update_status"

# ✅ Your FastAPI backend for scoring + charter
API_BASE = "http://localhost:8000"

# ✅ Jira browse base – update this to your real Jira URL
JIRA_BROWSE_BASE = "https://selvera24.atlassian.net/browse/"  # <-- change me


st.set_page_config(
    page_title="Revenue Project Copilot",
    layout="wide",
    page_icon="📋",
)


def _word_count(text: str) -> int:
    if not text:
        return 0
    return len(str(text).split())


def compute_readiness_components(row: pd.Series):
    """
    Compute component scores and overall readiness.
    All scores are 0.0–1.0.
    Components:
      - requirements_clarity
      - outcomes_defined
      - system_data_scope
      - risk_alignment
    """
    # ----- Requirements Clarity -----
    problem = str(row.get("problem_statement", "") or "")
    required_changes = str(row.get("required_changes", "") or "")

    problem_wc = _word_count(problem)
    changes_wc = _word_count(required_changes)

    # 30 words for problem → full credit, scaled otherwise
    problem_score = min(problem_wc / 30.0, 1.0)
    # 20 words for required changes → full credit; if blank, 0
    changes_score = 0.0 if not required_changes.strip() else min(changes_wc / 20.0, 1.0)

    requirements_clarity = 0.6 * problem_score + 0.4 * changes_score

    # ----- Outcomes Defined -----
    expected = str(row.get("expected_outcome", "") or "")
    expected_wc = _word_count(expected)
    outcomes_defined = min(expected_wc / 20.0, 1.0)

    # ----- System / Data Scope -----
    systems = str(row.get("systems_touched", "") or "")
    data_objects = str(row.get("data_objects", "") or "")
    dependencies = str(row.get("downstream_dependencies", "") or "")

    systems_score = 1.0 if systems.strip() else 0.0
    data_score = 1.0 if data_objects.strip() else 0.0
    deps_score = 0.7 if dependencies.strip() else 0.0  # partial credit if present

    system_data_scope = (systems_score + data_score + deps_score) / 3.0

    # ----- Risk / Compliance Alignment -----
    audit_risk = str(row.get("audit_risk", "") or "").lower()
    control_impact = str(row.get("control_impact", "") or "")

    # If there is audit risk at all, we assume more attention; but the
    # alignment score measures whether control_impact has been defined.
    base = 1.0 if audit_risk in ("high", "medium") else 0.5
    control_score = 1.0 if control_impact.strip() else 0.0

    risk_alignment = 0.5 * base + 0.5 * control_score

    # ----- Weighted Readiness -----
    readiness = (
        0.35 * requirements_clarity
        + 0.25 * outcomes_defined
        + 0.25 * system_data_scope
        + 0.15 * risk_alignment
    )
    readiness = max(0.0, min(1.0, readiness))

    return {
        "requirements_clarity": requirements_clarity,
        "outcomes_defined": outcomes_defined,
        "system_data_scope": system_data_scope,
        "risk_alignment": risk_alignment,
        "readiness": readiness,
    }


def is_high_risk_high_revenue(row: pd.Series) -> bool:
    revenue_impact = str(row.get("revenue_impact", "") or "").lower()
    audit_risk = str(row.get("audit_risk", "") or "").lower()
    return (revenue_impact == "high") or (audit_risk == "high")


def get_missing_critical_fields(row: pd.Series):
    """
    For high-risk / high-revenue, these must be present before promotion:
      - Problem Statement
      - Expected Outcome
      - Systems Touched
      - Data Objects
      - Downstream Dependencies
      - Control Impact
      - Triage Owner
    """
    missing = []

    if not str(row.get("problem_statement", "") or "").strip():
        missing.append("Problem Statement")

    if not str(row.get("expected_outcome", "") or "").strip():
        missing.append("Expected Outcome")

    if not str(row.get("systems_touched", "") or "").strip():
        missing.append("Systems Touched")

    if not str(row.get("data_objects", "") or "").strip():
        missing.append("Data Objects")

    if not str(row.get("downstream_dependencies", "") or "").strip():
        missing.append("Downstream Dependencies")

    if not str(row.get("control_impact", "") or "").strip():
        missing.append("Control Impact")

    if not str(row.get("triage_owner", "") or "").strip():
        missing.append("Triage Owner")

    return missing


@st.cache_data
def load_projects() -> pd.DataFrame:
    """
    Load projects from Cloudflare D1 via Pages JSON API.
    Expects { "projects": [ ... ] } from /api/backlog.
    Also computes readiness_score per project.
    """
    resp = requests.get(BACKLOG_API, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    projects = data.get("projects", [])
    df = pd.DataFrame(projects)

    if df.empty:
        return df

    # Normalize audit_critical to string
    if "audit_critical" in df.columns:
        df["audit_critical"] = df["audit_critical"].astype(str)

    # Numeric columns if present
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

    # Compute readiness_score
    readiness_scores = []
    for _, row in df.iterrows():
        comp = compute_readiness_components(row)
        readiness_scores.append(comp["readiness"])

    df["readiness_score"] = readiness_scores  # 0.0–1.0

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


def update_status(intake_id: str, new_status: str, triage_owner: str, triage_notes: str):
    """
    Call Cloudflare Pages API to update status + triage for a given intake id.
    Jira comment trail is handled in the Pages function.
    """
    url = STATUS_API
    payload = {
        "id": intake_id,
        "status": new_status,
        "triage_owner": triage_owner,
        "triage_notes": triage_notes,
    }
    resp = requests.put(url, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------
# Load data
# ---------------------------
df = load_projects()

st.title("📋 Revenue Transformation Backlog")

# ---------------------------
# Sidebar Filters
# ---------------------------
with st.sidebar:
    st.header("Filters")

    if df.empty:
        type_options = ["All"]
        flow_options = ["All"]
    else:
        type_options = ["All"] + sorted(df["type"].dropna().unique().tolist())
        flow_options = ["All"] + sorted(
            df["revenue_flow_impacted"].dropna().unique().tolist()
        )

    selected_type = st.selectbox("Project Type", type_options, index=0)
    selected_flow = st.selectbox("Revenue Flow Impacted", flow_options, index=0)

    audit_options = ["All", "Yes", "No"]
    selected_audit = st.selectbox("Audit Critical?", audit_options, index=0)

# Apply filters
filtered = df.copy()

if not filtered.empty:
    if selected_type != "All":
        filtered = filtered[filtered["type"] == selected_type]

    if selected_flow != "All":
        filtered = filtered[filtered["revenue_flow_impacted"] == selected_flow]

    if selected_audit != "All":
        filtered = filtered[filtered["audit_critical"].astype(str) == selected_audit]

    # Sort by readiness_score first, then priority_score
    if "readiness_score" in filtered.columns:
        filtered = filtered.sort_values(
            ["readiness_score", "priority_score"],
            ascending=[False, False],
        )

st.subheader(f"Backlog ({len(filtered)} of {len(df)} projects)")
if filtered.empty:
    st.info("No projects found. Check your D1 data or filters.")
else:
    # Include readiness + triage_owner in the table
    cols_to_show = [
        "id",
        "name",
        "source",
        "type",
        "status",
        "revenue_flow_impacted",
        "audit_critical",
        "priority_score",
        "readiness_score",
        "triage_owner",
        "systems_touched",
        "pain_points",
    ]
    if "jira_key" in filtered.columns:
        cols_to_show.insert(5, "jira_key")

    available_cols = [c for c in cols_to_show if c in filtered.columns]

    # Show readiness as 0–100 with rounding
    if "readiness_score" in filtered.columns:
        filtered_display = filtered.copy()
        filtered_display["readiness_score"] = (
            filtered_display["readiness_score"] * 100
        ).round(0)
    else:
        filtered_display = filtered

    st.dataframe(
        filtered_display[available_cols],
        use_container_width=True,
    )

st.markdown("---")
st.subheader("🔍 Project Detail & AI Insights")

if filtered.empty:
    st.info("No projects match the current filters.")
else:
    project_names = filtered["name"].tolist()
    selected_project_name = st.selectbox("Select a project", project_names)

    project = filtered[filtered["name"] == selected_project_name].iloc[0]

    # Compute readiness components for the selected project
    comp = compute_readiness_components(project)
    readiness_score = comp["readiness"]  # 0–1
    readiness_pct = round(readiness_score * 100)

    high_risk_high_rev = is_high_risk_high_revenue(project)

    col_left, col_right = st.columns([2, 1])

    # ---------- Left: Detail ----------
    with col_left:
        st.markdown(f"### {project['name']}")

        meta_cols = st.columns(5)
        meta_cols[0].metric("Type", project.get("type", ""))
        meta_cols[1].metric("Source", project.get("source", ""))
        meta_cols[2].metric("Status", project.get("status", ""))
        meta_cols[3].metric("Readiness", f"{readiness_pct}%")

        risk_label = "High-Risk / High-Revenue" if high_risk_high_rev else "Standard"
        meta_cols[4].metric("Risk Tier", risk_label)

        jira_key = project.get("jira_key", None)
        if jira_key:
            jira_url = f"{JIRA_BROWSE_BASE}{jira_key}"
            st.markdown(f"**Jira:** [{jira_key}]({jira_url})")
        else:
            st.markdown("**Jira:** –")

        st.markdown(
            "**Revenue Flow Impacted:** "
            + str(project.get("revenue_flow_impacted", ""))
        )
        st.markdown("**Audit Critical:** " + str(project.get("audit_critical", "")))

        st.markdown("**Systems Touched:**")
        st.code(str(project.get("systems_touched", "")), language="text")

        st.markdown("**Pain Points / Context:**")
        st.write(str(project.get("pain_points", "")))

        st.markdown("#### Current Scores (Human-Set)")
        score_cols = st.columns(6)
        score_cols[0].metric("BI", project.get("bi", None))
        score_cols[1].metric("Risk", project.get("risk", None))
        score_cols[2].metric("Align", project.get("align", None))
        score_cols[3].metric("Urgency", project.get("urgency", None))
        score_cols[4].metric("Cmplx", project.get("complexity", None))
        score_cols[5].metric("Cost", project.get("cost", None))

        st.metric("Priority Score", project.get("priority_score", None))

        st.markdown("#### 🧮 Readiness Breakdown")
        rb1, rb2, rb3, rb4 = st.columns(4)
        rb1.metric("Requirements", f"{round(comp['requirements_clarity']*100)}%")
        rb2.metric("Outcomes", f"{round(comp['outcomes_defined']*100)}%")
        rb3.metric("Systems/Data", f"{round(comp['system_data_scope']*100)}%")
        rb4.metric("Risk Align.", f"{round(comp['risk_alignment']*100)}%")

        st.markdown("#### 📄 Project Charter")

        charter_text = st.session_state.get("charter_text", "")
        charter_project_id = st.session_state.get("charter_project_id", None)

        if charter_text and charter_project_id == project["id"]:
            st.markdown(charter_text)

            st.download_button(
                "⬇️ Download Charter (.md)",
                data=charter_text,
                file_name=f"{str(project['name']).replace(' ', '_')}_charter.md",
                mime="text/markdown",
            )
        else:
            st.info("No charter generated yet for this project.")

        # ---------- Triage fields ----------
        st.markdown("#### 🧩 Triage Fields")

        triage_owner_val = st.text_input(
            "Triage Owner",
            value=str(project.get("triage_owner", "") or ""),
            key=f"triage_owner_{project['id']}",
        )

        triage_notes_val = st.text_area(
            "Triage Notes",
            value=str(project.get("triage_notes", "") or ""),
            key=f"triage_notes_{project['id']}",
        )

        # ---------- Status update controls ----------
        st.markdown("#### 🔄 Update Status")

        allowed_statuses = [
            "New",
            "Triage Review",
            "Prioritized",
            "Sent to Epic",
            "In Progress",
            "Complete",
            "Blocked",
            "Cancelled",
        ]

        current_status = str(project.get("status", "New"))
        new_status = st.selectbox(
            "Set new status",
            allowed_statuses,
            index=allowed_statuses.index(current_status)
            if current_status in allowed_statuses
            else 0,
            key=f"status_select_{project['id']}",
        )

        # Statuses that count as "promotion" into more committed phases
        promotion_statuses = {"Prioritized", "Sent to Epic", "In Progress"}

        if st.button("Save Status & Triage", key=f"save_status_{project['id']}"):
            # Hard gate for high-risk / high-revenue when promoting
            is_promotion = (new_status in promotion_statuses) and (
                new_status != current_status
            )
            missing_critical = get_missing_critical_fields(
                {**project.to_dict(), "triage_owner": triage_owner_val}
            )

            if high_risk_high_rev and is_promotion:
                # Require readiness >= 0.8 and no missing critical fields
                if readiness_score < 0.8 or missing_critical:
                    msg_lines = [
                        f"High-Risk / High-Revenue project is below readiness threshold for promotion to '{new_status}'.",
                        f"Current Readiness: {readiness_pct}%. Required: at least 80%.",
                    ]
                    if missing_critical:
                        msg_lines.append("")
                        msg_lines.append("Missing required fields:")
                        for f in missing_critical:
                            msg_lines.append(f"• {f}")
                    st.error("\n".join(msg_lines))
                else:
                    # Allowed to update
                    try:
                        update_status(
                            str(project["id"]),
                            new_status,
                            triage_owner_val,
                            triage_notes_val,
                        )
                        st.success(f"Status updated to {new_status}")
                        load_projects.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to update status/triage: {e}")
            else:
                # Soft gate for lower-risk items: warn but allow
                warning_shown = False
                if readiness_score < 0.6 or missing_critical:
                    msg_lines = [
                        f"Project is below ideal readiness for status '{new_status}'.",
                        f"Current Readiness: {readiness_pct}%. Recommended: at least 60%.",
                    ]
                    if missing_critical:
                        msg_lines.append("")
                        msg_lines.append("Missing recommended fields:")
                        for f in missing_critical:
                            msg_lines.append(f"• {f}")
                    st.warning("\n".join(msg_lines))
                    warning_shown = True

                try:
                    update_status(
                        str(project["id"]),
                        new_status,
                        triage_owner_val,
                        triage_notes_val,
                    )
                    if warning_shown:
                        st.info("Status updated despite readiness warnings.")
                    else:
                        st.success(f"Status updated to {new_status}")
                    load_projects.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to update status/triage: {e}")

    # ---------- Right: AI Insights & Charter Trigger ----------
    with col_right:
        st.markdown("#### 🤖 AI Score Suggestion")

        if st.button("✨ Generate AI Suggestion"):
            with st.spinner("Calling Copilot API (scoring)..."):
                try:
                    ai_result = call_ai_scoring(
                        description=str(project.get("pain_points", "")),
                        systems=str(project.get("systems_touched", "")),
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
                        "Note: This does not overwrite your D1 data yet — "
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
                        name=str(project.get("name", "")),
                        project_type=str(project.get("type", "")),
                        pain_points=str(project.get("pain_points", "")),
                        systems_touched=str(project.get("systems_touched", "")),
                        revenue_flow_impacted=str(
                            project.get("revenue_flow_impacted", "")
                        ),
                        audit_critical=str(project.get("audit_critical", "")),
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

# ---------------------------
# Steering Committee View
# ---------------------------
st.markdown("---")
st.subheader("🏛 Steering Committee View")

if df.empty:
    st.info("No projects available.")
else:
    steering_statuses = ["Prioritized", "Sent to Epic", "In Progress"]
    steering_df = df[df["status"].isin(steering_statuses)].copy()

    if steering_df.empty:
        st.info("No projects in Prioritized / Sent to Epic / In Progress yet.")
    else:
        cols = [
            "name",
            "source",
            "status",
            "priority_score",
            "readiness_score",
            "triage_owner",
            "jira_key",
            "revenue_flow_impacted",
            "audit_critical",
        ]
        existing_cols = [c for c in cols if c in steering_df.columns]
        steering_display = steering_df.copy()
        if "readiness_score" in steering_display.columns:
            steering_display["readiness_score"] = (
                steering_display["readiness_score"] * 100
            ).round(0)

        st.dataframe(steering_display[existing_cols], use_container_width=True)
