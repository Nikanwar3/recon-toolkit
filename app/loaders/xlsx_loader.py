import pandas as pd

from .schema import normalize_record


def load_xlsx(path):
    """Load orders from an Excel export (e.g. a billing system's manual extract)."""
    df = pd.read_excel(path, dtype=str, engine="openpyxl")
    return [normalize_record(r) for r in df.to_dict(orient="records")]
