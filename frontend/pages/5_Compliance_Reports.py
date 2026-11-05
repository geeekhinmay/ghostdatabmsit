"""
Page 5: Compliance & Evaluation Reports
Official Hackathon Audit Reports, Token Analysis, and Schema Verification
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from frontend.services.backend_adapter import backend_adapter

st.set_page_config(page_title="Compliance Reports | NORTHSTAR", page_icon="📋", layout="wide")

st.markdown("## 📋 **Compliance & Evaluation Reports**")
st.caption("Official hackathon evaluation benchmarks, accuracy metrics, token usage analysis, and output CSV verification.")

# Tabs: Evaluation Report vs Usage Report vs Output Verification
tab_eval, tab_usage, tab_val = st.tabs(["📊 Evaluation Report", "💰 Token & Cost Analysis", "🛡️ Output CSV Validator"])

with tab_eval:
    st.markdown("### 🏆 **Official Evaluation Report**")
    eval_text = backend_adapter.get_evaluation_report()
    st.markdown(eval_text)

with tab_usage:
    st.markdown("### ⚡ **Runtime Token Usage & Zero-Cost Architecture**")
    usage_text = backend_adapter.get_usage_report()
    st.markdown(usage_text)

with tab_val:
    st.markdown("### 🛡️ **Official Output CSV Schema & Ordering Validator**")
    st.write(
        "Runs `code.output.validator.validate_output` against the current `output.csv`. "
        "Verifies column headers, row counts, natural sort order, phase progression, and empty remediation citations."
    )

    col_btn, col_dl = st.columns([1, 1])
    with col_btn:
        validate_now = st.button("🔍 Run Full Official Validation Now", type="primary", use_container_width=True)

    out_path = backend_adapter.config.output_path
    if out_path.is_file():
        with col_dl:
            with open(out_path, mode="r", encoding="utf-8") as f:
                csv_bytes = f.read()
            st.download_button(
                label="📥 Download output.csv",
                data=csv_bytes,
                file_name="output.csv",
                mime="text/csv",
                use_container_width=True,
            )

    if validate_now:
        with st.spinner("Validating output.csv against official requirements..."):
            report = backend_adapter.validate_audit_output()

        if report.is_valid:
            st.success(f"✅ **VALIDATION PASSED!** (Verified {report.total_rows} case rows in {report.output_path})")
            st.markdown(
                f"""
                <div style="background-color: rgba(76, 175, 80, 0.1); border: 1px solid #4caf50; border-radius: 8px; padding: 14px; margin-top: 10px;">
                    <h5 style="color: #81c784; margin-top: 0;">Summary of Validated Rows</h5>
                    <ul style="margin: 0; padding-left: 20px; font-size: 0.92rem; color: #e8f5e9;">
                        <li><strong>COMPLETE Cases:</strong> {report.complete_count}</li>
                        <li><strong>INCOMPLETE Cases:</strong> {report.incomplete_count}</li>
                        <li><strong>NOT_APPLICABLE Cases:</strong> {report.not_applicable_count}</li>
                        <li><strong>Total Output Rows:</strong> {report.total_rows}</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.error("❌ Validation Failed with the following errors:")
            for err in report.errors:
                st.write(f"- 🔴 {err}")
