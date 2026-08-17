# Changelog

## 0.5.6 - 2026-08-17

Found while writing the consolidated user manual, by executing the
documented Quick Start sequence rather than only reading it.

### Fixed

- **Demonstration entity IDs collided across projects.** `structured-demo`
  and `pilot-demo` created their normalized governance entities (rights
  holders, authorizations, element cards, model runs, reviews, market
  tests, revenue distributions) and pilot records (studies, tasks,
  participants, sessions, installations, task attempts, SUS responses,
  benchmarks) under fixed literal IDs such as `auth-demo-001` and
  `participant-demo-01`. Entity IDs are a global primary key by design —
  `get_entity(entity_type, entity_id)` takes no project argument — so
  running either demo command a second time under a *different* project ID
  against the same database found the first project's entities already
  registered under those IDs and silently reused them instead of creating
  new ones for the second project. The second project was then left with no
  authorization record of its own, and any Gate 1 check against it failed
  with "Gate 1 requires at least one approved authorization record" even
  though the demonstration had appeared to run successfully. Every
  demonstration-generated ID is now salted with the calling `project_id`.
  Re-running a demonstration under the *same* project ID remains fully
  supported and idempotent, unchanged from prior behaviour.

### Tests

- Increased from 73 to 74. The new test runs `structured-demo` under one
  project and `pilot-demo` under a second, against the same database, and
  asserts each project ends up with its own distinct authorization record
  and a quality check with zero blocking issues.

## 0.5.5 - 2026-08-03

Corrections from a fourth audit round, which examined spreadsheet-facing
outputs, numeric evidence validation, the web write endpoints, and concurrency.

### Fixed

- **CSV exports no longer carry executable formulas.** Every CSV the package
  writes is encoded UTF-8 with a BOM so that Excel opens it cleanly, and several
  exported fields (notes, titles, labels) hold text supplied by collaborators. A
  value such as `=cmd|'/c calc'!A1` was written through unchanged and would run
  when the file was opened. Cells beginning with `=`, `+`, `-`, `@`, tab, or
  carriage return are now prefixed with an apostrophe, the standard
  neutralisation, which spreadsheets treat as text and do not display. Numeric
  values are unaffected. This covers the research export, the evidence export,
  and the release export.
- **Gate evidence rejects NaN and infinity.** `float("nan") <= 0` is False and
  infinity is greater than zero, so both passed the positive-number check and
  were recorded as evidence. Infinity then serialised into an exported manifest
  as a bare `Infinity` literal, which is not valid JSON and breaks a strict
  parser. Counts and scores must now be finite.

### Verified, unchanged

- The local interface binds to 127.0.0.1 only, and project names supplied
  through the web form are HTML-escaped rather than reflected.
- Sixteen concurrent project creations against one database all succeeded.
- The built wheel contains no tests, examples, databases, or key files.

### Tests

- Increased from 70 to 73.

## 0.5.4 - 2026-08-03

Corrections from a third audit round, which examined export paths, the web
interface, withdrawal, and key handling under realistic failure conditions.

### Fixed

- **Research export now states its disclosure level.** `export-research`
  produces CSV tables that omit consent paths and identity hashes, and the
  README said so — but the same bundle ships `manifest.json`, which preserves
  the complete record including participant codes, identity-token hashes,
  source-row hashes, and the local path of a registered consent document. The
  README's scope ("CSV exports") was narrower than the bundle's contents, and
  the difference was exactly the sensitive material. The README now labels the
  bundle RESTRICTED, names what `manifest.json` contains, and points to
  `export-submission-release` for anything leaving the project environment.
- **A database copied without its key is refused before a key is created.**
  Loading generated a fresh key and only then failed the fingerprint check,
  leaving behind a key file that looked authoritative but derived different
  codes for the same people. The fingerprint is now consulted first.
- **`get_entity` no longer raises AttributeError on a malformed import batch.**
  The 0.5.3 change that surfaced import warnings assumed `mapping_json` held an
  object; a hand-edited or legacy record raised a bare AttributeError from a
  read path.

### Verified, unchanged

- The local web interface exposes no participant code, identity hash, consent
  path, or local filesystem path on any served route.
- Withdrawal propagates end to end: participant status, enrollment timestamp,
  and subsequent quality checks all reflect it.

### Tests

- Increased from 67 to 70.

## 0.5.3 - 2026-08-03

Corrections from a self-audit of the 0.5.2 changes. Four of the five items are
defects introduced by 0.5.2 itself; the fifth is pre-existing.

### Fixed

- **Substituted key now refused.** A key file replaced or restored from the
  wrong backup silently derived different participant codes, so the same person
  could be enrolled twice with nothing linking the records. A fingerprint over
  a fixed constant is recorded on first use and verified afterwards; a mismatch
  raises with instructions rather than proceeding. The fingerprint reveals
  nothing about the key.
- **Bulk-import performance restored.** Both the identity hash and the row
  digest consulted the stored scheme, each opening a database connection, so
  an import cost about three connections per row against 1.1 in 0.5.1. The
  scheme and key are now cached per manager instance, returning the rate to
  1.1. The scheme is immutable once recorded, so caching is safe.
- **Shipped release template no longer fails readiness.** The template still
  declared `software_version` 0.5.1, which after the readiness check became
  version-aware in 0.5.2 meant the package's own template failed its own check.
  A regression test now pins the template to the package version.
- **Privacy exclusion log mentions the key.** The generated
  `PRIVACY_EXCLUSION_LOG.md` listed the excluded record types but not the
  pseudonymization key file introduced in 0.5.2. The builder never reads it,
  and the log now says so.
- **Databases without a stable path are refused for keyed derivation**
  (pre-existing). `:memory:` resolves to a literal file of that name rather
  than an in-memory database, so a key file named `:memory:.key` appeared in
  the working directory. Keyed derivation now raises and points to
  `HERITAGEGATE_IDENTITY_KEY_FILE` instead.

- **Import warnings now read back identically.** `import_participants_csv`
  returned `warnings` and `dropped_columns` at the top level while a later
  `get_entity` call nested them under `mapping`. Both paths now derive from the
  stored record, so the same batch has the same shape however it is obtained.

### Documented, not fixed

- In-memory databases remain unsupported: `:memory:` resolves to a file of that
  name rather than an in-memory database. Keyed derivation now refuses such a
  database, but the file is still created. Recorded under Known limitations in
  `docs/v052_upgrade_and_key_management.md`; changing the path resolution would
  touch every module's database access for little practical gain.

### Tests

- Increased from 61 to 67. The additions pin each item above, including a
  connection-per-row budget that fails if the caching is removed.

## 0.5.2 - 2026-08-02

Corrections arising from an independent verification run on Linux/Python 3.12.
Each item was found by executing v0.5.1 rather than by reading it.

### Fixed

- `pilot-demo` now enrols its synthetic participants as v0.5 records. The
  bundled demonstration previously produced eight blocking `MISSING_ENROLLMENT`
  issues and a report headed "Blocking issues: 8", because it built v0.4 pilot
  records that the v0.5 quality checker requires enrolments for.
- Analysis artefacts no longer embed per-run identifiers, so
  `sha256sum -c SHA256SUMS.txt` now verifies across runs. Previously
  `analysis_report.md`, `analysis_input_manifest.json` and
  `data_quality_report.json` embedded a fresh `quality_run_id` and timestamp
  and failed verification even though the statistics were identical. Run-scoped
  provenance moved to `analysis_run_context.json`, which is deliberately
  excluded from the checksum file.
- `enroll_existing_participant` raises `RealPilotError` on a duplicate
  enrolment instead of letting `sqlite3.IntegrityError` escape through the API.
- The package version is defined once in `heritagegate.version` and read from
  there, replacing hard-coded version strings in the web layer, the demo data,
  and the release-readiness check.

### Changed — participant pseudonymization

- Identity derivation now uses HMAC-SHA-256 under a per-database secret stored
  outside the database (`<database>.key`, mode 0600 where the platform
  supports it, overridable with `HERITAGEGATE_IDENTITY_KEY_FILE`). The previous
  derivation was `sha256(project_id | source_id)`, whose only salt was a public
  project identifier; a low-entropy roster identifier could be confirmed by
  recomputation in under a second. `source_row_hash` is keyed on the same basis.
- Databases that already contain enrolments keep the original scheme, recorded
  as `identity_hash_scheme` in `schema_metadata`, so existing participant codes
  remain valid. New databases use the keyed scheme.
- **The key file is required to reproduce participant codes.** Back it up with
  the same care as the database, and do not commit it.

### Changed — direct-identifier detection

- Detection is now layered: an expanded exact-match set, ASCII substring
  matching for variants, and CJK substring matching. Column names such as
  `contact_email`, `e-mail`, `telephone`, `student_id`, `ssn`, `id_card`,
  `date_of_birth`, `ip_address`, `姓名`, `手机号`, `身份证号` and `联系方式`
  were accepted by v0.5.1 and are now refused. Refusal messages name the rule
  that matched.
- Unrecognized columns are still discarded, but the import batch, the audit
  event, and the returned record now report them. Silent acceptance was the
  substantive hazard: a researcher supplying an unrecognized identifier column
  would otherwise believe the file had been reviewed and accepted.

### Tests

- Increased automated test coverage from 45 to 61 tests. The 16 additions in
  `tests/test_v052.py` pin each defect above, including backward compatibility
  with a v0.5.1 database and non-rejection of the shipped import template.

## 0.5.1 - 2026-07-29

- Fixed Windows test portability by reading generated UTF-8 reports with an explicit encoding.
- Fixed a Windows SQLite file-lock during test cleanup by explicitly closing the temporary connection.
- Kept the database schema and reproducible-analysis method versions at 0.5.0 because no persisted structure or statistical algorithm changed.

## 0.5.0 - 2026-07-29

- Added versioned consent-document registration with SHA-256 digests.
- Added direct-identifier-refusing participant CSV import and hashed source tokens.
- Added enrollment, eligibility, withdrawal, data-use scope, and import-batch records.
- Added missingness, consent, crossover, task-coverage, installation, and withdrawal checks.
- Added deterministic Wilson and seeded-bootstrap statistical reporting.
- Added GitHub, Zenodo, CodeMeta, CFF, SoftwareX metadata, manuscript, highlights, and cover-letter generation.
- Added privacy-safe submission-release packages that exclude participant-level records.
- Added release readiness and real-pilot web dashboard.
- Increased automated test coverage from 33 to 45 tests.

## 0.4.1 — 2026-07-29

- Fixed a Windows-only test cleanup failure caused by SQLite connections remaining open after transaction context exit.
- Updated the v0.3-to-v0.4 migration regression test to close SQLite handles deterministically with `contextlib.closing`.
- Preserved database schema version `0.4.0`; no database migration is required.
- No workflow, pilot-data, evidence-export, or web-interface behavior changed.

## 0.4.0 — 2026-07-29

- Added a versioned pilot-study protocol entity with ethics and outcome metadata.
- Added de-identified participants, standardized tasks, sessions, timed installation records, task attempts, SUS responses, and workflow benchmarks.
- Added automatic calculation of installation success, task completion, task duration, errors, assistance, SUS, and HeritageGate-versus-baseline workflow metrics.
- Added an eight-condition SoftwareX evidence-readiness checklist.
- Added browser pilot dashboard and validated JSON entry for all pilot record classes.
- Added SoftwareX evidence ZIP generation with raw CSV data, computed metrics, manuscript evidence report, candidate results sentences, vector SVG figures, metadata, and SHA-256 checksums.
- Added a fully synthetic crossover pilot demonstration with 8 participant codes, 16 sessions, 80 task attempts, 8 SUS responses, and 4 workflow benchmarks.
- Added non-destructive v0.3-to-v0.4 schema upgrading.
- Expanded the automated test suite from 24 to 33 tests.

## 0.3.1 — 2026-07-29

- Hardened the Windows loopback HTTP health test against system proxy interception.
- Added bounded retry logic for thread-scheduling and endpoint-security delays.
- Configured local request threads for clean Windows shutdown.
- Kept the database schema version at `0.3.0`; this is a software/test hotfix only.

## 0.3.0 — 2026-07-29

- Added a dependency-free local browser interface bound to `127.0.0.1` by default.
- Added project creation and metadata editing in the browser.
- Added validated browser-based creation and editing for all normalized entities.
- Added Gate 0–7 progress, entity counts, readiness reporting, and audit views.
- Added browser gate actions for dedicated and structured evidence.
- Added browser and CLI JSON/CSV research exports.
- Added portable ZIP bundles with data dictionary and SHA-256 checksums.
- Added read-only health and project API endpoints.
- Added project and structured-entity update methods with audit events.
- Added v0.2-to-v0.3 migration and Windows quick-start documentation.
- Added three reproducible interface screenshots generated from the synthetic demo.
- Expanded the automated test suite from 16 to 24 tests.

## 0.2.0 — 2026-07-29

- Added normalized rights-holder, authorization, cultural-element, model-run,
  expert-review, market-test, and revenue-distribution entities.
- Added relational authorization-party, element-annotator, and model-run-element links.
- Added structured gate evidence builders for Gates 1, 3, 4, 5, 6, and 7.
- Added role-specific Gate 5 approval requirements.
- Added bounded cultural-reception and commercial-intention metrics for Gate 6.
- Added cumulative share and amount controls for revenue distributions.
- Added governance-owner and audit/takedown readiness configuration for Gate 7.
- Added non-destructive v0.1 SQLite schema upgrade support.
- Added a complete normalized synthetic demonstration and expanded the test suite to 16 tests.

## 0.1.0 — 2026-07-29

- Added SQLite-backed project persistence.
- Added Gate 0–7 evidence validators.
- Added ordered transition enforcement and feedback rollback.
- Added append-only audit records and JSON manifest export.
- Added synthetic end-to-end demo and unit tests.
