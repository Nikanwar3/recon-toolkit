"""Field comparators for the reconciliation engine.

Each comparator is `(source_value, target_value) -> bool` (True = equal).
Plain `==` is almost never the right comparator across real systems --
amounts round differently, dates arrive in different formats, and string
casing drifts -- so the engine takes a comparator per field instead of
assuming exact equality everywhere.
"""
from datetime import date, datetime
from typing import Any

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d-%m-%Y", "%d/%m/%Y")


def exact(source_value: Any, target_value: Any) -> bool:
    return source_value == target_value


def numeric_tolerance(tolerance: float):
    """Equal if both sides parse as numbers within `tolerance` of each
    other. NULL on either side is only equal to NULL on the other."""

    def cmp(source_value, target_value):
        if source_value is None or target_value is None:
            return source_value == target_value
        return abs(float(source_value) - float(target_value)) <= tolerance

    return cmp


def case_insensitive(source_value: Any, target_value: Any) -> bool:
    if source_value is None or target_value is None:
        return source_value == target_value
    return str(source_value).strip().lower() == str(target_value).strip().lower()


def parse_date(value: Any) -> date:
    """Parse a date from any of the formats real exports tend to use.
    Raises ValueError if none match, with the attempted value in the message.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date format: {value!r}")


def date_equal(source_value: Any, target_value: Any) -> bool:
    """Equal if both sides parse to the same calendar date, regardless of
    which of the supported formats each side used."""
    if source_value is None or target_value is None:
        return source_value == target_value
    try:
        return parse_date(source_value) == parse_date(target_value)
    except ValueError:
        # Neither side parses as a known date format -- fall back to a
        # literal string comparison rather than raising mid-reconciliation.
        return str(source_value).strip() == str(target_value).strip()
