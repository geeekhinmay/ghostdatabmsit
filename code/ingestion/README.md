# Ingestion Module (Owned by Member 2)

## Assigned Role
Member 2 owns data ingestion and parsing.

## Public Function Contract
```python
def load_dataset(dataset_dir: str | Path) -> DatasetBundle:
    """Load all participant-facing CSVs and evidence files into a structured DatasetBundle."""
    ...
```

## Shared Schemas
Import shared models from `code.models.schemas` and enums from `code.models.enums`:
- `DatasetBundle`
- `DeletionRequest`
- `UserIdentity`
- `UserAuditRecord`
- `SystemActivityRecord`
- `DeletionRule`
- `EvidenceFileManifest`
- `EvidenceRecord`

Do not invent custom schemas or modify existing model definitions.

## Integration Example
```python
from pathlib import Path
from code.ingestion import load_dataset

bundle = load_dataset(Path("dataset"))
print(f"Loaded {len(bundle.requests)} deletion requests")
```
