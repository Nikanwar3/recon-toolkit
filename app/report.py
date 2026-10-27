"""Render reconciliation results as a chart + text summary, and (for the
generic two-dataset engine) as machine-readable JSON/CSV job reports."""
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")  # headless-safe: no display backend required
import matplotlib.pyplot as plt

from .soap_client import amount_to_words


def _mismatch_field_counts(discrepancies):
    counter = Counter()
    for d in discrepancies:
        for field in d["field_mismatches"]:
            counter[field] += 1
        for source in d["missing_from"]:
            counter[f"missing:{source}"] += 1
    return counter


def render_chart(discrepancies, output_path="reconciliation_report.png"):
    counts = _mismatch_field_counts(discrepancies)
    labels = list(counts.keys())
    values = [counts[k] for k in labels]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(labels, values, color="#4C72B0")
    ax.set_title("Reconciliation Discrepancies by Type")
    ax.set_ylabel("Order count")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def render_summary(discrepancies, top_n=5):
    flagged = [d for d in discrepancies if d.get("flagged")]
    total_spread = sum(d["max_amount_spread"] for d in discrepancies)

    lines = [
        f"Reconciled orders with discrepancies: {len(discrepancies)}",
        f"High-priority (ML-flagged) discrepancies: {len(flagged)}",
        f"Total amount spread across mismatches: ${total_spread:,.2f}",
    ]

    words = amount_to_words(total_spread)
    if words:
        lines.append(f"Audit note: total mismatch amount is {words}.")

    lines.append("")
    lines.append(f"Top {min(top_n, len(flagged))} highest-priority orders:")
    for d in flagged[:top_n]:
        lines.append(
            f"  {d['order_id']}: missing_from={d['missing_from'] or 'none'}, "
            f"mismatched_fields={list(d['field_mismatches'].keys())}, "
            f"amount_spread=${d['max_amount_spread']:.2f}"
        )
    return "\n".join(lines)


def write_report(discrepancies, out_dir="."):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    chart_path = render_chart(discrepancies, out_dir / "reconciliation_report.png")
    summary = render_summary(discrepancies)
    (out_dir / "reconciliation_summary.txt").write_text(summary)
    return chart_path, summary


def build_job_report(
    job_id: str,
    status: str,
    source_name: str,
    target_name: str,
    source_count: int,
    target_count: int,
    matched_count: int,
    source_only_count: int,
    target_only_count: int,
    invalid_count: int,
    duration_seconds: float,
    field_mismatches: List[Dict[str, Any]],
    error_summary: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble the machine-readable report dict for one generic
    (source, target) reconciliation job. `field_mismatches` is a flat list
    of {"business_key", "field", "source_value", "target_value"} dicts --
    decoupled from both the engine's dataclasses and the DB layer's row
    type, so this function has no dependency on either.
    """
    return {
        "job_id": job_id,
        "status": status,
        "source_name": source_name,
        "target_name": target_name,
        "source_count": source_count,
        "target_count": target_count,
        "matched_count": matched_count,
        "mismatched_count": len({m["business_key"] for m in field_mismatches}),
        "source_only_count": source_only_count,
        "target_only_count": target_only_count,
        "invalid_count": invalid_count,
        "duration_seconds": duration_seconds,
        "field_mismatches": field_mismatches,
        "error_summary": error_summary,
    }


def write_json_report(report: Dict[str, Any], out_dir=".") -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{report['job_id']}_report.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    return path


def write_csv_report(report: Dict[str, Any], out_dir=".") -> Path:
    """Writes the field-level mismatches as CSV (the part of the report
    that is naturally tabular); job-level counts stay in the JSON report."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{report['job_id']}_mismatches.csv"
    fieldnames = ["business_key", "field", "source_value", "target_value"]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in report["field_mismatches"]:
            writer.writerow({k: row.get(k) for k in fieldnames})
    return path
