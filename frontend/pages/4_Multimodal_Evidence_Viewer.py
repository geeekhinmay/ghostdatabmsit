"""
Page 4: Multimodal Evidence Viewer
Inspect and Correlate All 94 Evidence Files Across Formats
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
import streamlit as st
from frontend.services.backend_adapter import backend_adapter

st.set_page_config(page_title="Evidence Viewer | NORTHSTAR", page_icon="📂", layout="wide")

st.markdown("## 📂 **Multimodal Evidence Viewer**")
st.caption("Inspect and correlate all 94 evidence files across SQL replicas, JSON snapshots, logs, PDFs, and OCR screenshots.")

# Retrieve evidence manifest list
evidence_list = backend_adapter.get_evidence_list()
if not evidence_list:
    st.error("No evidence manifest entries found.")
    st.stop()

# Filter Controls
col_f1, col_f2, col_f3 = st.columns([1, 1, 2])
formats = ["ALL"] + sorted(list(set(e["format"] for e in evidence_list)))
origins = ["ALL"] + sorted(list(set(e["origin"] for e in evidence_list)))

with col_f1:
    selected_format = st.selectbox("Filter Format:", options=formats, index=0)
with col_f2:
    selected_origin = st.selectbox("Filter Origin:", options=origins, index=0)
with col_f3:
    search_file = st.text_input("Search File ID or Path (e.g. evidence_01):", value="").strip().lower()

# Filtered list
filtered_files = []
for e in evidence_list:
    if selected_format != "ALL" and e["format"] != selected_format:
        continue
    if selected_origin != "ALL" and e["origin"] != selected_origin:
        continue
    if search_file and (search_file not in e["file_id"].lower() and search_file not in e["file_path"].lower()):
        continue
    filtered_files.append(e)

st.caption(f"Showing **{len(filtered_files)}** of **{len(evidence_list)}** evidence files")

# File Selection for Deep Preview
file_ids = [f["file_id"] for f in filtered_files]
if not file_ids:
    st.warning("No files match the current filters.")
    st.stop()

selected_file_id = st.selectbox("Select Evidence File to Inspect:", options=file_ids, index=0)

# Retrieve details for selected file
ev_detail = backend_adapter.get_evidence_details(selected_file_id)
if not ev_detail:
    st.error(f"Could not load details for {selected_file_id}")
    st.stop()

st.markdown("---")

# Evidence File Dossier
col_d1, col_d2 = st.columns([2, 1])

with col_d1:
    st.markdown(
        f"""
        <div style="background-color: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 14px; margin-bottom: 15px;">
            <h4 style="margin: 0 0 8px 0; font-family: monospace;">📁 {ev_detail.file_id} &nbsp;|&nbsp; <code>{ev_detail.file_path}</code></h4>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; font-size: 0.88rem; color: #b0bec5;">
                <div>🏛️ <strong>Origin:</strong> <code>{ev_detail.origin}</code></div>
                <div>📄 <strong>Format:</strong> <code>{ev_detail.file_format}</code></div>
                <div>⏰ <strong>Snapshot Captured:</strong> {ev_detail.captured_at}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_d2:
    st.markdown(
        f"""
        <div style="background-color: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 14px; margin-bottom: 15px;">
            <div style="font-size: 0.85rem; color: #90caf9;">⚖️ <strong>Cited by Cases:</strong></div>
            <div style="font-size: 1.25rem; font-weight: bold; color: #81c784;">{len(ev_detail.cited_by_cases)} cases</div>
            <div style="font-size: 0.8rem; color: #888;">Cited in audit output.csv</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# Content Preview
st.markdown("#### 🔍 **Evidence Content Preview**")

if ev_detail.preview_type == "image":
    if Path(ev_detail.preview_content).is_file():
        st.image(ev_detail.preview_content, caption=f"Screenshot Evidence: {ev_detail.file_path}", use_container_width=True)
    else:
        st.warning("Image file path could not be located on disk.")
elif ev_detail.preview_type == "sql":
    st.code(ev_detail.preview_content, language="sql")
elif ev_detail.preview_type == "json":
    st.code(ev_detail.preview_content, language="json")
else:
    st.text_area("File Snippet (First 120 lines):", value=ev_detail.preview_content, height=350, disabled=True)

# Cases citing this evidence
if ev_detail.cited_by_cases:
    st.markdown("##### 📌 **Cases Citing this Evidence File as Proof of Violation or Verification:**")
    st.write(", ".join(f"`{c}`" for c in ev_detail.cited_by_cases))
else:
    st.info("ℹ️ No cases currently cite this specific evidence file.")

st.markdown("---")
st.markdown("### 📋 **Complete Evidence Manifest Summary Table**")
st.dataframe(pd.DataFrame(evidence_list), use_container_width=True, hide_index=True)
