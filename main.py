#!/usr/bin/env python3
"""CLI entry point.

Two subcommands:
  demo  -- the original 5-source order reconciliation walkthrough
           (JSON/XML/CSV/XLSX/HTML -> reconcile -> ML triage -> chart+text).
  run   -- the generic, configurable two-dataset reconciliation engine:
           validate source + target (CSV/JSON) against a configurable
           business key and field rules, persist job metadata/results to a
           relational database, and emit JSON/CSV reports.

Running with no arguments is equivalent to `demo`, to preserve the
pre-existing `python main.py` behavior.
"""
import argparse
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone

from app.anomaly import score_discrepancies
from app.db.base import MismatchRow, ReconciliationJob, ReconciliationSummary
from app.errors import DatabaseConnectionError, ReconciliationError
from app.loaders import load_csv, load_html, load_json, load_records, load_xlsx, load_xml
from app.logging_config import configure_logging
from app.reconcile import reconcile
from app.reconciliation import FieldComparison, ReconciliationConfig, reconcile_datasets
from app.reconciliation import rules as comparison_rules
from app.report import build_job_report, write_csv_report, write_json_report, write_report
from app.validation import FieldSpec, validate_records

logger = logging.getLogger("recon_toolkit")


def run_demo(args):
    """The original 5-sample-source reconciliation walkthrough, unchanged."""
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


def _parse_compare_arg(arg):
    """Parse one `--compare` argument of the form `field[:rule[:param]]`.

    Supported rules: exact (default), numeric:<tolerance>, date, ci
    (case-insensitive string).
    """
    parts = arg.split(":")
    name = parts[0]
    rule = parts[1] if len(parts) > 1 else "exact"

    if rule == "exact":
        comparator = comparison_rules.exact
        coerce = None
    elif rule == "numeric":
        tolerance = float(parts[2]) if len(parts) > 2 else 0.0
        comparator = comparison_rules.numeric_tolerance(tolerance)
        coerce = float
    elif rule == "date":
        comparator = comparison_rules.date_equal
        coerce = None
    elif rule == "ci":
        comparator = comparison_rules.case_insensitive
        coerce = None
    else:
        raise ReconciliationError(f"unknown comparison rule {rule!r} for field {name!r}")

    field_spec = FieldSpec(name=name, required=True, coerce=coerce)
    return FieldComparison(name=name, comparator=comparator), field_spec


def _build_repository(args):
    if args.db_backend == "sqlite":
        from app.db import SqliteReconciliationRepository

        return SqliteReconciliationRepository(args.sqlite_path)
    if args.db_backend == "oracle":
        from app.db.oracle_repo import OracleReconciliationRepository

        dsn = os.environ.get("ORACLE_DSN")
        user = os.environ.get("ORACLE_USER")
        password = os.environ.get("ORACLE_PASSWORD")
        if not all([dsn, user, password]):
            raise DatabaseConnectionError(
                "ORACLE_DSN, ORACLE_USER and ORACLE_PASSWORD env vars must all be set "
                "to use --db-backend oracle (see docs/oracle-setup.md)"
            )
        return OracleReconciliationRepository(dsn=dsn, user=user, password=password)
    raise ValueError(f"unknown db backend {args.db_backend!r}")


def run_generic(args):
    """Generic, configurable reconciliation of a source and target dataset,
    with job metadata and results persisted to the configured database."""
    configure_logging()

    key_fields = args.key
    parsed_compare = [_parse_compare_arg(c) for c in args.compare]
    compare_fields = [comparison for comparison, _ in parsed_compare]

    field_specs_by_name = {k: FieldSpec(name=k, required=True) for k in key_fields}
    for _, spec in parsed_compare:
        field_specs_by_name[spec.name] = spec
    field_specs = list(field_specs_by_name.values())

    job_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    perf_start = time.perf_counter()

    repo = _build_repository(args)
    try:
        repo.initialize_schema()
        repo.create_job(
            ReconciliationJob(
                job_id=job_id,
                source_name=args.source_name,
                target_name=args.target_name,
                status="running",
                started_at=started_at,
            )
        )

        source_raw = load_records(args.source)
        target_raw = load_records(args.target)

        source_validation = validate_records(source_raw, field_specs, key_fields)
        target_validation = validate_records(target_raw, field_specs, key_fields)
        invalid_count = len(source_validation.invalid) + len(target_validation.invalid)

        config = ReconciliationConfig(key_fields=key_fields, compare_fields=compare_fields)
        result = reconcile_datasets(source_validation.valid, target_validation.valid, config)

        flat_mismatches = []
        mismatch_rows = []
        for mismatched in result.mismatched:
            key_str = "|".join(str(part) for part in mismatched.key)
            for field_mismatch in mismatched.mismatches:
                row = {
                    "business_key": key_str,
                    "field": field_mismatch.field,
                    "source_value": field_mismatch.source_value,
                    "target_value": field_mismatch.target_value,
                }
                flat_mismatches.append(row)
                mismatch_rows.append(
                    MismatchRow(
                        business_key=key_str,
                        field_name=field_mismatch.field,
                        source_value=str(field_mismatch.source_value),
                        target_value=str(field_mismatch.target_value),
                    )
                )

        duration_seconds = round(time.perf_counter() - perf_start, 4)
        summary = ReconciliationSummary(
            job_id=job_id,
            source_count=len(source_raw),
            target_count=len(target_raw),
            matched_count=result.matched_count,
            mismatched_count=result.mismatched_count,
            source_only_count=result.source_only_count,
            target_only_count=result.target_only_count,
            invalid_count=invalid_count,
            duration_seconds=duration_seconds,
        )
        repo.save_summary(summary)
        if mismatch_rows:
            repo.save_mismatches(job_id, mismatch_rows)
        repo.complete_job(job_id, datetime.now(timezone.utc))

        report = build_job_report(
            job_id=job_id,
            status="completed",
            source_name=args.source_name,
            target_name=args.target_name,
            source_count=summary.source_count,
            target_count=summary.target_count,
            matched_count=summary.matched_count,
            source_only_count=summary.source_only_count,
            target_only_count=summary.target_only_count,
            invalid_count=invalid_count,
            duration_seconds=duration_seconds,
            field_mismatches=flat_mismatches,
        )
        json_path = write_json_report(report, args.out_dir)
        csv_path = write_csv_report(report, args.out_dir)

        print(
            f"Job {job_id}: matched={summary.matched_count} "
            f"mismatched={summary.mismatched_count} "
            f"source_only={summary.source_only_count} "
            f"target_only={summary.target_only_count} invalid={invalid_count} "
            f"duration={duration_seconds}s"
        )
        print(f"Reports written to {json_path} and {csv_path}")
    except Exception as exc:
        logger.exception("reconciliation job %s failed", job_id)
        try:
            repo.fail_job(job_id, datetime.now(timezone.utc), str(exc))
        except Exception:
            logger.exception("additionally failed to record job %s as failed", job_id)
        raise
    finally:
        repo.close()


def build_parser():
    ap = argparse.ArgumentParser(description="Data reconciliation and validation platform")
    sub = ap.add_subparsers(dest="command")

    demo_ap = sub.add_parser("demo", help="Run the 5-source order reconciliation demo")
    demo_ap.add_argument("--data-dir", default="data/sample")
    demo_ap.add_argument("--out-dir", default="output")

    run_ap = sub.add_parser("run", help="Reconcile two CSV/JSON datasets with configurable keys/rules")
    run_ap.add_argument("--source", required=True, help="Path to the source dataset (.csv or .json)")
    run_ap.add_argument("--target", required=True, help="Path to the target dataset (.csv or .json)")
    run_ap.add_argument("--source-name", default="source")
    run_ap.add_argument("--target-name", default="target")
    run_ap.add_argument("--key", action="append", required=True, help="Business key field (repeatable)")
    run_ap.add_argument(
        "--compare", action="append", default=[],
        help="field[:rule[:param]] to compare; rule in exact|numeric|date|ci (repeatable)",
    )
    run_ap.add_argument("--out-dir", default="output")
    run_ap.add_argument("--db-backend", choices=["sqlite", "oracle"], default="sqlite")
    run_ap.add_argument("--sqlite-path", default="recon.db")

    return ap


def main():
    argv = sys.argv[1:] or ["demo"]
    ap = build_parser()
    args = ap.parse_args(argv)

    if args.command == "demo":
        run_demo(args)
    elif args.command == "run":
        run_generic(args)
    else:  # pragma: no cover - argparse already restricts choices
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
