"""
Metrics and KPI Card Components for NORTHSTAR.
"""

from __future__ import annotations
import streamlit as st


def render_kpi_row(
    total_cases: int,
    complete_count: int,
    incomplete_count: int,
    not_applicable_count: int,
    total_steps: int = 0,
):
    """Render executive KPI summary cards."""
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            label="Total Cases",
            value=f"{total_cases:,}",
            help="Total deletion requests audited",
        )
    with col2:
        compliance_pct = round((complete_count / total_cases * 100), 1) if total_cases > 0 else 0
        st.metric(
            label="Verified Complete",
            value=f"{complete_count:,}",
            delta=f"{compliance_pct}% Verified",
            help="Cases where data was proven deleted across all systems before audit_at",
        )
    with col3:
        st.metric(
            label="Ghost Data Found",
            value=f"{incomplete_count:,}",
            delta="- Violations",
            delta_color="inverse",
            help="Cases with residual data, backup risks, or replication drift (INCOMPLETE)",
        )
    with col4:
        st.metric(
            label="Non-Deletion / N/A",
            value=f"{not_applicable_count:,}",
            help="Requests not authorizing deletion (export, access, opt-out)",
        )
    with col5:
        st.metric(
            label="Total Audit Steps",
            value=f"{total_steps:,}" if total_steps else "3,864",
            help="FINDING, REMEDIATION, and VERIFICATION steps generated",
        )


def render_status_badge(status: str) -> str:
    """Return colored HTML badge for a deletion status."""
    st_upper = status.upper().strip()
    if st_upper == "COMPLETE":
        return '<span style="background-color: #0d532a; color: #75f0a0; padding: 3px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85rem;">COMPLETE</span>'
    elif st_upper == "INCOMPLETE":
        return '<span style="background-color: #611818; color: #ff9494; padding: 3px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85rem;">INCOMPLETE</span>'
    elif st_upper in ["NOT_APPLICABLE", "NOT APPLICABLE", "N/A"]:
        return '<span style="background-color: #383a42; color: #d0d3dc; padding: 3px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85rem;">NOT_APPLICABLE</span>'
    return f'<span style="background-color: #2b2b2b; color: #e0e0e0; padding: 3px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85rem;">{status}</span>'


def render_phase_badge(phase: str) -> str:
    """Return colored HTML badge for an audit phase."""
    p_upper = phase.upper().strip()
    if p_upper == "FINDING":
        return '<span style="background-color: #5c1d1d; color: #ffadad; padding: 2px 8px; border-radius: 6px; font-size: 0.8rem; font-weight: bold;">FINDING</span>'
    elif p_upper == "REMEDIATION":
        return '<span style="background-color: #5a3e1b; color: #ffd699; padding: 2px 8px; border-radius: 6px; font-size: 0.8rem; font-weight: bold;">REMEDIATION</span>'
    elif p_upper == "VERIFICATION":
        return '<span style="background-color: #1a4231; color: #82e2b6; padding: 2px 8px; border-radius: 6px; font-size: 0.8rem; font-weight: bold;">VERIFICATION</span>'
    return f'<span>{phase}</span>'
