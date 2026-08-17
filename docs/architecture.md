# Architecture

HeritageGate v0.4.0 uses a dependency-free layered architecture.

```text
Browser / CLI
      |
      v
Web routing and HTML rendering / argparse commands
      |
      v
HeritageGateEngine
      |
      +--> Gate validators and ordered transition rules
      +--> StructuredDataManager
      +--> PilotStudyManager
      +--> Research and SoftwareX evidence exporters
      |
      v
SQLite persistence and append-only audit events
```

## Layers

### Interface layer

- `heritagegate.cli`: command-line interface.
- `heritagegate.web`: local HTTP server, HTML views, validated form actions,
  downloads, and read-only JSON endpoints.

### Workflow layer

- `heritagegate.engine`: projects, gate transitions, failures, rollback,
  project metadata, manifests, and audit events.
- `heritagegate.validators`: minimum evidence rules for Gate 0–7.

### Structured-data layer

- `heritagegate.structured`: normalized entity creation, editing, relationship
  validation, readiness reporting, and structured evidence construction.

### Pilot-study layer

- `heritagegate.pilot`: protocol, participant, task, session, installation,
  task-attempt, SUS, benchmark, validation, and descriptive metrics.

### Export layer

- `heritagegate.exporter`: complete JSON/CSV directory export, portable ZIP bundles,
  data dictionary, and SHA-256 checksums.
- `heritagegate.evidence`: SoftwareX evidence reports, candidate manuscript text,
  vector figures, pilot CSV files, readiness checklist, and checksums.

### Persistence layer

- `heritagegate.db`: SQLite schema, connections, migrations, and JSON encoding.

## Deployment boundary

Version 0.4 is a local single-process research application. The default HTTP
binding is loopback-only. The application is not designed as a public multi-user
service and does not provide authentication, transport encryption, or row-level
permissions.
