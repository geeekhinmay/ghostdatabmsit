"""
Audit Step Timeline Component for NORTHSTAR.
Renders an intuitive, chronological audit trail for a case.
"""

from __future__ import annotations
import streamlit as st
from typing import List, Any
from frontend.components.metrics_cards import render_phase_badge


def render_step_timeline(steps: List[Any]):
    """Render a visual chronological timeline of audit steps."""
    if not steps:
        st.info("ℹ️ No steps generated for this request (Non-Deletion / NOT_APPLICABLE).")
        return

    st.markdown("#### Chronological Audit & Remediation Sequence")
    
    for s in steps:
        step_no = getattr(s, "step_no", 0)
        phase = getattr(s, "phase", "")
        op = getattr(s, "operation", "")
        state = getattr(s, "state", "")
        sys_id = getattr(s, "system_id", "")
        res_id = getattr(s, "resource_id", "")
        evidence_id = getattr(s, "evidence_id", "")

        # Border styling according to phase
        border_color = "#e57373" if phase == "FINDING" else ("#ffb74d" if phase == "REMEDIATION" else "#81c784")
        bg_color = "rgba(229, 115, 115, 0.08)" if phase == "FINDING" else ("rgba(255, 183, 77, 0.08)" if phase == "REMEDIATION" else "rgba(129, 199, 132, 0.08)")

        badge_html = render_phase_badge(phase)
        evidence_html = f'<span style="background-color: #1e3a5f; color: #82b1ff; padding: 2px 6px; border-radius: 4px; font-size: 0.8rem; font-family: monospace;">📁 {evidence_id}</span>' if evidence_id else '<span style="color: #888; font-size: 0.8rem;">(Future step)</span>'

        st.markdown(
            f"""
            <div style="border-left: 4px solid {border_color}; background-color: {bg_color}; padding: 12px 16px; margin-bottom: 10px; border-radius: 0 8px 8px 0;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <div>
                        <span style="font-weight: bold; font-size: 1.05rem; margin-right: 8px;">Step #{step_no}</span>
                        {badge_html}
                    </div>
                    <div>
                        {evidence_html}
                    </div>
                </div>
                <div style="font-family: monospace; font-size: 0.92rem; margin-bottom: 4px;">
                    <strong>Operation:</strong> <span style="color: #64b5f6;">{op}</span> &nbsp;|&nbsp; 
                    <strong>State:</strong> <span style="color: #ffb74d;">{state}</span>
                </div>
                <div style="font-size: 0.88rem; color: #b0bec5;">
                    🏢 <strong>System:</strong> <code>{sys_id or 'all_systems'}</code> &nbsp;|&nbsp; 
                    📦 <strong>Resource:</strong> <code>{res_id or 'all_records'}</code>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
