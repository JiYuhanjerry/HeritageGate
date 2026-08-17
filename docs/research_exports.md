# Research-data exports

HeritageGate v0.4.0 can export a single project as a directory or a portable ZIP.
The export is designed for audit, reproducibility, descriptive analysis, and
handoff to R, Python, spreadsheet, or qualitative-analysis workflows.

## Directory export

```powershell
heritagegate --db project.db export-csv PROJECT_ID .\research_export
```

## ZIP export

```powershell
heritagegate --db project.db export-research PROJECT_ID .\research_bundle.zip
```

## Files

- `manifest.json`: complete nested project record.
- `projects.csv`: project state and governance metadata.
- `gate_records.csv`: all gate outcomes and evidence payloads.
- `gate_summary.csv`: Gate 0–7 summary.
- `audit_trail.csv`: append-only project events.
- `rights_holders.csv`.
- `authorization_records.csv`.
- `cultural_element_cards.csv`.
- `model_runs.csv`.
- `expert_reviews.csv`.
- `market_tests.csv`.
- `revenue_distributions.csv`.
- `pilot_studies.csv`.
- `pilot_participants.csv`.
- `pilot_tasks.csv`.
- `pilot_sessions.csv`.
- `installation_records.csv`.
- `pilot_task_attempts.csv`.
- `sus_responses.csv`.
- `workflow_benchmarks.csv`.
- `pilot_metrics.csv`.
- `entity_counts.csv`.
- `data_dictionary.csv`.
- `README.txt`.
- `SHA256SUMS.txt`.

CSV files use UTF-8 with BOM. Nested relationships, such as authorization
parties, annotators, source elements, and model parameters, are encoded as
compact JSON strings in individual cells. The full nested representation remains
available in `manifest.json`.

## Governance warning

Creating an export does not establish a right to distribute it. Researchers must
review privacy, authorization, community governance, contractual, security, and
financial-confidentiality requirements before moving a bundle outside its
controlled project environment.
