"""Main application entry point for the Ghost Data deletion audit solution.

Usage:
    python code/main.py [--dataset-dir PATH] [--output-path PATH] [--sample] [--validate-only PATH]
    python code/main.py --case case_01
    python code/main.py --interactive
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from code.orchestrator import Orchestrator
from code.output.validator import validate_output
from config.settings import AppConfig, get_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ghost_data_audit")


def print_case_detail_terminal(case_id: str, dataset_dir: str | Path | None = None) -> None:
    """Print complete case dossier, customer request text, identity graph, and audit steps to terminal."""
    config = get_config(dataset_dir)
    os.environ["DATASET_DIR"] = str(config.dataset_dir)
    orchestrator = Orchestrator(config=config)
    dataset = orchestrator.load_dataset_fn(config.dataset_dir)

    try:
        from code.ingestion import parse_all_evidence
        dataset.evidence_records = parse_all_evidence(config.dataset_dir, dataset.evidence_manifest)
    except Exception:
        pass

    # Find the target request
    req = None
    if hasattr(dataset, "requests_by_case_id") and case_id in dataset.requests_by_case_id:
        req = dataset.requests_by_case_id[case_id]
    elif hasattr(dataset, "requests") and case_id in dataset.requests:
        req = dataset.requests[case_id]
    elif hasattr(dataset, "sample_requests"):
        for r in dataset.sample_requests:
            if r.case_id == case_id:
                req = r
                break
    if not req and hasattr(dataset, "deletion_requests"):
        for r in dataset.deletion_requests:
            if r.case_id == case_id:
                req = r
                break

    if not req:
        print(f"\n[ERROR] Case '{case_id}' not found in dataset!\n")
        return

    identity = orchestrator.resolve_identity_fn(req, dataset)
    row = orchestrator.audit_case(req, dataset)

    # Parse status strings
    status_str = row.deletion_status.value if hasattr(row.deletion_status, "value") else str(row.deletion_status)
    reported_str = req.reported_status.value if hasattr(req.reported_status, "value") else str(req.reported_status)

    print("\n" + "=" * 80)
    print(f"  NORTHSTAR -- CASE AUDIT REPORT: {case_id}")
    print("=" * 80)
    print("CUSTOMER INPUT / DELETION REQUEST:")
    print(f"  Case ID:            {case_id}")
    print(f"  Customer Email:     {req.email}")
    print(f"  Requested At:       {req.requested_at}")
    print(f"  Reported Claim:     {reported_str}")
    print(f"  Audit Cutoff Time:  {req.audit_at}")
    print(f'  Request Text:       "{req.request_text}"')

    print("\nIDENTITY RESOLUTION (user_identities.csv + user_audit_log.csv):")
    user_id = getattr(identity, "user_id", "Not in snapshot")
    name = getattr(identity, "current_name", "Unknown")
    phone = getattr(identity, "current_phone", "None")
    email_hash = getattr(identity, "current_hash", "None")
    all_emails = list(getattr(identity, "all_emails", [req.email]))
    all_phones = list(getattr(identity, "all_phones", []))

    print(f"  Resolved User ID:   {user_id} ({name})")
    print(f"  Primary Phone:      {phone}")
    print(f"  Email Hash:         {email_hash}")
    print(f"  All Known Emails:   {', '.join(all_emails) if all_emails else 'None'}")
    print(f"  All Known Phones:   {', '.join(all_phones) if all_phones else 'None'}")

    print("\nAUDIT VERDICT & REMEDIATION PLAN:")
    print(f"  Official Verdict:   {status_str}")
    print(f"  Total Steps:        {len(row.steps_json)}")

    if not row.steps_json:
        print("  Steps Generated:    [] (Non-deletion request / NOT_APPLICABLE)")
    else:
        for s in row.steps_json:
            p_val = s.phase.value if hasattr(s.phase, "value") else str(s.phase)
            op_val = s.operation.value if hasattr(s.operation, "value") else str(s.operation)
            st_val = s.state.value if hasattr(s.state, "value") else str(s.state)
            ev_str = f" [Cited: {s.evidence_id}]" if s.evidence_id else " [Future Action]"
            print(f"    Step #{s.step_no:<2} | Phase: {p_val:<12} | Op: {op_val:<25} | State: {st_val:<8} | Sys: {s.system_id:<18} | Res: {s.resource_id:<12}{ev_str}")

    print("=" * 80 + "\n")


def run_interactive_mode(dataset_dir: str | Path | None = None) -> None:
    """Run an interactive CLI terminal session for live judge inspection."""
    config = get_config(dataset_dir)
    os.environ["DATASET_DIR"] = str(config.dataset_dir)
    orchestrator = Orchestrator(config=config)
    dataset = orchestrator.load_dataset_fn(config.dataset_dir)

    try:
        from code.ingestion import parse_all_evidence
        dataset.evidence_records = parse_all_evidence(config.dataset_dir, dataset.evidence_manifest)
    except Exception:
        pass

    print("\n" + "=" * 80)
    print("  NORTHSTAR LIVE INTERACTIVE AUDIT TERMINAL")
    print("  Type any Case ID (e.g. case_01, case_06, case_42) to inspect live.")
    print("  Type 'list' to see first 20 cases, or 'q' to exit.")
    print("=" * 80 + "\n")

    while True:
        try:
            user_in = input("northstar-audit> ").strip()
            if not user_in:
                continue
            if user_in.lower() in ["q", "quit", "exit"]:
                print("Exiting interactive terminal. Goodbye!")
                break
            if user_in.lower() == "list":
                all_cids = list(dataset.requests_by_case_id.keys()) if hasattr(dataset, "requests_by_case_id") else list(dataset.requests.keys())
                print(f"Total available cases: {len(all_cids)}. First 20:")
                print(", ".join(all_cids[:20]))
                continue

            print_case_detail_terminal(user_in, dataset_dir=dataset_dir)
        except (KeyboardInterrupt, EOFError):
            print("\nExiting interactive terminal. Goodbye!")
            break


def run_pipeline(
    dataset_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    sample_mode: bool = False,
    validate: bool = True,
) -> None:
    """Run the complete Ghost Data deletion audit pipeline.

    Args:
        dataset_dir: Configurable path to participant dataset directory.
        output_path: Target path for output.csv.
        sample_mode: If True, uses sample_deletion_requests.csv.
        validate: If True, runs validation on the generated output.
    """
    config = get_config(dataset_dir, output_path)
    logger.info("Initializing Ghost Data Deletion Audit Orchestrator...")
    logger.info(f"Project root: {config.project_root}")
    logger.info(f"Dataset directory: {config.dataset_dir}")
    logger.info(f"Target output: {config.output_path}")

    orchestrator = Orchestrator(config=config)

    # Determine which requests to audit
    case_ids = None
    import csv
    if sample_mode:
        sample_file = config.sample_requests_path
        if sample_file.is_file():
            with open(sample_file, mode="r", encoding="utf-8") as f:
                case_ids = [row["case_id"] for row in csv.DictReader(f)]
            logger.info(f"Running in sample mode: {len(case_ids)} sample cases.")
    else:
        full_file = config.deletion_requests_path
        if full_file.is_file():
            with open(full_file, mode="r", encoding="utf-8") as f:
                case_ids = [row["case_id"] for row in csv.DictReader(f)]
            logger.info(f"Running in full evaluation mode: {len(case_ids)} evaluation cases.")

    results = orchestrator.run(
        dataset_dir=config.dataset_dir,
        output_path=config.output_path,
        case_ids=case_ids,
        validate=validate,
    )
    logger.info(f"Pipeline finished successfully. Generated {len(results)} output rows.")

    # Print clean summary breakdown to terminal
    status_counts = {}
    for r in results:
        st_val = r.deletion_status.value if hasattr(r.deletion_status, "value") else str(r.deletion_status)
        status_counts[st_val] = status_counts.get(st_val, 0) + 1

    print("\n" + "=" * 65)
    print("  NORTHSTAR AUDIT EXECUTION SUMMARY")
    print("=" * 65)
    print(f"  Total Requests Audited : {len(results)}")
    for st_name, count in sorted(status_counts.items()):
        print(f"    - {st_name:<20} : {count:>4} cases")
    print("=" * 65 + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ghost Data Deletion Audit Pipeline")
    parser.add_argument(
        "--dataset-dir",
        type=str,
        default=None,
        help="Path to participant dataset directory (overrides DATASET_DIR environment variable)",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default=None,
        help="Path where output.csv should be written (default: <repo_root>/output.csv)",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Run pipeline on sample requests only (sample_deletion_requests.csv)",
    )
    parser.add_argument(
        "--validate-only",
        type=str,
        default=None,
        help="Validate an existing output.csv without running the pipeline",
    )
    parser.add_argument(
        "--case",
        "-c",
        type=str,
        default=None,
        help="Audit and display detailed user input and steps for a single case in the terminal (e.g. --case case_01)",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Start an interactive terminal prompt to query any case ID on demand",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.case:
        print_case_detail_terminal(args.case, dataset_dir=args.dataset_dir)
        sys.exit(0)

    if args.interactive:
        run_interactive_mode(dataset_dir=args.dataset_dir)
        sys.exit(0)

    if args.validate_only:
        target = Path(args.validate_only)
        logger.info(f"Validating existing output file: {target}")
        is_valid = validate_output(target)
        if is_valid:
            logger.info("Validation PASSED.")
            sys.exit(0)
        else:
            logger.error("Validation FAILED.")
            sys.exit(1)

    run_pipeline(
        dataset_dir=args.dataset_dir,
        output_path=args.output_path,
        sample_mode=args.sample,
        validate=True,
    )


if __name__ == "__main__":
    main()
