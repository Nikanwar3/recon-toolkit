"""SQLite implementation of `ReconciliationRepository`.

Uses stdlib `sqlite3` directly (no ORM) with parameterized queries
throughout -- every value is passed as a bind parameter, never interpolated
into SQL text, so this is not vulnerable to SQL injection even though the
inputs (job ids, business keys, field values) ultimately come from external
data files. Used for local development and CI; `oracle_repo.py` implements
the same interface against Oracle Database.
"""
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

from ..errors import DatabaseConnectionError, TransactionError
from .base import MismatchRow, ReconciliationJob, ReconciliationRepository, ReconciliationSummary

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "db" / "sqlite" / "schema.sql"


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _parse_iso(text: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(text) if text else None


class SqliteReconciliationRepository(ReconciliationRepository):
    def __init__(self, db_path: str):
        self.db_path = db_path
        try:
            self._conn = sqlite3.connect(db_path)
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            raise DatabaseConnectionError(f"could not open SQLite database at {db_path!r}") from exc

    def initialize_schema(self) -> None:
        schema_sql = _SCHEMA_PATH.read_text()
        try:
            with self._conn:
                self._conn.executescript(schema_sql)
        except sqlite3.Error as exc:
            raise TransactionError("failed to initialize schema") from exc

    def create_job(self, job: ReconciliationJob) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO reconciliation_jobs
                        (job_id, source_name, target_name, status, started_at, finished_at, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.job_id,
                        job.source_name,
                        job.target_name,
                        job.status,
                        _iso(job.started_at),
                        _iso(job.finished_at),
                        job.error_message,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise TransactionError(f"job {job.job_id!r} already exists") from exc
        except sqlite3.Error as exc:
            raise TransactionError("failed to create job") from exc

    def complete_job(self, job_id: str, finished_at: datetime) -> None:
        self._update_status(job_id, "completed", finished_at, error_message=None)

    def fail_job(self, job_id: str, finished_at: datetime, error_message: str) -> None:
        self._update_status(job_id, "failed", finished_at, error_message=error_message)

    def _update_status(self, job_id, status, finished_at, error_message):
        try:
            with self._conn:
                cursor = self._conn.execute(
                    """
                    UPDATE reconciliation_jobs
                       SET status = ?, finished_at = ?, error_message = ?
                     WHERE job_id = ?
                    """,
                    (status, _iso(finished_at), error_message, job_id),
                )
                if cursor.rowcount == 0:
                    raise TransactionError(f"no job found with job_id {job_id!r}")
        except sqlite3.Error as exc:
            raise TransactionError(f"failed to update job {job_id!r}") from exc

    def save_summary(self, summary: ReconciliationSummary) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO reconciliation_summaries
                        (job_id, source_count, target_count, matched_count, mismatched_count,
                         source_only_count, target_only_count, invalid_count, duration_seconds)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        summary.job_id,
                        summary.source_count,
                        summary.target_count,
                        summary.matched_count,
                        summary.mismatched_count,
                        summary.source_only_count,
                        summary.target_only_count,
                        summary.invalid_count,
                        summary.duration_seconds,
                    ),
                )
        except sqlite3.Error as exc:
            raise TransactionError(f"failed to save summary for job {summary.job_id!r}") from exc

    def save_mismatches(self, job_id: str, mismatches: Sequence[MismatchRow]) -> None:
        rows = [(job_id, m.business_key, m.field_name, m.source_value, m.target_value) for m in mismatches]
        try:
            with self._conn:
                self._conn.executemany(
                    """
                    INSERT INTO reconciliation_mismatches
                        (job_id, business_key, field_name, source_value, target_value)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    rows,
                )
        except sqlite3.Error as exc:
            # The `with self._conn:` block rolls back automatically on
            # exception -- a partial batch never lands. Re-raised as a
            # typed error so callers can distinguish this from bad input.
            raise TransactionError(
                f"failed to save mismatches for job {job_id!r}; transaction rolled back"
            ) from exc

    def get_job(self, job_id: str) -> Optional[ReconciliationJob]:
        row = self._conn.execute(
            "SELECT * FROM reconciliation_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        return ReconciliationJob(
            job_id=row["job_id"],
            source_name=row["source_name"],
            target_name=row["target_name"],
            status=row["status"],
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=_parse_iso(row["finished_at"]),
            error_message=row["error_message"],
        )

    def get_summary(self, job_id: str) -> Optional[ReconciliationSummary]:
        row = self._conn.execute(
            "SELECT * FROM reconciliation_summaries WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        return ReconciliationSummary(
            job_id=row["job_id"],
            source_count=row["source_count"],
            target_count=row["target_count"],
            matched_count=row["matched_count"],
            mismatched_count=row["mismatched_count"],
            source_only_count=row["source_only_count"],
            target_only_count=row["target_only_count"],
            invalid_count=row["invalid_count"],
            duration_seconds=row["duration_seconds"],
        )

    def list_jobs(self, limit: int = 20) -> List[ReconciliationJob]:
        rows = self._conn.execute(
            "SELECT * FROM reconciliation_jobs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            ReconciliationJob(
                job_id=row["job_id"],
                source_name=row["source_name"],
                target_name=row["target_name"],
                status=row["status"],
                started_at=datetime.fromisoformat(row["started_at"]),
                finished_at=_parse_iso(row["finished_at"]),
                error_message=row["error_message"],
            )
            for row in rows
        ]

    def close(self) -> None:
        self._conn.close()
