# HeritageGate User Manual

Version 0.5.5. This manual consolidates installation, the command-line
interface, the Gate 0–7 workflow, the normalized governance entities, the
pilot-study and real-pilot modules, release preparation, and the local
browser interface into a single reference. It complements, rather than
replaces, the topic-specific documents listed in [Further
documentation](#further-documentation).

## Contents

1. [Installation](#1-installation)
2. [Core concepts](#2-core-concepts)
3. [Quick start](#3-quick-start)
4. [The Gate 0–7 workflow](#4-the-gate-07-workflow)
5. [Normalized governance entities](#5-normalized-governance-entities)
6. [Pilot-study module (v0.4)](#6-pilot-study-module-v04)
7. [Real-pilot module (v0.5)](#7-real-pilot-module-v05)
8. [Release and publication preparation](#8-release-and-publication-preparation)
9. [Exports at a glance](#9-exports-at-a-glance)
10. [The local browser interface](#10-the-local-browser-interface)
11. [Command reference](#11-command-reference)
12. [Troubleshooting](#12-troubleshooting)
13. [Further documentation](#13-further-documentation)

## 1. Installation

HeritageGate requires Python 3.10 or later. It is pure Python with no
mandatory third-party runtime dependency, so installation does not require
network access at run time.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # PowerShell; use `source .venv/bin/activate` on Linux/macOS
python -m pip install .\dist\heritagegate-0.5.5-py3-none-any.whl
python -c "import heritagegate; print(heritagegate.__version__)"   # expect: 0.5.5
```

For development, install in editable mode instead:

```powershell
python -m pip install -e .
```

An optional `Dockerfile` (based on `python:3.12-slim`) is included for
containerized installation.

## 2. Core concepts

- **Project.** The unit of work. Every command operates on a project
  identified by `--project-id` (or a positional `project_id` argument) inside
  a SQLite database given by the global `--db` flag.
- **Database.** A single SQLite file, given with `--db PATH` before the
  subcommand, e.g. `heritagegate --db pilot.db status PROJECT_ID`. If omitted,
  it defaults to `heritagegate.db` in the current directory. The schema is
  versioned; opening an older database non-destructively upgrades it.
- **Gates.** Eight ordered stages, numbered -1 (not started) through 7
  (governance complete). A project must pass gates strictly in order; see
  [§4](#4-the-gate-07-workflow).
- **Normalized entities.** Structured records — rights holders,
  authorizations, element cards, model runs, expert reviews, market tests,
  and revenue distributions — stored in relational tables rather than free
  text, so a gate's evidence can be built from them automatically.
- **Pilot vs. real-pilot.** The v0.4 pilot module (§6) captures usability
  records directly, with no privacy machinery, and is intended for internal
  or synthetic use. The v0.5 real-pilot module (§7) adds consent
  registration, de-identified participant import, withdrawal, and automated
  data-quality checks, and is the module intended for an authorized pilot
  with real participants.
- **Output.** Every CLI command prints one JSON object to standard output on
  success, and writes `error: <message>` to standard error with exit code 2
  on failure.

## 3. Quick start

Initialize a database and create a project:

```powershell
heritagegate --db project.db init-db
heritagegate --db project.db create-project --name "Cloud-lattice pilot" --heritage "Fictional cloud-lattice motif (synthetic)" --project-id proj-001
```

A new project starts at Gate -1 (`"current_gate": -1`). Check its state at
any time:

```powershell
heritagegate --db project.db status proj-001
```

Pass Gate 0 with a JSON payload satisfying its validator (§4):

```powershell
echo {"permission_status":"permissible","rationale":"Community elder council approved use for this collection.","reviewers":["reviewer-1"]} > gate0.json
heritagegate --db project.db pass-gate proj-001 0 gate0.json
```

`status` now reports `"current_gate": 0` and `"status": "active"`. Repeat
`pass-gate` with each subsequent gate's required payload to advance through
Gate 7, or run the built-in synthetic demonstration instead:

```powershell
heritagegate --db project.db demo --project-id demo-001
```

Launch the local browser interface against the same database:

```powershell
heritagegate --db project.db web --open-browser
```

The server binds to `127.0.0.1:8765` by default (`--host` and `--port`
override this) and needs no external service.

## 4. The Gate 0–7 workflow

`pass-gate PROJECT_ID GATE PAYLOAD_JSON` accepts a project, the target gate
number, and a JSON file. Two rules are enforced before the gate-specific
validator runs:

- **Ordering.** Only the immediate next gate is accepted. Attempting to skip
  ahead fails with, for example: `error: Project is at Gate 0; the next
  passable gate is Gate 1, not Gate 2`.
- **Red line (Gate 0 only).** A Gate 0 payload with `permission_status` other
  than `"permissible"` is refused with: `error: Gate 0 can pass only when
  permission_status is 'permissible'`. This blocks a project whose cultural
  authorization is restricted or pending from proceeding at all.

Each gate's validator requires the following fields to be present and
non-empty (booleans marked "must be `true`" are additionally checked for that
exact value; numeric fields marked "positive" must be a finite number greater
than zero — `NaN` and infinity are rejected):

| Gate | Required fields |
|---|---|
| 0 — Permission | `permission_status` (must be `permissible`, `restricted`, or `pending`), `rationale`, `reviewers` |
| 1 — Authorization | `authorization_status` (must be `approved`), `authorizers`, `permitted_uses`, `prohibited_uses`, `attribution_requirements`, `revenue_terms`, `authorization_record_ref` |
| 2 — Digitization | `dataset_id`, `source_count` (positive), `technical_metadata_complete` (must be `true`), `cultural_metadata_complete` (must be `true`), `license_terms`, `capture_log_ref` |
| 3 — Semantic library | `library_version`, `elements_count` (positive), `bearer_annotation` (must be `true`), `prohibited_combinations_documented` (must be `true`), `element_card_schema_ref` |
| 4 — AI-assisted generation | `model_name`, `model_version`, `constraint_method`, `provenance_enabled` (must be `true`), `generated_variants` (positive), `source_element_ids`, `generation_log_ref` |
| 5 — Multi-stakeholder review | `bearer_approved` (must be `true`), `design_expert_approved` (must be `true`), `production_feasible` (must be `true`), `review_record_ref`, `reviewers` |
| 6 — Market test | `sample_size` (positive), `perceived_authenticity`, `perceived_cultural_value`, `story_comprehension`, `purchase_intention`, `recommendation_intention` (each a number from 1 to 5), `test_channel`, `market_test_report_ref` |
| 7 — Governance | `rights_map_current` (must be `true`), `revenue_protocol_active` (must be `true`), `audit_takedown_ready` (must be `true`), `distribution_records_ref`, `governance_owner`, `audit_trail_ref` |

Related commands:

- `fail-gate PROJECT_ID GATE PAYLOAD_JSON [--feedback-target GATE]` records a
  failed review without advancing the project, optionally naming an earlier
  gate the project should be reconsidered from.
- `rollback PROJECT_ID TARGET_GATE --reason "..."` moves a project back to an
  earlier *already-completed* gate. The failed or superseded record is kept,
  not deleted, so the audit trail stays append-only.
- `audit PROJECT_ID` prints the full audit trail; `records PROJECT_ID` prints
  the raw gate records.

## 5. Normalized governance entities

Seven entity types capture the rights, provenance, and review evidence that
gate payloads reference: `rights-holder`, `authorization`, `element-card`,
`model-run`, `expert-review`, `market-test`, `revenue-distribution`. A model
run must name the element cards it drew on, so provenance can be traced
forward from a generated output to its authorization, and backward from a
takedown request to every affected record.

```powershell
heritagegate --db project.db add-entity rights-holder proj-001 rights_holder.json
heritagegate --db project.db list-entities rights-holder proj-001
heritagegate --db project.db get-entity rights-holder ENTITY_ID
heritagegate --db project.db update-entity rights-holder proj-001 ENTITY_ID rights_holder_updated.json
```

Once enough normalized entities exist for a project, two commands let a gate
be evaluated and passed from them instead of a hand-built payload:

```powershell
heritagegate --db project.db structured-readiness proj-001 1
heritagegate --db project.db pass-structured-gate proj-001 1
```

`structured-readiness` accepts gates 1, 3, 4, 5, 6, and 7 — the gates whose
evidence can be assembled from normalized records. `configure-governance
PROJECT_ID --owner NAME [--audit-takedown-ready]` sets the Gate 7 ownership
and audit-readiness fields directly. `structured-demo [--project-id ID]` runs
a full synthetic Gate 0–7 demonstration using normalized entities throughout.

Example JSON payload shapes are in `examples/structured_v020/`.

## 6. Pilot-study module (v0.4)

The v0.4 pilot module records usability evidence directly against eight
entity types: `study`, `participant`, `task`, `session`, `installation`,
`task-attempt`, `sus-response`, `workflow-benchmark`. It carries no privacy
safeguards — records are stored as supplied — and is intended for internal
testing or fully synthetic demonstrations, not for real participant data.
Use the [real-pilot module](#7-real-pilot-module-v05) for authorized
fieldwork with real participants.

```powershell
heritagegate --db project.db add-pilot-entity participant proj-001 participant.json
heritagegate --db project.db list-pilot-entities participant proj-001
heritagegate --db project.db get-pilot-entity participant ENTITY_ID
heritagegate --db project.db pilot-summary proj-001
```

`pilot-demo [--project-id ID]` (default `demo-pilot-001`) generates a fully
synthetic pilot dataset — participants, sessions, installations, task
attempts, SUS responses, and a workflow benchmark — for software testing.
All records it creates are explicitly marked synthetic and must not be
presented as evidence about a real tradition, community, participant, or
software effect.

## 7. Real-pilot module (v0.5)

The real-pilot module is the privacy-aware path for an authorized pilot: it
registers versioned consent, imports participants without retaining local
identifiers, enforces withdrawal, runs automated data-quality checks, and
produces deterministic, checksummed statistical reports. Six entity types —
`consent-document`, `enrollment`, `import-batch`, `quality-run`,
`analysis-run`, `release-profile` — are listable and retrievable with
`list-v050-entities` and `get-v050-entity`.

### 7.1 Register a consent document

```powershell
heritagegate --db pilot.db register-consent PROJECT_ID consent.pdf `
    --title "HeritageGate usability pilot consent" `
    --version 1.0 --language en `
    --ethics-ref ETHICS-2026-001 `
    --effective-from 2026-08-01 `
    --withdrawal-contact research@example.org `
    --retention-policy "Retain de-identified records for five years"
```

The consent file itself is never copied into the database; HeritageGate
stores its local path reference and SHA-256 digest only. The command prints
the new document's `id`, needed for the next step.

### 7.2 Import de-identified participants

```powershell
heritagegate --db pilot.db import-participants PROJECT_ID participants.csv --consent-document-id CONSENT_ID
```

A format-reference template is at
`examples/v050_real_pilot/participant_import_template.csv`. Required
columns: `source_id`, `participant_role` (one of `researcher`, `bearer`,
`cultural_expert`, `designer`, `developer`, `student`, `other`),
`experience_level` (`novice`, `intermediate`, `advanced`), `consent_status`
(`consented`, `exempt`, `withdrawn` — a `consented` row requires
`--consent-document-id` and an ISO-8601 `consented_at`). Optional columns:
`consented_at`, `eligibility_status` (`eligible`, `ineligible`, `pending`),
`demographics_json`, `data_use_scope_json`, `notes`.

Column headers are checked in three layers before any row is read: exact
names, ASCII-fragment matches, and CJK-fragment matches (covering common
Chinese-language headings such as 姓名, 手机, 身份证). Any match refuses the
whole file and names the rule that fired. Columns outside the recognized set
are silently dropped from storage but reported by name in the batch result,
so an unrecognized identifier column is visible rather than silently
imported. Participant codes are derived by HMAC-SHA-256 under a per-database
key stored outside the database (§2.3 of the SoftwareX manuscript describes
the threat model this addresses).

### 7.3 Withdrawal

```powershell
heritagegate --db pilot.db withdraw-participant PROJECT_ID PARTICIPANT_ID --withdrawn-at 2026-08-10T00:00:00Z --reason "Participant request"
```

New sessions for a withdrawn participant are prevented, and any session
timestamped after withdrawal is flagged by the next quality check.

### 7.4 Data-quality checking

```powershell
heritagegate --db pilot.db quality-check PROJECT_ID
```

Fifteen named checks run, each emitting an issue at `blocking` or `advisory`
severity if it fires: `ETHICS_UNRESOLVED`, `CONSENT_DOCUMENT_MISSING`,
`CONSENT_TIMESTAMP_MISSING`, `MISSING_ENROLLMENT`, `DIRECT_IDENTIFIER_KEY`,
`INELIGIBLE_SESSION`, `SESSION_TIME_MISSING`, `INVALID_WITHDRAWAL_TIME`,
`POST_WITHDRAWAL_SESSION`, `REQUIRED_TASK_MISSING`, `INSTALLATION_MISSING`,
`CROSSOVER_INCOMPLETE`, `SUS_MISSING`, `PROTOCOL_COUNT`,
`SAMPLE_BELOW_PLAN`. Any blocking issue prevents the release-readiness check
(§8) from passing.

### 7.5 Reproducible analysis

```powershell
heritagegate --db pilot.db analyze-pilot PROJECT_ID analysis_output --seed 20260729
```

Writes `analysis_results.json`, `analysis_report.md`, `analysis_table.csv`,
`analysis_input_manifest.json`, `data_quality_report.json`, and
`SHA256SUMS.txt` to the output directory, plus `analysis_run_context.json`
holding run-scoped identifiers that are deliberately excluded from the
checksum set. Given the same seed and the same underlying data, the five
checksummed files are byte-identical run to run: `sha256sum -c` against a
published `SHA256SUMS.txt` verifies a later run on another machine. Reported
intervals — Wilson 95% intervals for completion and installation rates,
seeded bootstrap intervals for durations, SUS scores, and paired differences
— are descriptive and do not establish causality.

## 8. Release and publication preparation

### 8.1 Configure a release profile

```powershell
heritagegate --db pilot.db configure-release PROJECT_ID release_profile.json
```

A starting template is at
`examples/v050_real_pilot/release_profile_template.json`. Required fields
include `software_title`, `manuscript_title`, `software_version`,
`release_status` (`draft`, `candidate`, `released`), `evidence_status`
(`synthetic`, `real_pilot`, `validated_real_pilot`), `license_spdx`, and a
non-empty `authors` list where each author has a non-empty `name`.
`support_email`, when given, must be a syntactically valid email address.

### 8.2 Check readiness

```powershell
heritagegate --db pilot.db release-readiness PROJECT_ID
```

Evaluates a checklist covering the data-quality run, analysis run, and
release-profile completeness. A passing checklist is not editorial approval:
repository links, DOI, authors, ethics, consent, empirical results, and every
manuscript claim still require human verification before submission.

### 8.3 Build the submission-release package

```powershell
heritagegate --db pilot.db export-submission-release PROJECT_ID submission_release.zip
```

Refuses to build without a configured release profile. The resulting ZIP
contains: `CITATION.cff`, `.zenodo.json`, `codemeta.json`,
`GitHub_RELEASE_NOTES.md`, `README_RELEASE.md`, `Highlights.txt`,
`SoftwareX_manuscript_draft.md`, `softwarex_metadata_tables.md`,
`Cover_letter_draft.md`, `CRediT_author_statement_template.md`,
`Data_availability_statement.md`, `Generative_AI_use_declaration.md`,
`Author_verification_required.md`, `PRIVACY_EXCLUSION_LOG.md`,
`package_metadata.json`, `release_readiness.json`,
`aggregate_analysis_results.json`, `public_aggregate_evidence.json`, and
`SHA256SUMS.txt`. Participant rows and codes, consent files and local paths,
source identifiers, identity-token hashes, source-row hashes, raw session
evidence, and the pseudonymization key are never written to this package —
verified adversarially, not only by policy (see the SoftwareX manuscript,
§3.4). `Highlights.txt` in this ZIP is a reasonable starting point for a
journal's separate highlights requirement.

## 9. Exports at a glance

| Command | Produces | Includes participant-level data? |
|---|---|---|
| `export PROJECT_ID out.json` | One reproducible project manifest | Yes — restricted |
| `export-csv PROJECT_ID out_dir/` | Analysis-ready CSV files + manifest | Yes — restricted |
| `export-research PROJECT_ID out.zip` | Portable research ZIP: manifest, CSVs, data dictionary, checksums | Yes — restricted, for the research team only |
| `export-softwarex-evidence PROJECT_ID out.zip` | v0.4 pilot evidence ZIP for SoftwareX preparation | Aggregate only |
| `export-submission-release PROJECT_ID out.zip` | Privacy-filtered publication package (§8.3) | No — excluded and adversarially tested |

Every CSV writer neutralizes cells that a spreadsheet would read as a
formula (leading `=`, `+`, `-`, `@`, tab, or carriage return are
apostrophe-prefixed) so an exported file cannot execute code when opened in
Excel or a similar application.

## 10. The local browser interface

```powershell
heritagegate --db project.db web --host 127.0.0.1 --port 8765 --open-browser
```

The server binds to loopback only. Pages available: `/` (project list),
`/projects/new`, `/projects/{id}` (dashboard: gate progress, structured
evidence, pilot and real-pilot summaries, release readiness, exports,
recent audit events), `/projects/{id}/edit`, `/projects/{id}/governance`,
`/projects/{id}/pilot`, `/projects/{id}/real-pilot`,
`/projects/{id}/entities/{type}` and `.../new` and `.../{entity_id}/edit`,
`/projects/{id}/pilot/{type}` and `.../new`, `/projects/{id}/api` (raw JSON
manifest), plus JSON endpoints `/health` and `/api/projects`, and
per-project download endpoints under `/projects/{id}/export/`. Consent
registration and participant import stay command-line-only, so the browser
process never receives or retains an uploaded source file.

## 11. Command reference

All commands take the global `--db PATH` flag before the subcommand.

| Command | Purpose |
|---|---|
| `init-db` | Create or upgrade the schema |
| `create-project` / `update-project` / `status` / `list-projects` | Project lifecycle |
| `pass-gate` / `fail-gate` / `rollback` / `audit` / `records` | Gate 0–7 workflow |
| `export` / `export-csv` / `export-research` | Restricted research exports |
| `demo` / `structured-demo` / `pilot-demo` | Synthetic demonstrations |
| `add-entity` / `update-entity` / `list-entities` / `get-entity` | Governance entities |
| `configure-governance` / `structured-readiness` / `pass-structured-gate` | Structured-evidence gate passing |
| `add-pilot-entity` / `list-pilot-entities` / `get-pilot-entity` / `pilot-summary` | v0.4 pilot module |
| `export-softwarex-evidence` | v0.4 pilot evidence ZIP |
| `register-consent` / `import-participants` / `withdraw-participant` | v0.5 consent and enrollment |
| `quality-check` / `analyze-pilot` | v0.5 integrity checks and reproducible analysis |
| `configure-release` / `release-readiness` / `export-submission-release` | v0.5 publication preparation |
| `list-v050-entities` / `get-v050-entity` | v0.5 record inspection |
| `web` | Local browser interface |

Run `heritagegate COMMAND -h` for a command's full argument list, or
`heritagegate -h` for the complete list.

## 12. Troubleshooting

- **`error: Project is at Gate X; the next passable gate is Gate Y, not Gate
  Z`** — gates must be passed strictly in order; pass Gate Y first.
- **`error: Gate 0 can pass only when permission_status is 'permissible'`** —
  by design. A restricted or pending Gate 0 payload is recorded but the
  project does not advance.
- **`error: Missing required field: FIELD`** — the gate's validator (§4) or
  entity schema requires that field; check `schemas/*.schema.json` for the
  full shape.
- **`error: Participant import refuses direct-identifier columns: ...`** —
  rename or remove the listed column from the CSV; see §7.2.
- **`error: A release profile is required before building a submission
  package`** — run `configure-release` before
  `export-submission-release`.
- **Keyed pseudonymization errors mentioning a "stable location"** — occurs
  when the database path itself has no fixed location (for example
  `:memory:`); use a named database file, or set the environment variable
  named in the error message to an explicit key-file path.
- **Windows path or console issues** — verify the same virtual environment is
  active in the shell running each command, and prefer PowerShell's `` ` ``
  line-continuation as shown in the examples above rather than a Unix `\`.

## 13. Further documentation

This manual is the entry point; the following documents go deeper on
specific subsystems:

- `docs/architecture.md` — component and data-flow overview
- `docs/data_model.md`, `docs/structured_data_model.md` — schema detail
- `docs/pilot_study_module.md` — v0.4 pilot module
- `docs/real_pilot_implementation.md` — v0.5 real-pilot module
- `docs/reproducible_analysis.md` — the statistical methods behind §7.5
- `docs/research_exports.md` — the exports in §9
- `docs/submission_release_module.md` — the package built in §8.3
- `docs/softwarex_evidence_package.md`, `docs/softwarex_readiness.md` —
  SoftwareX-specific preparation
- `docs/migration_v041_to_v050.md` and the other `migration_*.md` files —
  upgrading an existing database
- `docs/roadmap.md` — planned future development
- `README.md` — project overview and license information
