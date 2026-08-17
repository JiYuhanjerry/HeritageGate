# Migration from v0.2.0 to v0.3.0

Version 0.3.0 is a non-destructive application upgrade. The normalized entity
schema introduced in v0.2 remains compatible. Opening a v0.2 database with the
v0.3 engine updates `schema_metadata.schema_version` to `0.3.0` without deleting
projects, gate records, audit events, or normalized entities.

## Recommended Windows procedure

1. Back up the v0.2 database.

```powershell
Copy-Item .\structured_demo.db .\structured_demo_v0.2.0_backup.db
```

2. Install v0.3 from its new source directory.

```powershell
python -m pip install -e .
```

3. Initialize the existing database with the v0.3 script.

```powershell
python .\run_heritagegate.py --db .\structured_demo.db init-db
```

4. Confirm the package version.

```powershell
python -c "import heritagegate; print(heritagegate.__version__)"
```

Expected result: `0.3.0`.

5. Run the complete test suite.

```powershell
python -m unittest discover -s .\tests -v
```

Expected result: `Ran 24 tests` and `OK`.

The v0.3 release adds application features rather than destructive table
changes. No automatic conversion of external files or undocumented legacy JSON
is attempted.
