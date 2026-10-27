"""Oracle Database implementation of `ReconciliationRepository`.

Uses the `python-oracledb` thin driver (pure Python, no Oracle Instant
Client needed for a standard connection) and the `reconciliation_pkg`
PL/SQL package installed by `db/oracle/plsql/reconciliation_pkg.sql` for
summary and data-quality reads.

`python-oracledb` is an optional dependency (see requirements-oracle.txt),
not part of the core install -- this module is only imported when the
Oracle backend is actually selected (see `main.py --db-backend oracle`), so
the rest of the platform runs fine without an Oracle client present. See
docs/oracle-setup.md for how to provision an instance and run
db/oracle/schema.sql + db/oracle/plsql/reconciliation_pkg.sql against it.
"""
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

from ..errors import DatabaseConnectionError, TransactionError
from .base import MismatchRow, ReconciliationJob, ReconciliationRepository, ReconciliationSummary

logger = logging.getLogger(__name__)

try:
    import oracledb
except ImportError:  # pragma: no cover - exercised only when the driver is absent
    oracledb = None

_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "db" / "oracle" / "schema.sql"

# ORA-00955: name is already used by an existing object (table/index already
# present) -- treated as success so initialize_schema() is idempotent.
_ALREADY_EXISTS = "ORA-00955"
# ORA-20001 is this platform's "job not found" application error, raised by
# reconciliation_pkg (see db/oracle/plsql/reconciliation_pkg.sql).
_JOB_NOT_FOUND = "ORA-20001"


class OracleReconciliationRepository(ReconciliationRepository):
    def __init__(self, dsn: str, user: str, password: str):
        if oracledb is None:
            raise DatabaseConnectionError(
                "python-oracledb is not installed; run "
                "'pip install -r requirements-oracle.txt' to enable the Oracle backend"
            )
        try:
            self._conn = oracledb.connect(user=user, password=password, dsn=dsn)
        except oracledb.DatabaseError as exc:
            raise DatabaseConnectionError(f"could not connect to Oracle DSN {dsn!r}") from exc

    def initialize_schema(self) -> None:
        statements = [
            s.strip()
            for s in re.split(r";\s*(?:\n|$)", _SCHEMA_PATH.read_text())
            if s.strip() and not s.strip().upper().startswith("COMMIT")
        ]
        try:
            with self._conn.cursor() as cursor:
                for statement in statements:
                    try:
                        cursor.execute(statement)
                    except oracledb.DatabaseError as exc:
                        if _ALREADY_EXISTS in str(exc):
                            continue
                        raise
            self._conn.commit()
        except oracledb.DatabaseError as exc:
            self._conn.rollback()
            raise TransactionError("failed to initialize Oracle schema") from exc

    def create_job(self, job: ReconciliationJob) -> None:
        try:
            with self._conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO reconciliation_jobs
                        (job_id, source_name, target_name, status,
                         started_at, finished_at, error_message)
                    VALUES
                        (:job_id, :source_name, :target_name, :status,
                         :started_at, :finished_at, :error_message)
                    """,
                    job_id=job.job_id,
                    source_name=job.source_name,
                    target_name=job.target_name,
                    status=job.status,
                    started_at=job.started_at,
                    finished_at=job.finished_at,
                    error_message=job.error_message,
                )
            self._conn.commit()
        except oracledb.IntegrityError as exc:
            self._conn.rollback()
            raise TransactionError(f"job {job.job_id!r} already exists") from exc
        except oracledb.DatabaseError as exc:
            self._conn.rollback()
            raise TransactionError("failed to create job") from exc

    def complete_job(self, job_id: str, finished_at: datetime) -> None:
        self._update_status(job_id, "completed", finished_at, error_message=None)

    def fail_job(self, job_id: str, finished_at: datetime, error_message: str) -> None:
        self._update_status(job_id, "failed", finished_at, error_message=error_message)

    def _update_status(self, job_id, status, finished_at, error_message):
        try:
            with self._conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE reconciliation_jobs
                       SET status = :status, finished_at = :finished_at, error_message = :error_message
                     WHERE job_id = :job_id
                    """,
                    status=status, finished_at=finished_at, error_message=error_message, job_id=job_id,
                )
                if cursor.rowcount == 0:
                    self._conn.rollback()
                    raise TransactionError(f"no job found with job_id {job_id!r}")
            self._conn.commit()
        except oracledb.DatabaseError as exc:
            self._conn.rollback()
            raise TransactionError(f"failed to update job {job_id!r}") from exc

    def save_summary(self, summary: ReconciliationSummary) -> None:
        try:
            with self._conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO reconciliation_summaries
                        (job_id, source_count, target_count, matched_count, mismatched_count,
                         source_only_count, target_only_count, invalid_count, duration_seconds)
                    VALUES (:job_id, :source_count, :target_count, :matched_count, :mismatched_count,
                            :source_only_count, :target_only_count, :invalid_count, :duration_seconds)
                    """,
                    job_id=summary.job_id,
                    source_count=summary.source_count,
                    target_count=summary.target_count,
                    matched_count=summary.matched_count,
                    mismatched_count=summary.mismatched_count,
                    source_only_count=summary.source_only_count,
                    target_only_count=summary.target_only_count,
                    invalid_count=summary.invalid_count,
                    duration_seconds=summary.duration_seconds,
                )
            self._conn.commit()
        except oracledb.DatabaseError as exc:
            self._conn.rollback()
            raise TransactionError(f"failed to save summary for job {summary.job_id!r}") from exc

    def save_mismatches(self, job_id: str, mismatches: Sequence[MismatchRow]) -> None:
        rows = [
            {
                "job_id": job_id,
                "business_key": m.business_key,
                "field_name": m.field_name,
                "source_value": m.source_value,
                "target_value": m.target_value,
            }
            for m in mismatches
        ]
        try:
            with self._conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO reconciliation_mismatches
                        (job_id, business_key, field_name, source_value, target_value)
                    VALUES (:job_id, :business_key, :field_name, :source_value, :target_value)
                    """,
                    rows,
                )
            self._conn.commit()
        except oracledb.DatabaseError as exc:
            self._conn.rollback()
            raise TransactionError(
                f"failed to save mismatches for job {job_id!r}; transaction rolled back"
            ) from exc

    def get_job(self, job_id: str) -> Optional[ReconciliationJob]:
        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT job_id, source_name, target_name, status, started_at, finished_at, error_message
                  FROM reconciliation_jobs WHERE job_id = :job_id
                """,
                job_id=job_id,
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return ReconciliationJob(
            job_id=row[0], source_name=row[1], target_name=row[2], status=row[3],
            started_at=row[4], finished_at=row[5], error_message=row[6],
        )

    def get_summary(self, job_id: str) -> Optional[ReconciliationSummary]:
        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT job_id, source_count, target_count, matched_count, mismatched_count,
                       source_only_count, target_only_count, invalid_count, duration_seconds
                  FROM reconciliation_summaries WHERE job_id = :job_id
                """,
                job_id=job_id,
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return ReconciliationSummary(
            job_id=row[0], source_count=row[1], target_count=row[2], matched_count=row[3],
            mismatched_count=row[4], source_only_count=row[5], target_only_count=row[6],
            invalid_count=row[7], duration_seconds=row[8],
        )

    def list_jobs(self, limit: int = 20) -> List[ReconciliationJob]:
        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT job_id, source_name, target_name, status, started_at, finished_at, error_message
                  FROM reconciliation_jobs ORDER BY started_at DESC
                  FETCH FIRST :limit ROWS ONLY
                """,
                limit=limit,
            )
            rows = cursor.fetchall()
        return [
            ReconciliationJob(
                job_id=row[0], source_name=row[1], target_name=row[2], status=row[3],
                started_at=row[4], finished_at=row[5], error_message=row[6],
            )
            for row in rows
        ]

    def get_match_rate(self, job_id: str) -> Optional[float]:
        """Calls `reconciliation_pkg.get_match_rate` -- a PL/SQL-side
        calculation rather than a Python re-implementation, so the business
        rule for "what counts as a healthy match rate" lives in one place
        (the database) regardless of which client calls it."""
        result = self._conn.cursor().callfunc(
            "reconciliation_pkg.get_match_rate", oracledb.DB_TYPE_NUMBER, [job_id]
        )
        return float(result) if result is not None else None

    def run_data_quality_check(self, job_id: str) -> List[tuple]:
        """Calls `reconciliation_pkg.run_data_quality_check`, which returns
        mismatch counts grouped by field via a ref cursor."""
        cursor = self._conn.cursor()
        out_cursor = cursor.var(oracledb.CURSOR)
        try:
            cursor.callproc("reconciliation_pkg.run_data_quality_check", [job_id, out_cursor])
            return list(out_cursor.getvalue())
        except oracledb.DatabaseError as exc:
            if _JOB_NOT_FOUND in str(exc):
                return []
            raise

    def close(self) -> None:
        self._conn.close()
