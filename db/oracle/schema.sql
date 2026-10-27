-- Oracle Database schema for reconciliation job metadata and results.
-- Functionally equivalent to db/sqlite/schema.sql but using Oracle types
-- and syntax (IDENTITY columns, TIMESTAMP WITH TIME ZONE, named
-- constraints). Run as the application schema owner, e.g.:
--   sqlplus recon_app/<password>@//localhost:1521/XEPDB1 @db/oracle/schema.sql
--
-- See docs/oracle-setup.md for how to provision the schema owner and
-- docs/database-schema.md for the full data dictionary.

CREATE TABLE reconciliation_jobs (
    job_id          VARCHAR2(64)  NOT NULL,
    source_name     VARCHAR2(128) NOT NULL,
    target_name     VARCHAR2(128) NOT NULL,
    status          VARCHAR2(16)  NOT NULL,
    started_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    finished_at     TIMESTAMP WITH TIME ZONE,
    error_message   VARCHAR2(4000),
    CONSTRAINT pk_reconciliation_jobs PRIMARY KEY (job_id),
    CONSTRAINT chk_job_status CHECK (status IN ('running', 'completed', 'failed'))
);

CREATE INDEX idx_jobs_status     ON reconciliation_jobs (status);
CREATE INDEX idx_jobs_started_at ON reconciliation_jobs (started_at);

CREATE TABLE reconciliation_summaries (
    job_id              VARCHAR2(64)   NOT NULL,
    source_count        NUMBER(10)     NOT NULL,
    target_count        NUMBER(10)     NOT NULL,
    matched_count       NUMBER(10)     NOT NULL,
    mismatched_count    NUMBER(10)     NOT NULL,
    source_only_count   NUMBER(10)     NOT NULL,
    target_only_count   NUMBER(10)     NOT NULL,
    invalid_count       NUMBER(10)     NOT NULL,
    duration_seconds    NUMBER(12, 3)  NOT NULL,
    CONSTRAINT pk_reconciliation_summaries PRIMARY KEY (job_id),
    CONSTRAINT fk_summary_job FOREIGN KEY (job_id)
        REFERENCES reconciliation_jobs (job_id) ON DELETE CASCADE,
    CONSTRAINT chk_summary_counts CHECK (
        source_count >= 0 AND target_count >= 0 AND matched_count >= 0 AND
        mismatched_count >= 0 AND source_only_count >= 0 AND
        target_only_count >= 0 AND invalid_count >= 0 AND duration_seconds >= 0
    )
);

CREATE TABLE reconciliation_mismatches (
    id              NUMBER GENERATED ALWAYS AS IDENTITY,
    job_id          VARCHAR2(64)   NOT NULL,
    business_key    VARCHAR2(256)  NOT NULL,
    field_name      VARCHAR2(128)  NOT NULL,
    source_value    VARCHAR2(4000),
    target_value    VARCHAR2(4000),
    CONSTRAINT pk_reconciliation_mismatches PRIMARY KEY (id),
    CONSTRAINT fk_mismatch_job FOREIGN KEY (job_id)
        REFERENCES reconciliation_jobs (job_id) ON DELETE CASCADE
);

CREATE INDEX idx_mismatches_job_id    ON reconciliation_mismatches (job_id);
CREATE INDEX idx_mismatches_field     ON reconciliation_mismatches (field_name);

COMMIT;
