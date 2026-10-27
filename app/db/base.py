"""Persistence interface for reconciliation job metadata and summaries.

Two concrete implementations exist behind this interface:
`SqliteReconciliationRepository` (stdlib `sqlite3`, used for local dev/CI)
and `OracleReconciliationRepository` (`python-oracledb`, in `oracle_repo.py`,
used when an Oracle instance is configured). Business logic in
`app.reconciliation` and `main.py` depends only on this interface, never on
a specific driver, so the backend is a deployment choice, not a code change.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence


@dataclass
class ReconciliationJob:
    job_id: str
    source_name: str
    target_name: str
    status: str  # "running" | "completed" | "failed"
    started_at: datetime
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None


@dataclass
class ReconciliationSummary:
    job_id: str
    source_count: int
    target_count: int
    matched_count: int
    mismatched_count: int
    source_only_count: int
    target_only_count: int
    invalid_count: int
    duration_seconds: float


@dataclass
class MismatchRow:
    business_key: str
    field_name: str
    source_value: Optional[str]
    target_value: Optional[str]


class ReconciliationRepository(ABC):
    @abstractmethod
    def initialize_schema(self) -> None:
        """Create tables/indexes if they do not already exist. Idempotent."""

    @abstractmethod
    def create_job(self, job: ReconciliationJob) -> None:
        """Insert a new job row in 'running' status."""

    @abstractmethod
    def complete_job(self, job_id: str, finished_at: datetime) -> None:
        """Mark a job 'completed'."""

    @abstractmethod
    def fail_job(self, job_id: str, finished_at: datetime, error_message: str) -> None:
        """Mark a job 'failed' with a diagnostic message (no record contents)."""

    @abstractmethod
    def save_summary(self, summary: ReconciliationSummary) -> None:
        """Persist the aggregate counts for a completed job."""

    @abstractmethod
    def save_mismatches(self, job_id: str, mismatches: Sequence[MismatchRow]) -> None:
        """Persist field-level mismatches for a job, in a single transaction."""

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[ReconciliationJob]:
        """Fetch a job by id, or None if it does not exist."""

    @abstractmethod
    def get_summary(self, job_id: str) -> Optional[ReconciliationSummary]:
        """Fetch a job's summary by id, or None if it does not exist."""

    @abstractmethod
    def list_jobs(self, limit: int = 20) -> List[ReconciliationJob]:
        """Most recent jobs first."""

    @abstractmethod
    def close(self) -> None:
        """Release the underlying connection."""

    def __enter__(self) -> "ReconciliationRepository":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
