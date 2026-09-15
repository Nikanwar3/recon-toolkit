#!/usr/bin/env python3
"""CLI entry point: load all five sample sources, reconcile, score, report."""
import argparse

from app.anomaly import score_discrepancies
from app.loaders import load_csv, load_html, load_json, load_xlsx, load_xml
from app.reconcile import reconcile
from app.report import write_report


def main():
    ap = argparse.ArgumentParser(description="Multi-source order reconciliation")
    ap.add_argument("--data-dir", default="data/sample")
    ap.add_argument("--out-dir", default="output")
    args = ap.parse_args()

    d = args.data_dir
    sources = {
        "erp": load_json(f"{d}/erp_orders.json"),
        "warehouse": load_xml(f"{d}/warehouse_orders.xml"),
        "finance": load_csv(f"{d}/finance_orders.csv"),
        "billing": load_xlsx(f"{d}/billing_orders.xlsx"),
        "legacy_portal": load_html(f"{d}/legacy_report.html"),
    }

    discrepancies = reconcile(sources)
    discrepancies = score_discrepancies(discrepancies)
    chart_path, summary = write_report(discrepancies, args.out_dir)

    print(summary)
    print(f"\nChart written to {chart_path}")


if __name__ == "__main__":
    main()
