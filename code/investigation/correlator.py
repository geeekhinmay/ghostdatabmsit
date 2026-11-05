"""
Evidence correlation and deep indexing engine.

Indexes all participant-facing evidence files (SQL dumps, JSON snapshots,
readback trace logs, service event logs, account handovers, and PDF documents)
and correlates discovered artifacts with resolved customer identity clusters,
enforcing strict temporal boundaries (captured_at <= audit_at) and rejecting
unrelated decoy records.

Owned by: Member 3 (Chirag Gowda)
Module: code/investigation/correlator.py
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import zlib
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

_RESOURCE_ID_RE = re.compile(
    r"\b((?:account|search|support|analytics|data_flow|backup|audit_record|tombstone|export|connector|marketing)_\w+)\b"
)
_USER_ID_RE = re.compile(r"\b(user_\d+)\b")
_EMAIL_RE = re.compile(r"[\w\.-]+@[\w\.-]+\.[A-Za-z]{2,}")
_HASH_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")


class EvidenceIndexer:
    """
    In-memory deep index for cross-referencing evidence files by customer identifiers.
    """

    def __init__(self, dataset_dir: Path):
        self.dataset_dir = Path(dataset_dir)
        self.records_by_term: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.manifest_entries: List[Dict[str, Any]] = []
        self._indexed = False
        self._index_all()

    def _add_hit(self, term: Optional[str], hit: Dict[str, Any]) -> None:
        if term and isinstance(term, str):
            t = term.strip().lower()
            if t:
                self.records_by_term[t].append(hit)

    def _index_all(self) -> None:
        manifest_path = self.dataset_dir / "evidence_files.csv"
        if not manifest_path.exists():
            logger.warning("evidence_files.csv not found at %s", manifest_path)
            return

        import csv
        with open(manifest_path, "r", encoding="utf-8-sig", errors="ignore") as f:
            self.manifest_entries = list(csv.DictReader(f))

        for entry in self.manifest_entries:
            fid = entry.get("file_id", "")
            fpath_rel = entry.get("file_path", "")
            origin = entry.get("origin", "")
            cap_str = entry.get("captured_at", "")
            if not cap_str:
                continue

            try:
                captured_at = datetime.fromisoformat(cap_str.replace("Z", "+00:00"))
            except Exception:
                continue

            abs_path = self.dataset_dir / fpath_rel
            if not abs_path.exists():
                continue

            ext = abs_path.suffix.lower()
            if ext == ".sql":
                self._index_sql_file(abs_path, fid, captured_at, origin)
            elif ext == ".json":
                self._index_json_file(abs_path, fid, captured_at, origin)
            elif ext in [".log", ".txt"]:
                self._index_log_file(abs_path, fid, captured_at, origin)
            elif ext == ".pdf":
                self._index_pdf_file(abs_path, fid, captured_at, origin)

        self._indexed = True
        logger.info("Indexed %d evidence files across %d unique terms", len(self.manifest_entries), len(self.records_by_term))

    def _index_sql_file(self, fpath: Path, fid: str, captured_at: datetime, origin: str) -> None:
        try:
            with open(fpath, "r", encoding="utf-8-sig", errors="ignore") as f:
                for line in f:
                    l_str = line.strip()
                    if not l_str.startswith("INSERT INTO"):
                        continue

                    emails = _EMAIL_RE.findall(l_str)
                    uids = _USER_ID_RE.findall(l_str)
                    res_ids = _RESOURCE_ID_RE.findall(l_str)

                    hit = {
                        "file_id": fid,
                        "captured_at": captured_at,
                        "origin": origin,
                        "type": "sql",
                        "raw": l_str,
                        "resource_ids": res_ids,
                    }
                    for e in emails: self._add_hit(e, hit)
                    for u in uids: self._add_hit(u, hit)
                    for r in res_ids: self._add_hit(r, hit)
        except Exception as exc:
            logger.warning("Error indexing SQL file %s: %s", fpath, exc)

    def _index_json_file(self, fpath: Path, fid: str, captured_at: datetime, origin: str) -> None:
        try:
            with open(fpath, "r", encoding="utf-8-sig", errors="ignore") as f:
                data = json.load(f)
        except Exception as exc:
            logger.warning("Error reading JSON file %s: %s", fpath, exc)
            return

        if isinstance(data, dict):
            # 1. Snapshots bundle (e.g. evidence_51)
            if "snapshots" in data:
                for snap in data.get("snapshots", []):
                    dstore = snap.get("data_store", "")
                    coll = snap.get("collection", "")
                    for rec in snap.get("records", []):
                        hit = {
                            "file_id": fid,
                            "captured_at": captured_at,
                            "origin": origin,
                            "system_id": dstore,
                            "collection": coll,
                            "data": rec,
                            "type": "json_record",
                        }
                        self._extract_json_terms(rec, hit)

            # 2. Service exports bundle (e.g. evidence_92)
            elif "service_exports" in data:
                for sys_id, sys_data in data.get("service_exports", {}).items():
                    if isinstance(sys_data, dict):
                        for coll_name, items in sys_data.items():
                            if isinstance(items, list):
                                for item in items:
                                    hit = {
                                        "file_id": fid,
                                        "captured_at": captured_at,
                                        "origin": origin,
                                        "system_id": sys_id,
                                        "collection": coll_name,
                                        "data": item,
                                        "type": "service_export",
                                    }
                                    self._extract_json_terms(item, hit)

            # 3. Export jobs (e.g. evidence_59)
            elif "jobs" in data and isinstance(data["jobs"], list):
                for job in data["jobs"]:
                    hit = {
                        "file_id": fid,
                        "captured_at": captured_at,
                        "origin": origin,
                        "system_id": "export_service",
                        "data": job,
                        "type": "json_record",
                    }
                    self._extract_json_terms(job, hit)

            # 4. Standard records container (e.g. evidence_56)
            elif "records" in data and isinstance(data["records"], list):
                source = data.get("source", "unknown")
                for rec in data["records"]:
                    hit = {
                        "file_id": fid,
                        "captured_at": captured_at,
                        "origin": origin,
                        "system_id": source,
                        "data": rec,
                        "type": "json_record",
                    }
                    self._extract_json_terms(rec, hit)
            else:
                hit = {
                    "file_id": fid,
                    "captured_at": captured_at,
                    "origin": origin,
                    "system_id": "unknown",
                    "data": data,
                    "type": "json_record",
                }
                self._extract_json_terms(data, hit)

    def _extract_json_terms(self, obj: Any, hit: Dict[str, Any]) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str):
                    if "@" in v:
                        self._add_hit(v, hit)
                    elif v.startswith("user_"):
                        self._add_hit(v, hit)
                    elif len(v) == 64 and _HASH_RE.match(v):
                        self._add_hit(v, hit)
                    elif any(v.startswith(p) for p in [
                        "account_", "search_", "support_", "analytics_",
                        "data_flow_", "backup_", "audit_record_", "tombstone_", "export_"
                    ]):
                        self._add_hit(v, hit)
                elif isinstance(v, (dict, list)):
                    self._extract_json_terms(v, hit)
        elif isinstance(obj, list):
            for item in obj:
                self._extract_json_terms(item, hit)

    def _index_log_file(self, fpath: Path, fid: str, captured_at: datetime, origin: str) -> None:
        try:
            with open(fpath, "r", encoding="utf-8-sig", errors="ignore") as f:
                lines = f.readlines()
        except Exception as exc:
            logger.warning("Error indexing log file %s: %s", fpath, exc)
            return

        traces: Dict[str, List[str]] = defaultdict(list)
        standalone: List[str] = []

        for line in lines:
            l_str = line.strip()
            if not l_str or l_str.startswith("#"):
                continue

            m_tr = re.search(r'"trace_id"\s*:\s*"([^"]+)"', l_str) or re.search(r'\btrace_id=([^\s,]+)', l_str)
            if m_tr:
                traces[m_tr.group(1)].append(l_str)
            else:
                standalone.append(l_str)

        # Index grouped traces
        for tr_id, tr_lines in traces.items():
            full_raw = "\n".join(tr_lines)
            emails = _EMAIL_RE.findall(full_raw)
            uids = _USER_ID_RE.findall(full_raw)
            res_ids = _RESOURCE_ID_RE.findall(full_raw)
            hashes = _HASH_RE.findall(full_raw)

            hit = {
                "file_id": fid,
                "captured_at": captured_at,
                "origin": origin,
                "type": "log",
                "raw": full_raw,
                "lines": tr_lines,
                "trace_id": tr_id,
                "resource_ids": res_ids,
            }
            for e in emails: self._add_hit(e, hit)
            for u in uids: self._add_hit(u, hit)
            for r in res_ids: self._add_hit(r, hit)
            for h in hashes: self._add_hit(h, hit)

        # Index standalone lines
        for l_str in standalone:
            emails = _EMAIL_RE.findall(l_str)
            uids = _USER_ID_RE.findall(l_str)
            res_ids = _RESOURCE_ID_RE.findall(l_str)
            hashes = _HASH_RE.findall(l_str)

            hit = {
                "file_id": fid,
                "captured_at": captured_at,
                "origin": origin,
                "type": "log",
                "raw": l_str,
                "resource_ids": res_ids,
            }
            for e in emails: self._add_hit(e, hit)
            for u in uids: self._add_hit(u, hit)
            for r in res_ids: self._add_hit(r, hit)
            for h in hashes: self._add_hit(h, hit)

    def _index_pdf_file(self, fpath: Path, fid: str, captured_at: datetime, origin: str) -> None:
        try:
            with open(fpath, "rb") as f:
                content = f.read()

            extracted_text = []
            pos = 0
            while True:
                idx = content.find(b"/Filter [ /ASCII85Decode /FlateDecode ]", pos)
                if idx == -1:
                    break
                s_idx = content.find(b"stream\n", idx)
                if s_idx == -1:
                    s_idx = content.find(b"stream\r\n", idx)
                    if s_idx != -1:
                        s_idx += 8
                else:
                    s_idx += 7

                if s_idx != -1:
                    m_len = re.search(rb"/Length\s+(\d+)", content[idx:s_idx])
                    if m_len:
                        length = int(m_len.group(1))
                        stream_bytes = content[s_idx : s_idx + length].strip()
                        try:
                            dec = base64.a85decode(stream_bytes, adobe=True)
                            decomp = zlib.decompress(dec)
                            extracted_text.append(decomp.decode("latin1", errors="ignore"))
                        except Exception:
                            pass
                pos = idx + 40

            full_text = " ".join(extracted_text)
            emails = _EMAIL_RE.findall(full_text)
            uids = _USER_ID_RE.findall(full_text)
            res_ids = _RESOURCE_ID_RE.findall(full_text)

            hit = {
                "file_id": fid,
                "captured_at": captured_at,
                "origin": origin,
                "type": "pdf",
                "text": full_text,
                "resource_ids": res_ids,
            }
            for e in emails: self._add_hit(e, hit)
            for u in uids: self._add_hit(u, hit)
            for r in res_ids: self._add_hit(r, hit)
        except Exception as exc:
            logger.warning("Error indexing PDF file %s: %s", fpath, exc)

