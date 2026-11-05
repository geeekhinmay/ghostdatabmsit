"""
Backend Adapter Service for NORTHSTAR.

Encapsulates all communication between the Streamlit frontend and the existing
Python backend modules (Orchestrator, Ingestion, Investigation, Policy, Output).
Provides typed dataclasses and safe fallbacks for UI consumption.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import AppConfig, get_config
from code.models.enums import DeletionStatus, Phase, StepOperation, StepState, EvidenceFormat
from code.models.schemas import DatasetBundle, DeletionRequest, OutputRow, Step
from code.orchestrator import Orchestrator
from code.output.validator import validate_output, validate_steps_json

logger = logging.getLogger("northstar_adapter")


# ---------------------------------------------------------------------------
# Data Transfer Objects (DTOs) for Frontend Presentation
# ---------------------------------------------------------------------------


@dataclass
class BackendStatus:
    is_ready: bool
    project_root: str
    dataset_dir: str
    output_path: str
    dataset_exists: bool
    requests_count: int = 0
    sample_count: int = 0
    identities_count: int = 0
    audit_log_count: int = 0
    system_activity_count: int = 0
    rules_count: int = 0
    evidence_files_count: int = 0
    error_message: Optional[str] = None


@dataclass
class AuditExecutionResult:
    success: bool
    mode: str  # "SAMPLE" or "FULL"
    total_cases: int
    duration_seconds: float
    output_path: str
    status_counts: Dict[str, int] = field(default_factory=dict)
    total_steps: int = 0
    is_valid: bool = False
    validation_errors: List[str] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
    error_message: Optional[str] = None


@dataclass
class StepDTO:
    step_no: int
    phase: str
    operation: str
    state: str
    system_id: str
    resource_id: str
    evidence_id: str


@dataclass
class CaseDetailDTO:
    case_id: str
    deletion_status: str
    request_email: str
    requested_at: str
    reported_status: str
    reported_at: str
    audit_at: str
    request_text: str
    # Identity details
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    current_phone: Optional[str] = None
    email_hash: Optional[str] = None
    all_emails: List[str] = field(default_factory=list)
    all_phones: List[str] = field(default_factory=list)
    identity_audit_trail: List[Dict[str, str]] = field(default_factory=list)
    # Audit outcome
    steps: List[StepDTO] = field(default_factory=list)
    findings_count: int = 0
    remediation_count: int = 0
    verification_count: int = 0
    cited_evidence_ids: List[str] = field(default_factory=list)


@dataclass
class EvidenceDetailDTO:
    file_id: str
    file_path: str
    origin: str
    file_format: str
    captured_at: str
    exists_on_disk: bool
    size_bytes: int = 0
    preview_content: str = ""
    preview_type: str = "text"  # "text", "json", "sql", "image", "unsupported"
    total_extracted_records: int = 0
    extracted_records_snippet: List[Dict[str, Any]] = field(default_factory=list)
    cited_by_cases: List[str] = field(default_factory=list)


@dataclass
class ValidationReportDTO:
    is_valid: bool
    total_rows: int
    output_path: str
    errors: List[str] = field(default_factory=list)
    complete_count: int = 0
    incomplete_count: int = 0
    not_applicable_count: int = 0


# ---------------------------------------------------------------------------
# Backend Adapter Class
# ---------------------------------------------------------------------------


class BackendAdapter:
    """Singleton adapter facilitating all interactions with the backend."""

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or get_config()
        self._bundle_cache: Optional[DatasetBundle] = None
        self._orchestrator: Optional[Orchestrator] = None
        self._evidence_records_cache: Optional[List[Any]] = None

    def get_config(self) -> AppConfig:
        return self.config

    def check_backend_readiness(self) -> BackendStatus:
        """Verify backend environment, dataset files, and readiness."""
        try:
            ds_dir = self.config.dataset_dir
            ds_exists = ds_dir.is_dir()
            
            status = BackendStatus(
                is_ready=ds_exists,
                project_root=str(self.config.project_root),
                dataset_dir=str(ds_dir),
                output_path=str(self.config.output_path),
                dataset_exists=ds_exists,
            )

            if ds_exists:
                # Count records in primary CSVs quickly
                status.requests_count = self._count_csv_lines(self.config.deletion_requests_path)
                status.sample_count = self._count_csv_lines(self.config.sample_requests_path)
                status.identities_count = self._count_csv_lines(self.config.user_identities_path)
                status.audit_log_count = self._count_csv_lines(self.config.user_audit_log_path)
                status.system_activity_count = self._count_csv_lines(self.config.system_activity_path)
                status.rules_count = self._count_csv_lines(self.config.deletion_rules_path)
                status.evidence_files_count = self._count_csv_lines(self.config.evidence_manifest_path)

            return status
        except Exception as e:
            logger.exception("Error checking backend readiness")
            return BackendStatus(
                is_ready=False,
                project_root=str(self.config.project_root),
                dataset_dir=str(self.config.dataset_dir),
                output_path=str(self.config.output_path),
                dataset_exists=False,
                error_message=str(e),
            )

    @staticmethod
    def _count_csv_lines(path: Path) -> int:
        if not path.is_file():
            return 0
        try:
            with open(path, mode="r", encoding="utf-8-sig", errors="ignore") as f:
                return max(0, sum(1 for _ in f) - 1)
        except Exception:
            return 0

    def get_bundle(self, force_reload: bool = False) -> DatasetBundle:
        """Load and cache the DatasetBundle using Member 2's loader."""
        if self._bundle_cache is None or force_reload:
            from code.ingestion.loader import load_dataset
            self._bundle_cache = load_dataset(self.config.dataset_dir)
        return self._bundle_cache

    def get_orchestrator(self) -> Orchestrator:
        """Get or initialize the Orchestrator."""
        if self._orchestrator is None:
            self._orchestrator = Orchestrator(config=self.config)
        return self._orchestrator

    def run_audit(
        self,
        sample_mode: bool = False,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> AuditExecutionResult:
        """
        Execute either Sample (32 cases) or Full (518 cases) audit run.
        """
        mode_str = "SAMPLE" if sample_mode else "FULL"
        start_time = time.time()
        captured_logs: List[str] = []

        class TerminalAndBufferHandler(logging.Handler):
            def emit(self, record):
                try:
                    msg = self.format(record)
                    captured_logs.append(msg)
                    # Write directly to terminal console
                    if sys.__stdout__:
                        sys.__stdout__.write(f"[AUDIT] {msg}\n")
                        sys.__stdout__.flush()
                except Exception:
                    pass

        custom_handler = TerminalAndBufferHandler()
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        custom_handler.setFormatter(formatter)
        root_logger = logging.getLogger()
        root_logger.addHandler(custom_handler)
        root_logger.setLevel(logging.INFO)

        try:
            config = self.config
            orch = self.get_orchestrator()
            
            # Select target case_ids
            case_ids = []
            target_csv = config.sample_requests_path if sample_mode else config.deletion_requests_path
            
            if target_csv.is_file():
                with open(target_csv, mode="r", encoding="utf-8-sig") as f:
                    case_ids = [row["case_id"].strip() for row in csv.DictReader(f) if "case_id" in row]
            
            if not case_ids:
                raise ValueError(f"No case IDs found in {target_csv}")

            total_cases = len(case_ids)
            
            # Notify start
            if progress_callback:
                progress_callback(0, total_cases, f"Starting {mode_str} audit of {total_cases} cases...")

            # Output path: keep output.csv reserved for full 518 cases
            target_out_path = (config.project_root / "sample_output_generated.csv") if sample_mode else config.output_path

            results = orch.run(
                dataset_dir=config.dataset_dir,
                output_path=target_out_path,
                case_ids=case_ids,
                validate=True,
            )

            duration = round(time.time() - start_time, 2)
            
            # Aggregate status counts and steps
            status_counts: Dict[str, int] = {}
            total_steps = 0
            for r in results:
                s = r.deletion_status.value if hasattr(r.deletion_status, "value") else str(r.deletion_status)
                status_counts[s] = status_counts.get(s, 0) + 1
                total_steps += len(r.steps_json)

            # Validate output
            is_valid = validate_output(
                target_out_path,
                expected_rows=len(results),
                dataset_dir=config.dataset_dir,
            )

            if progress_callback:
                progress_callback(total_cases, total_cases, f"Completed {mode_str} audit successfully!")

            return AuditExecutionResult(
                success=True,
                mode=mode_str,
                total_cases=len(results),
                duration_seconds=duration,
                output_path=str(target_out_path),
                status_counts=status_counts,
                total_steps=total_steps,
                is_valid=is_valid,
                logs=captured_logs,
            )

        except Exception as e:
            logger.exception("Error executing audit run")
            duration = round(time.time() - start_time, 2)
            return AuditExecutionResult(
                success=False,
                mode=mode_str,
                total_cases=0,
                duration_seconds=duration,
                output_path=str(self.config.output_path),
                logs=captured_logs,
                error_message=str(e),
            )
        finally:
            root_logger.removeHandler(custom_handler)

    def get_audit_results(self, output_path: Optional[Path | str] = None) -> List[Dict[str, Any]]:
        """
        Read and return rows from output.csv.
        Each entry has: case_id, deletion_status, steps (parsed list), step_count.
        """
        p = Path(output_path) if output_path else self.config.output_path
        if not p.is_file():
            return []

        results = []
        with open(p, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                case_id = row.get("case_id", "").strip()
                status = row.get("deletion_status", "").strip()
                steps_raw = row.get("steps_json", "[]")
                try:
                    steps = json.loads(steps_raw)
                except Exception:
                    steps = []

                results.append({
                    "case_id": case_id,
                    "deletion_status": status,
                    "steps": steps,
                    "step_count": len(steps),
                })
        return results

    def get_case_details(self, case_id: str) -> Optional[CaseDetailDTO]:
        """
        Retrieve complete deep-dive details for a specific case:
        Request data, identity resolution graph, and step-by-step breakdown.
        """
        bundle = self.get_bundle()
        req = bundle.requests_by_case_id.get(case_id)
        if not req:
            # Check sample requests
            for r in bundle.sample_requests:
                if r.case_id == case_id:
                    req = r
                    break
        if not req:
            return None

        # Resolve Identity using Member 3's resolver
        from code.identity.resolver import resolve_identity
        identity = resolve_identity(req, bundle)

        # Retrieve authoritative steps and verdict from output.csv or fallback to run audit_case
        out_row = None
        for out_candidate in [self.config.output_path, self.config.project_root / "sample_output_generated.csv"]:
            if out_candidate.is_file():
                try:
                    with open(out_candidate, mode="r", encoding="utf-8-sig") as f:
                        for r in csv.DictReader(f):
                            if r.get("case_id", "").strip() == case_id:
                                st_val = r.get("deletion_status", "").strip()
                                try:
                                    s_json = json.loads(r.get("steps_json", "[]"))
                                except Exception:
                                    s_json = []
                                out_row = (st_val, s_json)
                                break
                except Exception:
                    pass
            if out_row:
                break

        if out_row:
            final_status, raw_steps_data = out_row
        else:
            orch = self.get_orchestrator()
            row = orch.audit_case(req, bundle)
            final_status = row.deletion_status.value if hasattr(row.deletion_status, "value") else str(row.deletion_status)
            raw_steps_data = row.steps_json

        step_dtos: List[StepDTO] = []
        findings_count = 0
        remediation_count = 0
        verification_count = 0
        cited_evidence: Set[str] = set()

        for s in raw_steps_data:
            if isinstance(s, dict):
                p_val = s.get("phase", "")
                op_val = s.get("operation", "")
                st_val = s.get("state", "")
                sys_id = s.get("system_id", "")
                res_id = s.get("resource_id", "")
                ev_id = s.get("evidence_id", "")
                s_no = s.get("step_no", 1)
            else:
                p_val = s.phase.value if hasattr(s.phase, "value") else str(s.phase)
                op_val = s.operation.value if hasattr(s.operation, "value") else str(s.operation)
                st_val = s.state.value if hasattr(s.state, "value") else str(s.state)
                sys_id = s.system_id
                res_id = s.resource_id
                ev_id = s.evidence_id or ""
                s_no = s.step_no
            
            if p_val == "FINDING":
                findings_count += 1
            elif p_val == "REMEDIATION":
                remediation_count += 1
            elif p_val == "VERIFICATION":
                verification_count += 1

            if ev_id:
                cited_evidence.add(ev_id)

            step_dtos.append(
                StepDTO(
                    step_no=s_no,
                    phase=p_val,
                    operation=op_val,
                    state=st_val,
                    system_id=sys_id,
                    resource_id=res_id,
                    evidence_id=ev_id,
                )
            )

        # Audit trail history from identity
        history_trail = []
        if hasattr(identity, "audit_history") and identity.audit_history:
            for log in identity.audit_history:
                history_trail.append({
                    "event_time": str(getattr(log, "event_time", "")),
                    "field_changed": getattr(log, "field_changed", getattr(log, "field_name", "")),
                    "old_value": getattr(log, "old_value", ""),
                    "new_value": getattr(log, "new_value", ""),
                })

        all_emails = list(getattr(identity, "all_emails", [req.email]))
        all_phones = list(getattr(identity, "all_phones", []))

        return CaseDetailDTO(
            case_id=req.case_id,
            deletion_status=final_status,
            request_email=req.email,
            requested_at=str(req.requested_at),
            reported_status=req.reported_status.value if hasattr(req.reported_status, "value") else str(req.reported_status),
            reported_at=str(req.reported_at),
            audit_at=str(req.audit_at),
            request_text=req.request_text,
            user_id=getattr(identity, "user_id", None),
            user_name=getattr(identity, "current_name", None),
            current_phone=getattr(identity, "current_phone", None),
            email_hash=getattr(identity, "current_hash", None),
            all_emails=all_emails,
            all_phones=all_phones,
            identity_audit_trail=history_trail,
            steps=step_dtos,
            findings_count=findings_count,
            remediation_count=remediation_count,
            verification_count=verification_count,
            cited_evidence_ids=sorted(list(cited_evidence)),
        )

    def get_evidence_list(self) -> List[Dict[str, Any]]:
        """List all 94 evidence files from the manifest with metadata."""
        bundle = self.get_bundle()
        manifest = bundle.evidence_manifest
        ds_dir = self.config.dataset_dir
        
        items = []
        for entry in manifest:
            abs_p = ds_dir / entry.file_path
            ext = abs_p.suffix.lower().lstrip(".")
            exists = abs_p.is_file()
            size = abs_p.stat().st_size if exists else 0
            
            items.append({
                "file_id": entry.file_id,
                "file_path": entry.file_path,
                "origin": entry.origin,
                "format": ext.upper() if ext else "UNKNOWN",
                "captured_at": str(entry.captured_at),
                "size_kb": round(size / 1024, 1),
                "exists": exists,
            })
        return items

    def get_evidence_details(self, file_id: str) -> Optional[EvidenceDetailDTO]:
        """Retrieve preview content and correlation info for an evidence file."""
        bundle = self.get_bundle()
        entry = bundle.manifest_by_file_id.get(file_id)
        if not entry:
            return None

        ds_dir = self.config.dataset_dir
        abs_p = ds_dir / entry.file_path
        exists = abs_p.is_file()
        ext = abs_p.suffix.lower()

        preview_content = ""
        preview_type = "text"
        size = abs_p.stat().st_size if exists else 0

        if exists:
            try:
                if ext in [".log", ".txt"]:
                    preview_type = "text"
                    with open(abs_p, mode="r", encoding="utf-8-sig", errors="ignore") as f:
                        lines = [f.readline() for _ in range(120)]
                        preview_content = "".join(lines)
                elif ext == ".sql":
                    preview_type = "sql"
                    with open(abs_p, mode="r", encoding="utf-8-sig", errors="ignore") as f:
                        lines = [f.readline() for _ in range(120)]
                        preview_content = "".join(lines)
                elif ext == ".json":
                    preview_type = "json"
                    with open(abs_p, mode="r", encoding="utf-8-sig", errors="ignore") as f:
                        data = json.load(f)
                        preview_content = json.dumps(data, indent=2)[:4000]
                elif ext in [".png", ".jpg", ".jpeg"]:
                    preview_type = "image"
                    preview_content = str(abs_p)
                elif ext == ".pdf":
                    preview_type = "text"
                    preview_content = f"PDF Document: {entry.file_path}\nFile size: {round(size / 1024, 1)} KB\n(Rendered via parser text-extractor)"
            except Exception as e:
                preview_content = f"Error reading preview: {e}"

        # Find which cases cited this evidence file in output.csv
        cited_cases = []
        for r in self.get_audit_results():
            for s in r.get("steps", []):
                if s.get("evidence_id") == file_id:
                    cited_cases.append(r["case_id"])
                    break

        return EvidenceDetailDTO(
            file_id=entry.file_id,
            file_path=entry.file_path,
            origin=entry.origin,
            file_format=ext.upper().lstrip("."),
            captured_at=str(entry.captured_at),
            exists_on_disk=exists,
            size_bytes=size,
            preview_content=preview_content,
            preview_type=preview_type,
            cited_by_cases=sorted(cited_cases),
        )

    def validate_audit_output(self, output_path: Optional[Path | str] = None) -> ValidationReportDTO:
        """Validate output.csv and return structured results."""
        p = Path(output_path) if output_path else self.config.output_path
        if not p.is_file():
            return ValidationReportDTO(
                is_valid=False,
                total_rows=0,
                output_path=str(p),
                errors=[f"Output file does not exist: {p}"],
            )

        rows = self.get_audit_results(p)
        counts = {"COMPLETE": 0, "INCOMPLETE": 0, "NOT_APPLICABLE": 0}
        for r in rows:
            st = r["deletion_status"]
            counts[st] = counts.get(st, 0) + 1

        is_valid = validate_output(
            p,
            expected_rows=len(rows),
            dataset_dir=self.config.dataset_dir,
        )

        return ValidationReportDTO(
            is_valid=is_valid,
            total_rows=len(rows),
            output_path=str(p),
            errors=[] if is_valid else ["Validation errors detected in output.csv"],
            complete_count=counts.get("COMPLETE", 0),
            incomplete_count=counts.get("INCOMPLETE", 0),
            not_applicable_count=counts.get("NOT_APPLICABLE", 0),
        )

    def get_evaluation_report(self) -> str:
        """Read evaluation_report.md."""
        p = self.config.project_root / "code" / "evaluation" / "evaluation_report.md"
        if p.is_file():
            return p.read_text(encoding="utf-8")
        return "# Evaluation Report Not Found"

    def get_usage_report(self) -> str:
        """Read usage_report.md."""
        p = self.config.project_root / "code" / "evaluation" / "usage_report.md"
        if p.is_file():
            return p.read_text(encoding="utf-8")
        return "# Usage Report Not Found"


# Singleton instance
backend_adapter = BackendAdapter()
