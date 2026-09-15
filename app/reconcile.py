"""Core reconciliation engine: merge order records from N sources keyed by
order_id, and surface where sources disagree or a record is missing entirely.
"""
from collections import defaultdict

COMPARE_FIELDS = ["customer", "amount", "status", "date"]
AMOUNT_TOLERANCE = 0.01


def merge_by_order_id(sources):
    """Group records from every named source under their shared order_id.

    `sources` is a {source_name: records} mapping, not inferred purely from
    record contents -- a source that returns zero records must still count
    as a known source, otherwise a fully-failed export would be silently
    invisible to "missing_from" detection (the worst-case reconciliation miss).
    """
    merged = defaultdict(dict)
    for source_name, records in sources.items():
        for rec in records:
            merged[rec["order_id"]][source_name] = rec
    return merged, sorted(sources.keys())


def diff_order(order_id, by_source, all_sources):
    """Return the discrepancies for one order_id across all sources, or None."""
    present_sources = set(by_source.keys())
    missing_from = sorted(set(all_sources) - present_sources)

    field_mismatches = {}
    for field in COMPARE_FIELDS:
        values = {src: rec[field] for src, rec in by_source.items()}
        distinct = set(values.values())
        if field == "amount":
            # Tolerate float rounding noise; only flag real disagreement.
            amounts = list(values.values())
            if max(amounts) - min(amounts) > AMOUNT_TOLERANCE:
                field_mismatches[field] = values
        elif len(distinct) > 1:
            field_mismatches[field] = values

    if not missing_from and not field_mismatches:
        return None

    max_amount_spread = 0.0
    if "amount" in field_mismatches:
        amounts = list(field_mismatches["amount"].values())
        max_amount_spread = round(max(amounts) - min(amounts), 2)

    return {
        "order_id": order_id,
        "missing_from": missing_from,
        "field_mismatches": field_mismatches,
        "max_amount_spread": max_amount_spread,
        "sources_present": sorted(present_sources),
    }


def reconcile(sources):
    """Reconcile order records across an arbitrary number of named sources.

    `sources` is a {source_name: records} mapping. Returns a list of
    discrepancy dicts, one per order_id that disagrees across sources or is
    missing from at least one of them.
    """
    merged, all_sources = merge_by_order_id(sources)
    discrepancies = []
    for order_id, by_source in merged.items():
        d = diff_order(order_id, by_source, all_sources)
        if d:
            discrepancies.append(d)
    discrepancies.sort(key=lambda d: d["order_id"])
    return discrepancies
