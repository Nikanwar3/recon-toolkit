# Root Cause Analysis

Four reproducible failure scenarios from this codebase: two are real defects
found and fixed during this upgrade (not production incidents — this
project has no production deployment), and two are simulated infrastructure
failures exercised by the test suite. Each is labeled accordingly.

---

## Scenario 1 — Duplicate business key silently overwrote a record

**Status: real defect, found during this upgrade, now fixed.**

### Symptoms

Given two sources `sys_a` and `sys_b` where `sys_a` exports two records
under the same `order_id` (an upstream export bug, or two partial batches
concatenated into one file), reconciliation would report either zero
discrepancies or the wrong discrepancy, depending on dict insertion order —
whichever `sys_a` record happened to be inserted last into the merge dict
silently won, with no warning that a duplicate existed at all.

### Steps to reproduce (pre-fix behavior)

```python
from app.reconcile import reconcile

a = [
    {"order_id": "ORD-1", "customer": "Acme", "amount": 100.0, "status": "SHIPPED", "date": "2026-01-01"},
    {"order_id": "ORD-1", "customer": "Acme", "amount": 999.0, "status": "SHIPPED", "date": "2026-01-01"},
]
b = [{"order_id": "ORD-1", "customer": "Acme", "amount": 100.0, "status": "SHIPPED", "date": "2026-01-01"}]

reconcile({"sys_a": a, "sys_b": b})
# Pre-fix: returned [] (no discrepancy) if dict insertion happened to keep
# the first record, or a $899 amount discrepancy if it kept the second --
# non-deterministic from the caller's point of view, and either way, no
# signal that sys_a had sent two records for the same order_id at all.
```

### Root cause

`merge_by_order_id()` in `app/reconcile.py` built the merge dict with
`merged[rec["order_id"]][source_name] = rec` inside a plain loop over each
source's records. A second record for the same `order_id` within the same
source simply overwrote the dict entry for that `(order_id, source_name)`
key — there was no duplicate check at all.

### Corrective action

`merge_by_order_id()` now tracks `order_id`s already seen *within the
current source* and keeps only the first occurrence, logging a warning
(`duplicate order_id %r in source %r; keeping first occurrence`) so the
condition is visible in logs instead of silent. The same duplicate-key
problem is handled more thoroughly in the newer generic engine's input path
(`app/validation.validate_records`), which routes every duplicate into the
`invalid` bucket (reason `duplicate_key`) so it is visible in the job report
rather than only in logs.

### Regression test

`tests/test_reconcile.py::test_duplicate_order_id_within_one_source_keeps_first_record`
and `tests/test_validation.py::test_duplicate_business_key_keeps_first_flags_rest`.

---

## Scenario 2 — Malformed record raised an opaque exception instead of a typed, reportable error

**Status: real defect, found during this upgrade, now fixed.**

### Symptoms

A single record missing a required field (e.g. `amount`), or an
`amount` that doesn't parse as a number, crashed the whole loader with a
bare `KeyError` or `ValueError` and no indication of *which* record or
field was the problem — the entire reconciliation run aborted rather than
flagging just the one bad record.

### Steps to reproduce (pre-fix behavior)

```python
from app.loaders.schema import normalize_record

normalize_record({"order_id": "ORD-1", "customer": "Acme", "status": "SHIPPED", "date": "2026-01-01"})
# Pre-fix: KeyError: 'amount' -- no context about which record/source,
# and nothing in the caller's control flow to catch "this one record is
# bad" vs. "the whole load failed."
```

### Root cause

`normalize_record()` accessed `raw["order_id"]`, `raw["amount"]`, etc.
directly with no validation, on the implicit assumption that every input
record is well-formed. That assumption never held for the generic
two-dataset engine's inputs (arbitrary CSV/JSON from an unknown source),
and the 5-source demo loaders made the same assumption about synthetic
data that happened to always be clean.

### Corrective action

`normalize_record()` now checks required fields up front and wraps the
`amount` coercion in a `try/except`, raising `app.errors.ValidationError`
(with the offending field name attached) instead of a bare built-in
exception. The generic engine's input path never raises on bad data at
all: `app.validation.validate_records` captures every per-record problem
into a `ValidationResult.invalid` list (with a machine-readable `reason`
per record) and lets the valid records proceed, so one malformed row in a
10,000-row file no longer aborts the entire job.

### Regression test

`tests/test_validation.py::test_missing_required_field_is_invalid_not_a_crash`,
`test_invalid_type_is_captured_as_invalid_record`, and the generic-run
fixture exercised manually (duplicate + missing-amount CSV; see the CLI
example in `README.md`).

---

## Scenario 3 — Partial mismatch batch left behind after a failed insert

**Status: real behavior, exercised by an automated test; not an incident (no partial data has ever reached a real database through this code path) — documented because getting the transaction boundary right here is easy to get wrong.**

### Symptoms

If `save_mismatches()` is ever called for a `job_id` that doesn't exist yet
in `reconciliation_jobs` (for example, a future caller that persists
mismatches before creating the job row, or a job row that gets purged
mid-run by `reconciliation_pkg.purge_old_jobs` on Oracle), every row in
that batch violates the foreign key — the risk is a partial write, where
some rows in the batch land before the failing row is hit.

### Steps to reproduce

```python
from app.db.sqlite_repo import SqliteReconciliationRepository
from app.db.base import MismatchRow

repo = SqliteReconciliationRepository(":memory:")
repo.initialize_schema()
repo.save_mismatches("job-that-does-not-exist", [
    MismatchRow("ORD-1", "amount", "100", "150"),
    MismatchRow("ORD-2", "status", "OPEN", "CLOSED"),
])
# Raises app.errors.TransactionError
```

### Root cause

Without an explicit transaction boundary, `executemany()` over multiple
rows could commit earlier rows before failing on a later one (or, with
autocommit per-statement, leave the table in a half-written state for that
batch).

### Corrective action

`save_mismatches()` runs the whole batch inside a single `with self._conn:`
block (SQLite) / explicit `commit()`-only-on-full-success with `rollback()`
in the `except` branch (Oracle) — a `sqlite3.Error` anywhere in the batch
rolls back everything already executed in that `with` block, so the table
only ever contains fully-successful batches for a given call. Verified by
asserting zero rows exist under the failed `job_id` afterward, and that a
subsequent call with a *valid* `job_id` still succeeds (the connection
isn't left in a broken state by the rollback).

### Regression test

`tests/test_db_sqlite.py::test_save_mismatches_batch_rolls_back_entirely_on_failure`
and `::test_summary_violating_check_constraint_rolls_back`.

---

## Scenario 4 — Oracle backend selected without the driver installed or credentials configured

**Status: simulated — this development environment has no Oracle Database instance available, so this is a deliberately triggered configuration error, not an observed Oracle outage.**

### Symptoms

Running `python main.py run --db-backend oracle ...` without
`python-oracledb` installed, or without `ORACLE_DSN`/`ORACLE_USER`/
`ORACLE_PASSWORD` set, should fail immediately with a clear, actionable
message — not a stack trace buried inside the driver, and not a silent
fallback to a different backend.

### Steps to reproduce

```bash
# python-oracledb not installed (core requirements.txt doesn't include it):
python main.py run --source a.csv --target b.csv --key id --db-backend oracle

# or, with the driver installed but no credentials:
unset ORACLE_DSN ORACLE_USER ORACLE_PASSWORD
python main.py run --source a.csv --target b.csv --key id --db-backend oracle
```

### Root cause

`oracledb` is an optional dependency (`requirements-oracle.txt`), so
`import oracledb` can fail at runtime, and Oracle credentials are
necessarily environment-specific and must never be hardcoded or defaulted.

### Corrective action

`OracleReconciliationRepository.__init__` checks `oracledb is None` first
and raises `DatabaseConnectionError` with the exact `pip install` command
needed, before attempting any connection. `main.py`'s `_build_repository()`
checks all three required env vars up front and raises the same typed error
naming which variables are missing, before ever importing the Oracle
module. Neither path leaks a password or DSN detail into the error message.

### Regression test

Not unit-tested directly (it would require either uninstalling a package
mid-test-run or asserting on `ImportError` machinery, both of which test
the Python import system more than this code) — verified manually:

```bash
$ python main.py run --source a.csv --target b.csv --key id --db-backend oracle
app.errors.DatabaseConnectionError: ORACLE_DSN, ORACLE_USER and ORACLE_PASSWORD env vars
must all be set to use --db-backend oracle (see docs/oracle-setup.md)
```

See `docs/oracle-setup.md` for provisioning a real instance so Scenario 4
can be re-tested against an actual unreachable DSN rather than a missing
one.
