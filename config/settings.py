"""Global application configuration and path management.

Handles configurable dataset paths, output paths, and runtime settings.
Never uses hardcoded absolute computer paths.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def find_project_root() -> Path:
    """Locate the root of our project repository."""
    # Start looking upwards from the current file
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "code").is_dir() or (parent / ".git").is_dir():
            return parent
    return Path.cwd()


def resolve_dataset_dir(custom_path: str | Path | None = None) -> Path:
    """Resolve the dataset directory in priority order:
    1. Explicit custom_path argument
    2. DATASET_DIR environment variable
    3. <project_root>/dataset
    4. Sibling clone ../hackerrank-orchestrate-october26/dataset
    """
    if custom_path:
        p = Path(custom_path).resolve()
        if p.is_dir():
            return p

    env_dir = os.environ.get("DATASET_DIR")
    if env_dir:
        p = Path(env_dir).resolve()
        if p.is_dir():
            return p

    project_root = find_project_root()
    local_dataset = project_root / "dataset"
    if local_dataset.is_dir():
        return local_dataset

    # Check sibling directory
    sibling_dataset = project_root.parent / "hackerrank-orchestrate-october26" / "dataset"
    if sibling_dataset.is_dir():
        return sibling_dataset

    # Fallback to local_dataset even if not yet populated
    return local_dataset


@dataclass(frozen=True)
class AppConfig:
    """Application configuration container."""
    project_root: Path
    dataset_dir: Path
    output_path: Path
    sample_requests_path: Path
    sample_output_path: Path
    deletion_requests_path: Path
    user_identities_path: Path
    user_audit_log_path: Path
    system_activity_path: Path
    deletion_rules_path: Path
    evidence_manifest_path: Path
    evidence_dir: Path
    log_file_path: Path
    expected_full_cases: int = 518
    expected_sample_cases: int = 32

    @classmethod
    def load(cls, dataset_dir: str | Path | None = None, output_path: str | Path | None = None) -> AppConfig:
        root = find_project_root()
        ds_dir = resolve_dataset_dir(dataset_dir)
        out_path = Path(output_path).resolve() if output_path else (root / "output.csv")
        return cls(
            project_root=root,
            dataset_dir=ds_dir,
            output_path=out_path,
            sample_requests_path=ds_dir / "sample_deletion_requests.csv",
            sample_output_path=ds_dir / "sample_output.csv",
            deletion_requests_path=ds_dir / "deletion_requests.csv",
            user_identities_path=ds_dir / "user_identities.csv",
            user_audit_log_path=ds_dir / "user_audit_log.csv",
            system_activity_path=ds_dir / "system_activity.csv",
            deletion_rules_path=ds_dir / "deletion_rules.csv",
            evidence_manifest_path=ds_dir / "evidence_files.csv",
            evidence_dir=ds_dir / "evidence",
            log_file_path=root / "log.txt",
        )


_DEFAULT_CONFIG: AppConfig | None = None


def get_config(dataset_dir: str | Path | None = None, output_path: str | Path | None = None) -> AppConfig:
    """Retrieve global configuration, optionally initialized or refreshed."""
    global _DEFAULT_CONFIG
    if _DEFAULT_CONFIG is None or dataset_dir is not None or output_path is not None:
        _DEFAULT_CONFIG = AppConfig.load(dataset_dir, output_path)
    return _DEFAULT_CONFIG
