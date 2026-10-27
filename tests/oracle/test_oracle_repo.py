"""Tests against a real Oracle Database instance.

These are NOT run as part of the default test suite -- they require a live
Oracle instance reachable via ORACLE_DSN/ORACLE_USER/ORACLE_PASSWORD, with
db/oracle/schema.sql and db/oracle/plsql/reconciliation_pkg.sql already
installed (see docs/oracle-setup.md). They have not been executed in this
development environment, which has no Oracle instance available; they are
provided to run in any environment that does.

Run explicitly with:
    ORACLE_DSN=... ORACLE_USER=... ORACLE_PASSWORD=... pytest -m oracle
The default `pytest` invocation (no -m) excludes them via conftest.py.
"""
import os
from datetime import datetime, timezone

import pytest

from app.db.base import MismatchRow, ReconciliationJob, ReconciliationSummary
from app.errors import TransactionError

ORACLE_DSN = os.environ.get("ORACLE_DSN")
ORACLE_USER = os.environ.get("ORACLE_USER")
ORACLE_PASSWORD = os.environ.get("ORACLE_PASSWORD")

pytestmark = [
    pytest.mark.oracle,
    pytest.mark.skipif(
        not all([ORACLE_DSN, ORACLE_USER, ORACLE_PASSWORD]),
        reason="requires ORACLE_DSN, ORACLE_USER, ORACLE_PASSWORD for a live Oracle instance",
    ),
]


@pytest.fixture
def repo():
    from app.db.oracle_repo import OracleReconciliationRepository

    r = OracleReconciliationRepository(dsn=ORACLE_DSN, user=ORACLE_USER, password=ORACLE_PASSWORD)
    yield r
    r.close()


def _job(job_id):
    return ReconciliationJob(
        job_id=job_id, source_name="erp", target_name="finance", status="running",
        started_at=datetime.now(timezone.utc),
    )


def test_create_and_get_job_round_trips(repo):
    job_id = "oracle-test-job-1"
    repo.create_job(_job(job_id))
    fetched = repo.get_job(job_id)
    assert fetched is not None
    assert fetched.source_name == "erp"


def test_duplicate_job_id_raises_transaction_error(repo):
    job_id = "oracle-test-job-dup"
    repo.create_job(_job(job_id))
    with pytest.raises(TransactionError):
        repo.create_job(_job(job_id))


def test_save_summary_and_get_match_rate_via_plsql(repo):
    job_id = "oracle-test-job-match-rate"
    repo.create_job(_job(job_id))
    repo.save_summary(ReconciliationSummary(
        job_id=job_id, source_count=10, target_count=10, matched_count=8,
        mismatched_count=2, source_only_count=0, target_only_count=0,
        invalid_count=0, duration_seconds=0.5,
    ))
    rate = repo.get_match_rate(job_id)
    assert rate == 80.0


def test_data_quality_check_groups_mismatches_by_field(repo):
    job_id = "oracle-test-job-dq"
    repo.create_job(_job(job_id))
    repo.save_mismatches(job_id, [
        MismatchRow("ORD-1", "amount", "100", "150"),
        MismatchRow("ORD-2", "amount", "200", "250"),
        MismatchRow("ORD-3", "status", "OPEN", "CLOSED"),
    ])
    rows = repo.run_data_quality_check(job_id)
    as_dict = dict(rows)
    assert as_dict["amount"] == 2
    assert as_dict["status"] == 1


def test_save_mismatches_rolls_back_on_foreign_key_violation(repo):
    with pytest.raises(TransactionError):
        repo.save_mismatches("job-id-that-does-not-exist", [
            MismatchRow("ORD-1", "amount", "100", "150"),
        ])
