import json
from pathlib import Path

from .schema import normalize_record


def load_json(path):
    """Load orders from a JSON export (e.g. an ERP system's API dump)."""
    records = json.loads(Path(path).read_text())
    return [normalize_record(r) for r in records]
