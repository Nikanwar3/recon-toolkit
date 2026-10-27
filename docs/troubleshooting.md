# Troubleshooting

For Oracle-specific issues, see the table at the end of `docs/oracle-setup.md`.

| Symptom | Likely cause / fix |
|---|---|
| `FileNotFoundError: data/sample/erp_orders.json` running `main.py demo` | Sample data isn't generated yet — run `python scripts/generate_sample_data.py` first (`tests/conftest.py` does this automatically for the test suite, but the CLI does not). |
| `app.errors.ValidationError: ... is not valid JSON` from `main.py run` | The `--source`/`--target` file isn't valid JSON (or isn't a top-level array). Validate it with `python -m json.tool <file>`. |
| `app.errors.SchemaConfigError: key field(s) [...] are not declared in field_specs` | A `--key` field wasn't also passed as a `--compare` field or otherwise declared — every key field must appear in the record schema. |
| A record silently disappears from both `matched`/`mismatched`/`source_only`/`target_only` | It was rejected by validation — check the job's `invalid_count` in the JSON report, and re-run with `--db-backend sqlite` then query `reconciliation_jobs`/`reconciliation_summaries` for details, or add logging at `DEBUG` level. |
| `sqlite3.OperationalError: database is locked` | Another process (or a previous run that didn't call `repo.close()`) still holds the SQLite file open. Only one writer at a time is supported by this backend — use Oracle for concurrent writers. |
| Matplotlib errors about no display / `$DISPLAY` | Shouldn't happen — `app/report.py` forces the `Agg` (headless) backend before importing `pyplot`. If you see this, check nothing else imports `matplotlib.pyplot` first. |
| `SOAP NumberConversion unavailable, skipping words form` in logs | Expected and harmless — the public demo SOAP endpoint is occasionally unreachable; `app/soap_client.py` degrades gracefully and omits the "audit note" line rather than failing the report. |
| `pytest -m oracle` reports all tests skipped | `ORACLE_DSN`/`ORACLE_USER`/`ORACLE_PASSWORD` aren't all set, or no Oracle instance is reachable — see `docs/oracle-setup.md`. This is the expected state in an environment with no Oracle instance. |
| `ruff check` or `mypy` fails in CI after a local change | Run `pip install -r requirements-dev.txt` then `ruff check .` / `mypy app main.py` locally before pushing — CI runs the same commands. |
| `ImportError: oracledb` when **not** using `--db-backend oracle` | Shouldn't happen — `app/db/oracle_repo.py` is only imported lazily inside `_build_repository()` when `--db-backend oracle` is selected. If you hit this elsewhere, check for a stray top-level import. |
