import csv
import json

from app.report import build_job_report, write_csv_report, write_json_report


def _sample_report():
    return build_job_report(
        job_id="job-123",
        status="completed",
        source_name="erp",
        target_name="finance",
        source_count=10,
        target_count=9,
        matched_count=7,
        source_only_count=2,
        target_only_count=1,
        invalid_count=0,
        duration_seconds=0.1234,
        field_mismatches=[
            {"business_key": "ORD-1", "field": "amount", "source_value": 100.0, "target_value": 150.0},
        ],
    )


def test_build_job_report_contains_all_required_fields():
    report = _sample_report()
    for key in (
        "job_id", "status", "source_count", "target_count", "matched_count",
        "source_only_count", "target_only_count", "invalid_count",
        "duration_seconds", "field_mismatches", "error_summary",
    ):
        assert key in report


def test_mismatched_count_is_derived_from_distinct_business_keys():
    report = build_job_report(
        job_id="job-1", status="completed", source_name="s", target_name="t",
        source_count=1, target_count=1, matched_count=0, source_only_count=0,
        target_only_count=0, invalid_count=0, duration_seconds=0.0,
        field_mismatches=[
            {"business_key": "ORD-1", "field": "amount", "source_value": 1, "target_value": 2},
            {"business_key": "ORD-1", "field": "status", "source_value": "A", "target_value": "B"},
        ],
    )
    # Two field mismatches on the SAME order -> one mismatched record.
    assert report["mismatched_count"] == 1


def test_write_json_report_round_trips(tmp_path):
    report = _sample_report()
    path = write_json_report(report, tmp_path)
    assert path.exists()
    loaded = json.loads(path.read_text())
    assert loaded["job_id"] == "job-123"
    assert loaded["field_mismatches"][0]["field"] == "amount"


def test_write_csv_report_contains_mismatch_rows(tmp_path):
    report = _sample_report()
    path = write_csv_report(report, tmp_path)
    assert path.exists()
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["business_key"] == "ORD-1"
    assert rows[0]["field"] == "amount"


def test_write_csv_report_with_no_mismatches_writes_header_only(tmp_path):
    report = build_job_report(
        job_id="job-clean", status="completed", source_name="s", target_name="t",
        source_count=5, target_count=5, matched_count=5, source_only_count=0,
        target_only_count=0, invalid_count=0, duration_seconds=0.01,
        field_mismatches=[],
    )
    path = write_csv_report(report, tmp_path)
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows == []
