# Migration from v0.3.1 to v0.4.0

The v0.4.0 schema upgrade is non-destructive. Opening a v0.3.1 database with HeritageGate v0.4.0 retains all projects, gate records, audit events, and structured governance entities, then adds pilot-study tables.

## Recommended Windows procedure

```powershell
Copy-Item .\demo.db .\demo_v0.3.1_backup.db
python .\run_heritagegate.py --db .\demo.db init-db
```

Verify the schema:

```powershell
python -c "import sqlite3; c=sqlite3.connect('demo.db'); print(c.execute(\"select value from schema_metadata where key='schema_version'\").fetchone()[0])"
```

Expected value: `0.4.0`.

Existing records are not automatically converted into pilot-study observations because v0.3.1 did not contain participant, timing, task, SUS, or baseline-comparison data.
