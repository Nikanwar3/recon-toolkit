"""Render reconciliation results as a chart + text summary."""
from collections import Counter
from pathlib import Path

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
