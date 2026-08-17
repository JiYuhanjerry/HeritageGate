# HeritageGate

[![CI](https://github.com/JiYuhanjerry/HeritageGate/actions/workflows/ci.yml/badge.svg)](https://github.com/JiYuhanjerry/HeritageGate/actions/workflows/ci.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21979698.svg)](https://doi.org/10.5281/zenodo.21979698)

**HeritageGate** is an open-source Python research-software platform for
stage-gated, rights-aware, provenance-preserving AI-assisted intangible
cultural heritage (ICH) research and productization.

Version **0.5.6** extends the Gate 0–7 workflow with a privacy-aware real-pilot
implementation layer and a submission-release generator. It registers versioned
consent-document metadata, imports participants without retaining the local
source identifier, records withdrawal, detects missing or inconsistent study
data, generates deterministic statistical reports, and prepares GitHub, Zenodo,
and SoftwareX materials.

HeritageGate is not a substitute for legal advice, community authorization,
ethics review, informed consent, secure identity management, or editorial
judgment. The bundled examples are synthetic and must not be represented as
real ICH or human-participant evidence.

## What v0.5.6 implements

- Persistent Gate 0–Gate 7 workflow with ordered transitions and rollback.
- Normalized governance entities for rights, authorization, cultural-element
  cards, model runs, expert reviews, market tests, and revenue distributions.
- Pilot entities for protocols, de-identified participants, tasks, sessions,
  installations, task attempts, SUS responses, and workflow benchmarks.
- Versioned consent-document registration with SHA-256 verification.
- Anonymous participant CSV import that:
  - rejects common direct-identifier columns;
  - hashes the local source identifier instead of storing it;
  - generates a stable de-identified participant code;
  - links consented participants to a versioned consent document;
  - records sanitized import failures and duplicates.
- Participant withdrawal with prevention of new sessions.
- Data-quality checks for ethics status, enrollment, consent, direct-identifier
  keys, crossover completeness, required-task coverage, installations,
  post-withdrawal sessions, and planned sample size.
- Reproducible analysis with:
  - Wilson 95% intervals for completion and installation rates;
  - seeded bootstrap intervals for mean duration, SUS, and paired differences;
  - input SHA-256, random seed, data-quality run, CSV table, Markdown report,
    and checksums.
- Release profile for authors, license, software version, support email,
  repository, archive, executable, documentation, DOI, funding, conflicts,
  AI-use declaration, and data-availability statement.
- Privacy-safe submission-release ZIP containing GitHub release notes,
  `CITATION.cff`, CodeMeta, Zenodo metadata, SoftwareX metadata tables,
  highlights, cover-letter draft, manuscript draft, aggregate evidence,
  readiness checklists, and checksums.
- Local browser dashboard for real-pilot and release readiness.
- Non-destructive opening of earlier HeritageGate SQLite databases.
- **74 automated tests**.

## Installation

The release is pure Python and has no mandatory third-party runtime dependency.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .\dist\heritagegate-0.5.6-py3-none-any.whl
```

For editable development installation:

```powershell
python -m pip install -e .
```

Verify the version:

```powershell
python -c "import heritagegate; print(heritagegate.__version__)"
```

Expected output:

```text
0.5.6
```

## Synthetic demonstration

```powershell
python .\run_heritagegate.py `
    --db .\pilot_demo.db `
    pilot-demo `
    --project-id demo-pilot-001 |
    Set-Content -Encoding utf8 .\pilot_demo_output.json
```

The built-in demonstration creates fixed synthetic records for software testing.
It is not a real pilot and does not satisfy the v0.5 release-readiness checks for
validated human-participant evidence.

## Register a consent document

```powershell
heritagegate --db .\pilot.db register-consent PROJECT_ID .\consent.pdf `
    --title "HeritageGate usability pilot consent" `
    --version 1.0 `
    --language en `
    --ethics-ref ETHICS-2026-001 `
    --effective-from 2026-08-01 `
    --withdrawal-contact research@example.org `
    --retention-policy "Retain de-identified records for five years"
```

The consent file is not copied into the SQLite database. HeritageGate stores its
local reference and SHA-256 digest. Public release packages exclude both the file
and its local path.

## Import de-identified participants

Use `examples/v050_real_pilot/participant_import_template.csv`. The required
columns are:

- `source_id`
- `participant_role`
- `experience_level`
- `consent_status`

Optional columns include `consented_at`, `eligibility_status`,
`demographics_json`, `data_use_scope_json`, and `notes`.

```powershell
heritagegate --db .\pilot.db import-participants PROJECT_ID `
    .\participants.csv `
    --consent-document-id CONSENT_ID
```

Do not include names, email addresses, phone numbers, addresses, birth dates,
identity-document numbers, or messaging identifiers. HeritageGate refuses common
direct-identifier headers and direct-identifier keys inside demographics JSON.

## Quality checking and analysis

```powershell
heritagegate --db .\pilot.db quality-check PROJECT_ID
```

```powershell
heritagegate --db .\pilot.db analyze-pilot PROJECT_ID .\analysis_output `
    --seed 20260729
```

The output directory contains:

- `analysis_results.json`
- `analysis_report.md`
- `analysis_table.csv`
- `analysis_input_manifest.json`
- `data_quality_report.json`
- `SHA256SUMS.txt`

The intervals are descriptive. They do not establish causality and do not repair
limitations in allocation, missingness, measurement, or sample size.

## Configure release metadata

Prepare a JSON file based on
`examples/v050_real_pilot/release_profile_template.json`, then run:

```powershell
heritagegate --db .\pilot.db configure-release PROJECT_ID .\release_profile.json
```

Check readiness:

```powershell
heritagegate --db .\pilot.db release-readiness PROJECT_ID
```

A passing automated checklist is not editorial approval. Repository links, DOI,
authors, ethics, consent, empirical results, declarations, and all manuscript
claims require human verification.

## Build the submission-release package

```powershell
heritagegate --db .\pilot.db export-submission-release PROJECT_ID `
    .\heritagegate_submission_release.zip
```

The package deliberately excludes participant rows, participant codes, consent
files, consent references, local source identifiers, identity-token hashes,
source-row hashes, and raw session evidence. It contains aggregate evidence and
publication-preparation materials only.

## Local browser interface

```powershell
heritagegate --db .\pilot.db web --open-browser
```

Default address:

```text
http://127.0.0.1:8765/
```

The real-pilot dashboard is read-only for restricted file operations. Consent
registration and participant import remain command-line operations so the
browser does not retain uploaded source files.

## Testing

```powershell
python -m unittest discover -s .\tests -v
```

Expected ending:

```text
Ran 74 tests

OK
```

## Data and licensing

- Source code: Apache License 2.0.
- Synthetic example data: CC0-1.0 where stated.
- Code licensing does not license heritage data, community knowledge, consent
  materials, participant data, contracts, model weights, or financial records.
- Real records require separate authorization, privacy, security, ethics,
  retention, access-control, and publication decisions.

## Documentation

- `docs/USER_MANUAL.md` — consolidated installation, workflow, and command reference
- `docs/real_pilot_implementation.md`
- `docs/reproducible_analysis.md`
- `docs/submission_release_module.md`
- `docs/migration_v041_to_v050.md`
- `docs/pilot_study_module.md`
- `docs/softwarex_readiness.md`
- `softwarex_metadata_draft.md`

Historical quick-start and validation notes for earlier releases are in
`docs/v020_quickstart_windows.md` and `docs/v020_validation_report.md`. There
is currently no v0.5.x equivalent of these two documents; use the
Installation and Testing sections above until one is written.
