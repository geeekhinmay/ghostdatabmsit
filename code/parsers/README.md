# Parsers Module (Owned by Member 2)

## Assigned Role
Member 2 owns parsing and normalizing multimodal evidence files located under `dataset/evidence/`.

## Public Function Contract
```python
from pathlib import Path
from code.models.schemas import EvidenceFileManifest, EvidenceRecord

def parse_all_evidence(dataset_dir: str | Path, manifest: dict[str, EvidenceFileManifest]) -> dict[str, EvidenceRecord]:
    """Parse evidence files (SQL, logs, JSON, PDFs, images) into normalized EvidenceRecord objects."""
    ...
```

## Shared Schemas
Import `EvidenceFileManifest` and `EvidenceRecord` from `code.models.schemas`.
