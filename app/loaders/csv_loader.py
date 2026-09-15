import pandas as pd

from .schema import normalize_record


def load_csv(path):
    """Load orders from a CSV export (e.g. a finance system's batch report)."""
    df = pd.read_csv(path, dtype=str)
    return [normalize_record(r) for r in df.to_dict(orient="records")]
