"""
Page 3: Case Investigation Explorer
Deep-Dive into Customer Case Dossiers, Identity Graphs, and Audit Steps
"""

from __future__ import annotations

import sys
import importlib
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from frontend.services.backend_adapter import backend_adapter
if "frontend.services.backend_adapter" in sys.modules:
    ba_mod = sys.modules["frontend.services.backend_adapter"]
    if isinstance(ba_mod, type(sys)):
        importlib.reload(ba_mod)
        from frontend.services.backend_adapter import backend_adapter

import pandas as pd
import streamlit as st
from frontend.components.metrics_cards import render_status_badge
from frontend.components.timeline import render_step_timeline
from frontend.services.terminal_logger import log_to_terminal

st.set_page_config(page_title="Case Explorer | NORTHSTAR", page_icon="🔍", layout="wide")

st.markdown("## 🔍 **Case Investigation Explorer**")
st.caption("Inspect individual case dossiers, user intent, historical identity resolution graphs, and step-by-step remediation plans.")

# Fetch all cases
results = backend_adapter.get_audit_results()
if not results:
    st.warning("⚠️ No audit results loaded. Please run an audit in the **Interactive Audit Runner** first.")
    st.stop()

case_ids = [r["case_id"] for r in results]

# Selection controls
col_sel1, col_sel2 = st.columns([1, 2])
with col_sel1:
    selected_case_id = st.selectbox(
        "Select Case ID to Inspect:",
        options=case_ids,
        index=case_ids.index("case_37") if "case_37" in case_ids else 0,
    )
with col_sel2:
    st.write("")
    st.write("")
    st.caption(f"Total available cases in current output: **{len(case_ids)}**")

# Retrieve case details via backend adapter
case = backend_adapter.get_case_details(selected_case_id)
if not case:
    st.error(f"Could not load details for case {selected_case_id}")
    st.stop()

if "last_logged_case" not in st.session_state or st.session_state.last_logged_case != selected_case_id:
    st.session_state.last_logged_case = selected_case_id
    log_to_terminal(
        f"USER INSPECTING CASE IN UI: {case.case_id}",
        f"  Customer Email : {case.request_email}\n  Request Text   : \"{case.request_text}\"\n  Resolved ID    : {case.user_id} ({case.user_name})\n  Audit Verdict  : {case.deletion_status} ({len(case.steps)} steps generated)",
    )

st.markdown("---")

# Header Dossier
badge_html = render_status_badge(case.deletion_status)
reported_badge = render_status_badge(case.reported_status)

st.markdown(
    f"""
    <div style="background-color: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 18px; margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <h3 style="margin: 0; font-family: monospace;">📁 Case ID: {case.case_id}</h3>
            <div>
                <strong>Audit Verdict:</strong> {badge_html} &nbsp;&nbsp;|&nbsp;&nbsp;
                <strong>Reported Claim:</strong> {reported_badge}
            </div>
        </div>
        <div style="background-color: rgba(0, 0, 0, 0.25); border-left: 3px solid #64b5f6; padding: 10px 14px; border-radius: 4px; margin-bottom: 12px;">
            <div style="font-size: 0.85rem; color: #90caf9; margin-bottom: 2px;">💬 <strong>Customer Request Text:</strong></div>
            <div style="font-style: italic; font-size: 0.95rem;">"{case.request_text}"</div>
        </div>
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; font-size: 0.88rem; color: #cfd8dc;">
            <div>📧 <strong>Email:</strong> <code>{case.request_email}</code></div>
            <div>⏰ <strong>Requested:</strong> {case.requested_at}</div>
            <div>📋 <strong>Reported At:</strong> {case.reported_at}</div>
            <div>🔒 <strong>Audit Cutoff:</strong> {case.audit_at}</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Tabs: Identity Resolution Graph vs. Audit Steps vs. Raw Data
tab_steps, tab_identity, tab_raw = st.tabs(["🪜 Audit & Remediation Steps", "👤 Identity Resolution Graph", "📄 Raw Step JSON"])

with tab_steps:
    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
    col_stat1.metric("Total Steps", len(case.steps))
    col_stat2.metric("Residual Findings", case.findings_count)
    col_stat3.metric("Remediation Proposed", case.remediation_count)
    col_stat4.metric("Verification Steps", case.verification_count)

    st.write("")
    render_step_timeline(case.steps)

with tab_identity:
    st.markdown("#### 👤 **Current vs. Historical Identity Graph**")
    st.caption("Demonstrating how Northstar resolves identity drift across historical audit logs to find residual ghost data.")

    col_id1, col_id2 = st.columns(2)
    with col_id1:
        st.markdown(
            f"""
            <div style="background-color: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 14px;">
                <h5 style="color: #64b5f6; margin-top: 0;">Current Identity Snapshot</h5>
                <ul style="list-style: none; padding-left: 0; font-size: 0.9rem; line-height: 1.8;">
                    <li>🆔 <strong>User ID:</strong> <code>{case.user_id or 'Not in snapshot'}</code></li>
                    <li>👤 <strong>Name:</strong> {case.user_name or 'Unknown'}</li>
                    <li>📧 <strong>Primary Email:</strong> <code>{case.request_email}</code></li>
                    <li>📱 <strong>Phone:</strong> <code>{case.current_phone or 'Unknown'}</code></li>
                    <li>🔑 <strong>Email Hash:</strong> <code>{case.email_hash or 'None'}</code></li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_id2:
        st.markdown(
            f"""
            <div style="background-color: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 14px;">
                <h5 style="color: #81c784; margin-top: 0;">Expanded Alias Graph</h5>
                <p style="font-size: 0.88rem; color: #b0bec5; margin-bottom: 8px;">
                    All identifiers tracked across legacy systems:
                </p>
                <div style="font-size: 0.88rem;">
                    <strong>All Known Emails:</strong><br>
                    {'<br>'.join(f'• <code>{e}</code>' for e in case.all_emails) if case.all_emails else 'None'}
                </div>
                <div style="font-size: 0.88rem; margin-top: 8px;">
                    <strong>All Known Phones:</strong><br>
                    {'<br>'.join(f'• <code>{p}</code>' for p in case.all_phones) if case.all_phones else 'None'}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")
    st.markdown("##### 📜 **Historical Identity Audit Trail (`user_audit_log.csv`)**")
    if case.identity_audit_trail:
        st.dataframe(pd.DataFrame(case.identity_audit_trail), use_container_width=True, hide_index=True)
    else:
        st.info("ℹ️ No historical identity modifications recorded for this user ID prior to audit cutoff.")

with tab_raw:
    st.markdown("#### 📄 **Official Submission JSON Representation**")
    raw_step_dicts = [s.__dict__ for s in case.steps]
    st.json(raw_step_dicts)
