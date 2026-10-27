-- SQLite schema for reconciliation job metadata and results.
-- Used for local development and CI. See db/oracle/schema.sql for the
-- Oracle Database equivalent used in production-style deployments.

CREATE TABLE IF NOT EXISTS reconciliation_jobs (
    job_id          TEXT PRIMARY KEY,
    source_name     TEXT NOT NULL,
    target_name     TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status      ON reconciliation_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_started_at  ON reconciliation_jobs(started_at);

CREATE TABLE IF NOT EXISTS reconciliation_summaries (
    job_id              TEXT PRIMARY KEY REFERENCES reconciliation_jobs(job_id) ON DELETE CASCADE,
    source_count        INTEGER NOT NULL CHECK (source_count >= 0),
    target_count        INTEGER NOT NULL CHECK (target_count >= 0),
    matched_count        INTEGER NOT NULL CHECK (matched_count >= 0),
    mismatched_count    INTEGER NOT NULL CHECK (mismatched_count >= 0),
    source_only_count   INTEGER NOT NULL CHECK (source_only_count >= 0),
    target_only_count   INTEGER NOT NULL CHECK (target_only_count >= 0),
    invalid_count       INTEGER NOT NULL CHECK (invalid_count >= 0),
    duration_seconds    REAL NOT NULL CHECK (duration_seconds >= 0)
);

CREATE TABLE IF NOT EXISTS reconciliation_mismatches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL REFERENCES reconciliation_jobs(job_id) ON DELETE CASCADE,
    business_key    TEXT NOT NULL,
    field_name      TEXT NOT NULL,
    source_value    TEXT,
    target_value    TEXT
);

CREATE INDEX IF NOT EXISTS idx_mismatches_job_id ON reconciliation_mismatches(job_id);
