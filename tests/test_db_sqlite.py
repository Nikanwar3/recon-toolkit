from datetime import datetime, timezone

import pytest

from app.db.base import MismatchRow, ReconciliationJob, ReconciliationSummary
from app.db.sqlite_repo import SqliteReconciliationRepository
from app.errors import TransactionError


@pytest.fixture
def repo(tmp_path):
    db_path = tmp_path / "recon_test.db"
    r = SqliteReconciliationRepository(str(db_path))
    r.initialize_schema()
    yield r
    r.close()


def _job(job_id="job-1", status="running"):
    return ReconciliationJob(
        job_id=job_id,
        source_name="erp",
        target_name="finance",
        status=status,
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_initialize_schema_is_idempotent(repo):
    repo.initialize_schema()  # second call must not raise
    repo.initialize_schema()


def test_create_and_get_job_round_trips(repo):
    repo.create_job(_job())
    fetched = repo.get_job("job-1")
    assert fetched is not None
    assert fetched.source_name == "erp"
    assert fetched.status == "running"


def test_get_job_returns_none_for_unknown_id(repo):
    assert repo.get_job("does-not-exist") is None


def test_create_duplicate_job_id_raises_transaction_error(repo):
    repo.create_job(_job())
    with pytest.raises(TransactionError):
        repo.create_job(_job())  # same job_id -> primary key violation


def test_complete_job_updates_status_and_finished_at(repo):
    repo.create_job(_job())
    finished = datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc)
    repo.complete_job("job-1", finished)
    fetched = repo.get_job("job-1")
    assert fetched.status == "completed"
    assert fetched.finished_at == finished


def test_fail_job_records_error_message(repo):
    repo.create_job(_job())
    repo.fail_job("job-1", datetime.now(timezone.utc), "source file not found")
    fetched = repo.get_job("job-1")
    assert fetched.status == "failed"
    assert fetched.error_message == "source file not found"


def test_update_status_on_unknown_job_raises(repo):
    with pytest.raises(TransactionError):
        repo.complete_job("no-such-job", datetime.now(timezone.utc))


def test_save_and_fetch_summary(repo):
    repo.create_job(_job())
    summary = ReconciliationSummary(
        job_id="job-1", source_count=10, target_count=9, matched_count=8,
        mismatched_count=1, source_only_count=1, target_only_count=0,
        invalid_count=0, duration_seconds=0.42,
    )
    repo.save_summary(summary)
    fetched = repo.get_summary("job-1")
    assert fetched.matched_count == 8
    assert fetched.duration_seconds == 0.42


def test_summary_violating_check_constraint_rolls_back(repo):
    """Negative counts violate the CHECK constraints in db/sqlite/schema.sql
    -- the insert must fail cleanly and leave no partial row behind."""
    repo.create_job(_job())
    bad_summary = ReconciliationSummary(
        job_id="job-1", source_count=-1, target_count=9, matched_count=8,
        mismatched_count=1, source_only_count=1, target_only_count=0,
        invalid_count=0, duration_seconds=0.1,
    )
    with pytest.raises(TransactionError):
        repo.save_summary(bad_summary)
    assert repo.get_summary("job-1") is None


def test_save_mismatches_batch_rolls_back_entirely_on_failure(repo):
    """One bad row (referencing a job_id that does not exist, violating the
    foreign key) must not leave the earlier rows in the same batch committed
    -- the whole executemany() is one transaction."""
    repo.create_job(_job())
    rows = [
        MismatchRow(business_key="1", field_name="amount", source_value="100", target_value="150"),
        MismatchRow(business_key="2", field_name="status", source_value="OPEN", target_value="CLOSED"),
    ]
    with pytest.raises(TransactionError):
        repo.save_mismatches("job-that-does-not-exist", rows)

    # Nothing from the failed batch should be visible under the real job.
    repo.save_mismatches("job-1", rows)
    cursor = repo._conn.execute(
        "SELECT COUNT(*) FROM reconciliation_mismatches WHERE job_id = 'job-that-does-not-exist'"
    )
    assert cursor.fetchone()[0] == 0


def test_list_jobs_orders_most_recent_first(repo):
    repo.create_job(ReconciliationJob(
        job_id="job-a", source_name="s", target_name="t", status="running",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    ))
    repo.create_job(ReconciliationJob(
        job_id="job-b", source_name="s", target_name="t", status="running",
        started_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    ))
    jobs = repo.list_jobs()
    assert [j.job_id for j in jobs] == ["job-b", "job-a"]
