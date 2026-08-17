# Migration from v0.4.1 to v0.5.0

Back up the SQLite database before opening it with v0.5.0.

```powershell
Copy-Item .\pilot_demo.db .\pilot_demo_v0.4.1_backup.db
```

Open the database with the v0.5.0 script:

```powershell
python .\run_heritagegate.py --db .\pilot_demo.db init-db
```

The upgrade preserves existing projects, gate records, audit events, governance
entities, pilot records, and evidence. It adds:

- `consent_documents`
- `participant_import_batches`
- `participant_enrollments`
- `data_quality_runs`
- `analysis_runs`
- `release_profiles`

Existing v0.4 participant records are not automatically enrolled because the
software cannot infer a legitimate source token, consent-document link,
eligibility status, or data-use scope. Use anonymous CSV import or
`enroll_existing_participant` under an approved local procedure.
