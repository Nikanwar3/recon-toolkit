-- PL/SQL package providing server-side reconciliation summary and
-- data-quality reporting on top of the schema in db/oracle/schema.sql.
--
-- Install after the schema:
--   sqlplus recon_app/<password>@//localhost:1521/XEPDB1 @db/oracle/plsql/reconciliation_pkg.sql
--
-- These procedures are intentionally server-side (not re-implemented in
-- Python) to demonstrate genuine PL/SQL usage: a ref cursor for the
-- summary join, a pipelined-style aggregation for data-quality, named
-- exceptions with RAISE_APPLICATION_ERROR, and explicit transaction
-- control on the maintenance procedure.

CREATE OR REPLACE PACKAGE reconciliation_pkg AS

    -- Application-specific error codes (reserved range -20000..-20099).
    e_job_not_found EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_job_not_found, -20001);

    -- Returns one row joining a job with its summary counts.
    -- Raises e_job_not_found (-20001) if p_job_id does not exist.
    PROCEDURE get_job_summary(
        p_job_id   IN  reconciliation_jobs.job_id%TYPE,
        o_cursor   OUT SYS_REFCURSOR
    );

    -- Matched / (matched + mismatched + source_only + target_only), as a
    -- percentage. Returns NULL (not an error) when a job has zero
    -- comparable records, since 0/0 is not a data-quality signal.
    FUNCTION get_match_rate(
        p_job_id IN reconciliation_jobs.job_id%TYPE
    ) RETURN NUMBER;

    -- Data-quality report: for a given job, how many mismatches landed on
    -- each field, most frequent first -- surfaces which upstream field is
    -- the noisiest source of disagreement.
    PROCEDURE run_data_quality_check(
        p_job_id IN  reconciliation_jobs.job_id%TYPE,
        o_report OUT SYS_REFCURSOR
    );

    -- Deletes jobs (and cascaded summaries/mismatches) older than
    -- p_older_than_days, committing only if every delete succeeds.
    -- Returns the number of jobs purged.
    FUNCTION purge_old_jobs(
        p_older_than_days IN NUMBER
    ) RETURN NUMBER;

END reconciliation_pkg;
/

CREATE OR REPLACE PACKAGE BODY reconciliation_pkg AS

    PROCEDURE get_job_summary(
        p_job_id   IN  reconciliation_jobs.job_id%TYPE,
        o_cursor   OUT SYS_REFCURSOR
    ) IS
        v_exists NUMBER;
    BEGIN
        SELECT COUNT(*) INTO v_exists
          FROM reconciliation_jobs
         WHERE job_id = p_job_id;

        IF v_exists = 0 THEN
            RAISE_APPLICATION_ERROR(-20001, 'No reconciliation job found for job_id: ' || p_job_id);
        END IF;

        OPEN o_cursor FOR
            SELECT j.job_id,
                   j.source_name,
                   j.target_name,
                   j.status,
                   j.started_at,
                   j.finished_at,
                   j.error_message,
                   s.source_count,
                   s.target_count,
                   s.matched_count,
                   s.mismatched_count,
                   s.source_only_count,
                   s.target_only_count,
                   s.invalid_count,
                   s.duration_seconds
              FROM reconciliation_jobs j
              LEFT JOIN reconciliation_summaries s ON s.job_id = j.job_id
             WHERE j.job_id = p_job_id;
    EXCEPTION
        WHEN OTHERS THEN
            IF SQLCODE != -20001 THEN
                RAISE_APPLICATION_ERROR(-20099, 'get_job_summary failed for job_id ' || p_job_id || ': ' || SQLERRM);
            END IF;
            RAISE;
    END get_job_summary;

    FUNCTION get_match_rate(
        p_job_id IN reconciliation_jobs.job_id%TYPE
    ) RETURN NUMBER IS
        v_total   NUMBER;
        v_matched NUMBER;
    BEGIN
        SELECT matched_count,
               matched_count + mismatched_count + source_only_count + target_only_count
          INTO v_matched, v_total
          FROM reconciliation_summaries
         WHERE job_id = p_job_id;

        IF v_total = 0 THEN
            RETURN NULL;
        END IF;

        RETURN ROUND((v_matched / v_total) * 100, 2);
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20001, 'No summary found for job_id: ' || p_job_id);
    END get_match_rate;

    PROCEDURE run_data_quality_check(
        p_job_id IN  reconciliation_jobs.job_id%TYPE,
        o_report OUT SYS_REFCURSOR
    ) IS
    BEGIN
        OPEN o_report FOR
            SELECT field_name,
                   COUNT(*) AS mismatch_count
              FROM reconciliation_mismatches
             WHERE job_id = p_job_id
             GROUP BY field_name
             ORDER BY mismatch_count DESC, field_name;
    EXCEPTION
        WHEN OTHERS THEN
            RAISE_APPLICATION_ERROR(-20099, 'run_data_quality_check failed for job_id ' || p_job_id || ': ' || SQLERRM);
    END run_data_quality_check;

    FUNCTION purge_old_jobs(
        p_older_than_days IN NUMBER
    ) RETURN NUMBER IS
        v_purged NUMBER := 0;
    BEGIN
        DELETE FROM reconciliation_jobs
         WHERE started_at < SYSTIMESTAMP - NUMTODSINTERVAL(p_older_than_days, 'DAY');
        v_purged := SQL%ROWCOUNT;
        COMMIT;
        RETURN v_purged;
    EXCEPTION
        WHEN OTHERS THEN
            ROLLBACK;
            RAISE_APPLICATION_ERROR(-20098, 'purge_old_jobs failed, rolled back: ' || SQLERRM);
    END purge_old_jobs;

END reconciliation_pkg;
/
