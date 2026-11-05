"""
Page 1: Overview Dashboard
Executive Visualizations and Performance Metrics
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st
from frontend.components.metrics_cards import render_kpi_row, render_status_badge
from frontend.services.backend_adapter import backend_adapter

st.set_page_config(page_title="Overview Dashboard | NORTHSTAR", page_icon="📊", layout="wide")

st.markdown("## 📊 **Executive Overview Dashboard**")
st.caption("High-level audit telemetry, compliance rates, and residual risk distribution across systems.")

results = backend_adapter.get_audit_results()

if not results:
    st.warning("⚠️ No audit results found in output.csv. Please run an audit in the **Interactive Audit Runner** first!")
    st.stop()

# Compute aggregates
total_cases = len(results)
status_counts = Counter(r["deletion_status"] for r in results)
complete_count = status_counts.get("COMPLETE", 0)
incomplete_count = status_counts.get("INCOMPLETE", 0)
na_count = status_counts.get("NOT_APPLICABLE", 0)
total_steps = sum(r["step_count"] for r in results)

# Render KPI cards
render_kpi_row(total_cases, complete_count, incomplete_count, na_count, total_steps)

st.markdown("---")

# Visual Charts
col_chart1, col_chart2 = st.columns([1, 1])

with col_chart1:
    st.markdown("##### 🎯 **Deletion Status Distribution**")
    status_df = pd.DataFrame([
        {"Status": "COMPLETE (Compliant)", "Count": complete_count, "Color": "#4caf50"},
        {"Status": "INCOMPLETE (Ghost Data Found)", "Count": incomplete_count, "Color": "#f44336"},
        {"Status": "NOT_APPLICABLE (Non-Deletion)", "Count": na_count, "Color": "#9e9e9e"},
    ])
    fig_pie = px.pie(
        status_df,
        values="Count",
        names="Status",
        color="Status",
        color_discrete_map={
            "COMPLETE (Compliant)": "#66bb6a",
            "INCOMPLETE (Ghost Data Found)": "#ef5350",
            "NOT_APPLICABLE (Non-Deletion)": "#bdbdbd",
        },
        hole=0.45,
    )
    fig_pie.update_traces(textinfo="value+percent", textfont_size=13)
    fig_pie.update_layout(margin=dict(t=20, b=20, l=10, r=10), height=320)
    st.plotly_chart(fig_pie, use_container_width=True)

with col_chart2:
    st.markdown("##### 🪜 **Audit Steps by Phase Breakdown**")
    phase_counts = Counter()
    system_risk_counts = Counter()
    
    for r in results:
        for s in r.get("steps", []):
            phase_counts[s.get("phase", "UNKNOWN")] += 1
            if s.get("phase") == "FINDING":
                sys_id = s.get("system_id", "unknown_system")
                if sys_id:
                    system_risk_counts[sys_id] += 1

    phase_df = pd.DataFrame([
        {"Phase": "1. FINDING (Residual Data)", "Steps": phase_counts.get("FINDING", 0)},
        {"Phase": "2. REMEDIATION (Action Needed)", "Steps": phase_counts.get("REMEDIATION", 0)},
        {"Phase": "3. VERIFICATION (Proof/Checks)", "Steps": phase_counts.get("VERIFICATION", 0)},
    ])
    fig_bar = px.bar(
        phase_df,
        x="Phase",
        y="Steps",
        color="Phase",
        color_discrete_sequence=["#e57373", "#ffb74d", "#81c784"],
        text="Steps",
    )
    fig_bar.update_layout(showlegend=False, margin=dict(t=20, b=20, l=10, r=10), height=320)
    fig_bar.update_traces(textposition="outside")
    st.plotly_chart(fig_bar, use_container_width=True)

# Secondary Chart: Systems with Most Ghost Data Findings
if system_risk_counts:
    st.markdown("##### 🚨 **Top Systems with Residual Ghost Data Violations**")
    top_sys = system_risk_counts.most_common(8)
    sys_df = pd.DataFrame([{"System ID": k, "Ghost Data Findings": v} for k, v in top_sys])
    fig_sys = px.bar(
        sys_df,
        x="Ghost Data Findings",
        y="System ID",
        orientation="h",
        color="Ghost Data Findings",
        color_continuous_scale="Reds",
        text="Ghost Data Findings",
    )
    fig_sys.update_layout(yaxis=dict(autorange="reversed"), margin=dict(t=10, b=10, l=10, r=10), height=260)
    fig_sys.update_traces(textposition="outside")
    st.plotly_chart(fig_sys, use_container_width=True)

st.markdown("---")

# Filterable Case Browser
st.markdown("### 🔍 **Filter & Browse Audited Cases**")

filter_col1, filter_col2 = st.columns([1, 2])
with filter_col1:
    selected_status = st.selectbox(
        "Filter by Status:",
        options=["ALL", "COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"],
        index=0,
    )
with filter_col2:
    search_query = st.text_input("Search Case ID (e.g. case_001):", value="").strip().lower()

# Filter rows
filtered = []
for r in results:
    if selected_status != "ALL" and r["deletion_status"] != selected_status:
        continue
    if search_query and search_query not in r["case_id"].lower():
        continue
    filtered.append({
        "Case ID": r["case_id"],
        "Verdict": r["deletion_status"],
        "Total Steps": r["step_count"],
        "Has Findings": any(s.get("phase") == "FINDING" for s in r.get("steps", [])),
        "Remediation Required": any(s.get("phase") == "REMEDIATION" for s in r.get("steps", [])),
    })

df_table = pd.DataFrame(filtered)
st.caption(f"Showing **{len(df_table):,}** cases matching filters")

st.dataframe(
    df_table,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Case ID": st.column_config.TextColumn("Case ID", width="medium"),
        "Verdict": st.column_config.TextColumn("Audit Verdict", width="medium"),
        "Total Steps": st.column_config.NumberColumn("Steps Generated", width="small"),
        "Has Findings": st.column_config.CheckboxColumn("Residual Data?", width="small"),
        "Remediation Required": st.column_config.CheckboxColumn("Remediation?", width="small"),
    },
)

st.info("💡 To explore deep-dive details, identity graphs, and step sequences for any case, go to **3_Case_Investigation_Explorer**.")
