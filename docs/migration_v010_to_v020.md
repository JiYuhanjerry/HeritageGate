# Migration from v0.1.0 to v0.2.0

## Database behavior

Opening an existing v0.1 SQLite database with v0.2.0 is non-destructive.
HeritageGate:

1. retains the `projects`, `gate_records`, and `audit_events` tables;
2. adds `governance_owner` and `audit_takedown_ready` to `projects` when absent;
3. creates the normalized v0.2 entity and relationship tables;
4. records schema version `0.2.0` in `schema_metadata`.

Existing generic gate payloads are not silently converted into normalized
records. A v0.1 payload may contain counts or free-text references that are
insufficient to reconstruct named rights holders, parties, element cards, or
financial recipients without fabrication. Authors should create the normalized
records from the underlying source documentation.

## Recommended migration procedure

```powershell
Copy-Item .\project.db .\project_v010_backup.db
python -m pip install .\dist\heritagegate-0.2.0-py3-none-any.whl
heritagegate --db .\project.db init-db
heritagegate --db .\project.db status PROJECT_ID
```

Then add normalized records using `add-entity`, check each structured gate with
`structured-readiness`, and export a new manifest.

## Compatibility

The original `pass-gate`, `records`, `audit`, `demo`, and `export` commands
remain available. A project can therefore retain historical generic records
while adding structured entities prospectively.
