"""Main application entry point for the Ghost Data deletion audit solution.

Usage:
    python code/main.py [--dataset-dir PATH] [--output-path PATH] [--sample] [--validate-only PATH]
"""

from __future__ import annotations

import argparse
import logging
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()

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
