# Database Schema

The reconciliation platform persists job metadata, aggregate summaries, and
field-level mismatches for every run of `main.py run`. Two equivalent
schemas exist: `db/sqlite/schema.sql` (local dev/CI) and
`db/oracle/schema.sql` (production-style deployment). Both are accessed
through the same `app.db.ReconciliationRepository` interface
(`app/db/base.py`), so application code never branches on which database is
in use.

The 5-source demo (`main.py demo`) does not use the database at all — it
remains file-in, file-out, unchanged from before this upgrade.

## Tables

### `reconciliation_jobs`

One row per invocation of `main.py run`.

| Column          | Type (SQLite / Oracle)              | Notes                                      |
|-----------------|--------------------------------------|---------------------------------------------|
| `job_id`        | `TEXT` / `VARCHAR2(64)` PK           | UUID4, generated per run                    |
| `source_name`   | `TEXT` / `VARCHAR2(128)` NOT NULL    | Human-readable label, e.g. `"erp"`          |
| `target_name`   | `TEXT` / `VARCHAR2(128)` NOT NULL    | Human-readable label, e.g. `"finance"`      |
| `status`        | `TEXT` / `VARCHAR2(16)` NOT NULL     | `running` \| `completed` \| `failed` (CHECK)|
| `started_at`    | `TEXT` ISO8601 / `TIMESTAMP WITH TIME ZONE` | Set on creation                      |
| `finished_at`   | nullable, same type as `started_at`  | Set on completion or failure                |
| `error_message` | `TEXT` / `VARCHAR2(4000)` nullable   | Set only on failure; never record contents  |

Indexes: `status` (for dashboards/queries by state), `started_at` (for
`list_jobs()` and Oracle's `purge_old_jobs`).

### `reconciliation_summaries`

One row per job, 1:1 with `reconciliation_jobs` (`ON DELETE CASCADE`).

| Column                | Notes                                             |
|-----------------------|----------------------------------------------------|
| `job_id`              | PK, FK -> `reconciliation_jobs.job_id`            |
| `source_count`        | Rows loaded from the source file                   |
| `target_count`        | Rows loaded from the target file                   |
| `matched_count`       | Same key, all compared fields equal                |
| `mismatched_count`    | Same key, at least one compared field differs      |
| `source_only_count`   | Key present only in source                         |
| `target_only_count`   | Key present only in target                         |
| `invalid_count`       | Rows rejected by validation (either side, combined)|
| `duration_seconds`    | Wall-clock time for the reconciliation step         |

All count columns have a `CHECK (... >= 0)` constraint.

### `reconciliation_mismatches`

One row per (business key, field) that disagreed. A record with 3
mismatched fields produces 3 rows here, all sharing the same
`business_key`.

| Column         | Notes                                              |
|----------------|------------------------------------------------------|
| `id`           | Surrogate PK (`AUTOINCREMENT` / `GENERATED ALWAYS AS IDENTITY`) |
| `job_id`       | FK -> `reconciliation_jobs.job_id`, `ON DELETE CASCADE` |
| `business_key` | The configured key fields, joined with `\|`          |
| `field_name`   | Which compared field disagreed                       |
| `source_value` | Stringified source-side value                        |
| `target_value` | Stringified target-side value                        |

Indexed on `job_id` (lookup by job) and, on Oracle, additionally on
`field_name` (for `reconciliation_pkg.run_data_quality_check`'s
`GROUP BY field_name`).

## Why no ORM

Both repository implementations use hand-written, parameterized SQL
(`sqlite3` / `python-oracledb`) rather than an ORM. This is a deliberate
choice for a platform meant to demonstrate direct SQL and PL/SQL fluency,
not a limitation — every query is visible in `app/db/sqlite_repo.py` and
`app/db/oracle_repo.py`.

## Migration process

There is no migration framework (Alembic etc.) — that would be
overengineering for three tables. Instead:

- `db/sqlite/schema.sql` and `db/oracle/schema.sql` are the single source
  of truth for each backend's structure, applied via
  `CREATE TABLE IF NOT EXISTS` (SQLite) or a `CREATE TABLE` + "already
  exists" tolerance (Oracle, see `OracleReconciliationRepository.initialize_schema`)
  so re-running them is safe.
- A schema *change* (new column, new constraint) is a direct edit to the
  relevant `schema.sql`, applied with `ALTER TABLE` by hand against any
  existing database, and the corresponding repository method updated in
  the same commit. For a project this size, a migration tool would add a
  dependency and a learning curve without a corresponding benefit over "the
  SQL files are the schema, and the repo classes are reviewed in the same
  diff."
- Oracle schema/PL/SQL changes are applied with `sqlplus ... @db/oracle/schema.sql`
  and `@db/oracle/plsql/reconciliation_pkg.sql` — see `docs/oracle-setup.md`.
