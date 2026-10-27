# Oracle Database Setup

This platform's Oracle backend (`app/db/oracle_repo.py`) has **not** been
executed against a real Oracle instance in this development environment —
no Oracle Database was available here. The code, schema, and PL/SQL package
are genuine and ready to run; this document is how to actually exercise
them, and `tests/oracle/test_oracle_repo.py` is the test suite to run once
you do.

## 1. Get an Oracle instance

The quickest path for local development is the free Oracle Database Express
Edition (XE) container:

```bash
docker run -d --name oracle-xe \
  -p 1521:1521 \
  -e ORACLE_PWD=<admin-password> \
  gvenzl/oracle-xe:21-slim
```

Wait for the container to report healthy (`docker logs -f oracle-xe` until
you see "DATABASE IS READY TO USE!"), then the default pluggable database
is `XEPDB1` and the DSN is `localhost:1521/XEPDB1`.

Any other Oracle Database 19c+ instance (on-prem, Oracle Cloud Free Tier
Autonomous Database, etc.) works the same way — only the DSN changes.

## 2. Create an application schema/user

Connect as a privileged user (`sys` / `system`) and create a dedicated
schema for this app — never run the application against `sys`/`system`:

```sql
ALTER SESSION SET CONTAINER = XEPDB1;
CREATE USER recon_app IDENTIFIED BY "<a-strong-password>";
GRANT CONNECT, RESOURCE TO recon_app;
GRANT CREATE TABLE, CREATE SEQUENCE, CREATE PROCEDURE, CREATE VIEW TO recon_app;
GRANT UNLIMITED TABLESPACE TO recon_app;
```

## 3. Install the schema and PL/SQL package

```bash
sqlplus recon_app/<password>@//localhost:1521/XEPDB1 @db/oracle/schema.sql
sqlplus recon_app/<password>@//localhost:1521/XEPDB1 @db/oracle/plsql/reconciliation_pkg.sql
```

Both scripts are idempotent-ish: re-running `schema.sql` on an
already-provisioned schema will error on `CREATE TABLE`/`CREATE INDEX` for
objects that already exist (Oracle has no portable `IF NOT EXISTS` for DDL
prior to 23ai) — this is expected and does not indicate a problem; the
application's `initialize_schema()` tolerates it (see
`app/db/oracle_repo.py`, `_ALREADY_EXISTS`). The PL/SQL package always uses
`CREATE OR REPLACE` and is safe to re-run any time.

## 4. Install the Python driver

```bash
pip install -r requirements-oracle.txt
```

This installs `python-oracledb` in "thin" mode, which talks to Oracle over
the network directly — no separate Oracle Instant Client install needed for
a standard TCP connection.

## 5. Configure environment variables

```bash
cp .env.example .env
# edit .env with your real DSN/user/password -- never commit this file
export ORACLE_DSN=localhost:1521/XEPDB1
export ORACLE_USER=recon_app
export ORACLE_PASSWORD=<your-password>
```

## 6. Run a reconciliation against Oracle

```bash
python main.py run \
  --source data/sample/erp_orders.json \
  --target data/sample/finance_orders.csv \
  --key order_id \
  --compare amount:numeric:0.01 --compare status --compare date:date \
  --db-backend oracle \
  --out-dir output
```

## 7. Run the Oracle-only test suite

```bash
pytest -m oracle -v
```

These tests are excluded from the default `pytest` run (see
`pyproject.toml`'s `markers` and the main `README.md` test instructions) and
will `skip` (not fail) if the three env vars above aren't all set — so
`pytest` alone is always safe to run without an Oracle instance.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `DatabaseConnectionError: python-oracledb is not installed` | Run `pip install -r requirements-oracle.txt` |
| `DatabaseConnectionError: ORACLE_DSN, ORACLE_USER and ORACLE_PASSWORD env vars must all be set` | One or more env vars missing — see step 5 |
| `ORA-12541: TNS:no listener` | Oracle container/instance isn't up yet, or the port/host is wrong |
| `ORA-01017: invalid username/password` | Check the schema user and password from step 2 |
| `ORA-00942: table or view does not exist` | Schema not installed yet — run step 3 |
| `ORA-06550` / `PLS-00201` referencing `reconciliation_pkg` | PL/SQL package not installed, or installed under a different schema than `ORACLE_USER` |
