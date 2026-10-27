"""Format-only loaders for the generic two-dataset reconciliation CLI
(`main.py run`). Unlike `csv_loader`/`json_loader` (which hard-code the
5-field order schema and coerce eagerly), these return raw string-keyed
dicts straight off the wire -- schema validation and type coercion for an
arbitrary configured schema is `app.validation`'s job, not the loader's.
"""
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from ..errors import ValidationError


def load_csv_records(path: str) -> List[Dict[str, Any]]:
    """Load raw records from a CSV file. An empty file (header-only or
    zero-byte) yields an empty list rather than an error -- a dataset with
    no rows is valid input for reconciliation, just not a useful one."""
    p = Path(path)
    if p.stat().st_size == 0:
        return []
    df = pd.read_csv(p, dtype=str, keep_default_na=False, na_values=[""])
    return [
        {str(k): (None if pd.isna(v) else v) for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


def load_json_records(path: str) -> List[Dict[str, Any]]:
    """Load raw records from a JSON file holding a top-level array of
    objects. Raises ValidationError (not a bare JSONDecodeError) on
    malformed JSON, so callers get a typed, catchable error."""
    text = Path(path).read_text()
    if not text.strip():
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValidationError(f"{path} must contain a top-level JSON array of records")
    return data


_LOADERS = {".csv": load_csv_records, ".json": load_json_records}


def load_records(path: str) -> List[Dict[str, Any]]:
    """Dispatch to the right loader by file extension."""
    suffix = Path(path).suffix.lower()
    if suffix not in _LOADERS:
        raise ValidationError(f"unsupported input format {suffix!r} for {path}; expected .csv or .json")
    return _LOADERS[suffix](path)
