# Ghost Data Still Exists — Team Solution

AI-Powered Deletion Audit Agent for HackerRank Orchestrate (October 2026).

## Architecture & Team Division

```text
nasdhjksah101001/
├── code/
│   ├── main.py                     # Entry point & CLI (Member 1)
│   ├── orchestrator.py             # Central pipeline orchestrator (Member 1)
│   ├── models/                     # Shared Pydantic schemas & enums (Member 1)
│   │   ├── enums.py
│   │   └── schemas.py
│   ├── output/                     # Output writer & validation (Member 1)
│   │   ├── writer.py
│   │   └── validator.py
│   ├── ingestion/                  # Dataset ingestion (Member 2)
│   ├── parsers/                    # Multimodal evidence parsers (Member 2)
│   ├── identity/                   # Current & historical identity resolution (Member 3)
│   ├── investigation/              # Evidence correlation & risk detection (Member 3)
│   ├── policy/                     # deletion_rules.csv evaluation (Member 4)
│   ├── remediation/                # Ordered remediation planning (Member 4)
│   ├── verification/               # Evidence-backed & post-remediation verification (Member 4)
│   ├── evaluation/                 # Required reports
│   │   ├── evaluation_report.md
│   │   └── usage_report.md
│   └── tests/                      # Unit & integration test suites
│       ├── conftest.py
│       ├── test_models.py
│       ├── test_output.py
│       └── integration/
│           └── test_orchestrator.py
├── config/                         # Configuration & path management (Member 1)
│   └── settings.py
├── AGENTS.md                       # Agent turn logging rules
├── log.txt                         # Session turn log
└── output.csv                      # Root-level evaluation output
```

## Team Responsibilities

| Member | Identifier | Role | Assigned Modules |
|---|---|---|---|
| Member 1 (Lead) | Rajshekhar Singh | Technical Lead, Architect & Integrator | `code/main.py`, `code/orchestrator.py`, `code/models/`, `code/output/`, `config/`, `code/tests/integration/` |
| Member 2 | Team Member 2 | Data Ingestion & Evidence Parsing | `code/ingestion/`, `code/parsers/` |
| Member 3 | Team Member 3 | Identity Resolution & Investigation | `code/identity/`, `code/investigation/` |
| Member 4 | Team Member 4 | Policy, Remediation & Verification | `code/policy/`, `code/remediation/`, `code/verification/` |

## Shared Contracts

All members import shared models from `code.models.schemas` and enums from `code.models.enums`.

Proposed public interfaces:
- `load_dataset(dataset_dir: str | Path) -> DatasetBundle`
- `parse_all_evidence(dataset_dir: str | Path, manifest: dict[str, EvidenceFileManifest]) -> dict[str, EvidenceRecord]`
- `resolve_identity(request: DeletionRequest, dataset: DatasetBundle) -> IdentityResolution`
- `investigate_case(request: DeletionRequest, identity: IdentityResolution, evidence: DatasetBundle) -> InvestigationResult`
- `evaluate_policy(request: DeletionRequest, investigation: InvestigationResult, rules: list[DeletionRule]) -> PolicyDecision`
- `build_remediation_plan(request: DeletionRequest, investigation: InvestigationResult, policy: PolicyDecision) -> list[Step]`
- `build_verification_steps(request: DeletionRequest, investigation: InvestigationResult, policy: PolicyDecision) -> list[Step]`
- `write_output(results: list[OutputRow], output_path: str | Path) -> None`
- `validate_output(output_path: str | Path, expected_rows: int = 518) -> bool`

## Setup & Execution

### Prerequisites
- Python 3.10+
- Dependencies: `pydantic>=2.0`, `pytest>=8.0`

### Running the Test Suite
```bash
python -m pytest -v
```

### Running the Full Pipeline (518 Cases)
```bash
python code/main.py
```

### Running on Sample Cases (32 Cases)
```bash
python code/main.py --sample
```

### Validating Output
```bash
python code/main.py --validate-only output.csv
```
