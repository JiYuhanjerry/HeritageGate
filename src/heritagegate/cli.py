"""Command-line interface for HeritageGate."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .demo import GATE_PAYLOADS, run_structured_demo, run_pilot_demo
from .engine import HeritageGateEngine, WorkflowStateError
from .exporter import build_research_bundle, export_csv_directory
from .evidence import build_softwarex_evidence_package
from .release import build_submission_release_package
from .web import run_server
from .structured import ENTITY_ALIASES, StructuredDataError, StructuredReadinessError
from .pilot import PILOT_ENTITY_ALIASES, PilotDataError
from .realpilot import REAL_PILOT_ENTITY_ALIASES, RealPilotError
from .validators import GateValidationError


def read_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return value


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="heritagegate",
        description=(
            "Stage-gated, rights-aware workflow engine with normalized governance "
            "entities, pilot-study evidence capture, a local web UI, real-pilot safeguards, reproducible analysis, and SoftwareX release exports."
        ),
    )
    parser.add_argument(
        "--db", default="heritagegate.db", help="SQLite database path (default: heritagegate.db)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Create or non-destructively upgrade the SQLite schema")

    create = sub.add_parser("create-project", help="Create a new project")
    create.add_argument("--name", required=True)
    create.add_argument("--heritage", required=True)
    create.add_argument("--description", default="")
    create.add_argument("--project-id")

    sub.add_parser("list-projects", help="List all projects")

    update_project = sub.add_parser("update-project", help="Update project name, heritage label, and description")
    update_project.add_argument("project_id")
    update_project.add_argument("--name", required=True)
    update_project.add_argument("--heritage", required=True)
    update_project.add_argument("--description", default="")

    status = sub.add_parser("status", help="Show one project")
    status.add_argument("project_id")

    gate = sub.add_parser("pass-gate", help="Validate JSON evidence and pass the next gate")
    gate.add_argument("project_id")
    gate.add_argument("gate", type=int, choices=range(0, 8))
    gate.add_argument("payload_json")

    fail = sub.add_parser("fail-gate", help="Record a failed next-gate review")
    fail.add_argument("project_id")
    fail.add_argument("gate", type=int, choices=range(0, 8))
    fail.add_argument("payload_json")
    fail.add_argument("--feedback-target", type=int, choices=range(0, 8))

    rollback = sub.add_parser("rollback", help="Move a project to an earlier completed gate")
    rollback.add_argument("project_id")
    rollback.add_argument("target_gate", type=int, choices=range(-1, 8))
    rollback.add_argument("--reason", required=True)

    audit = sub.add_parser("audit", help="Print the project audit trail")
    audit.add_argument("project_id")

    records = sub.add_parser("records", help="Print all generic gate records")
    records.add_argument("project_id")

    export = sub.add_parser("export", help="Export a reproducible project manifest")
    export.add_argument("project_id")
    export.add_argument("output_json")

    export_csv = sub.add_parser("export-csv", help="Export analysis-ready CSV files and manifest JSON")
    export_csv.add_argument("project_id")
    export_csv.add_argument("output_directory")

    export_research = sub.add_parser("export-research", help="Build a portable ZIP research bundle")
    export_research.add_argument("project_id")
    export_research.add_argument("output_zip")

    demo = sub.add_parser("demo", help="Run the backward-compatible generic demo")
    demo.add_argument("--project-id", default="demo-synthetic-001")

    entity_choices = sorted(ENTITY_ALIASES)
    add_entity = sub.add_parser("add-entity", help="Create one normalized governance entity")
    add_entity.add_argument("entity_type", choices=entity_choices)
    add_entity.add_argument("project_id")
    add_entity.add_argument("payload_json")

    update_entity = sub.add_parser("update-entity", help="Update one normalized governance entity from JSON")
    update_entity.add_argument("entity_type", choices=entity_choices)
    update_entity.add_argument("project_id")
    update_entity.add_argument("entity_id")
    update_entity.add_argument("payload_json")

    list_entities = sub.add_parser("list-entities", help="List normalized entities for a project")
    list_entities.add_argument("entity_type", choices=entity_choices)
    list_entities.add_argument("project_id")

    get_entity = sub.add_parser("get-entity", help="Show one normalized entity")
    get_entity.add_argument("entity_type", choices=entity_choices)
    get_entity.add_argument("entity_id")

    governance = sub.add_parser("configure-governance", help="Configure Gate 7 ownership and audit readiness")
    governance.add_argument("project_id")
    governance.add_argument("--owner", required=True)
    governance.add_argument("--audit-takedown-ready", action="store_true")

    readiness = sub.add_parser("structured-readiness", help="Check whether normalized records support a gate")
    readiness.add_argument("project_id")
    readiness.add_argument("gate", type=int, choices=[1, 3, 4, 5, 6, 7])

    structured_gate = sub.add_parser("pass-structured-gate", help="Build evidence from normalized records and pass a gate")
    structured_gate.add_argument("project_id")
    structured_gate.add_argument("gate", type=int, choices=[1, 3, 4, 5, 6, 7])

    structured_demo = sub.add_parser("structured-demo", help="Run the normalized Gate 0-to-7 demonstration")
    structured_demo.add_argument("--project-id", default="demo-structured-001")

    pilot_choices = sorted(PILOT_ENTITY_ALIASES)
    add_pilot = sub.add_parser("add-pilot-entity", help="Create one v0.4 pilot-study entity")
    add_pilot.add_argument("entity_type", choices=pilot_choices)
    add_pilot.add_argument("project_id")
    add_pilot.add_argument("payload_json")

    list_pilot = sub.add_parser("list-pilot-entities", help="List v0.4 pilot-study entities")
    list_pilot.add_argument("entity_type", choices=pilot_choices)
    list_pilot.add_argument("project_id")

    get_pilot = sub.add_parser("get-pilot-entity", help="Show one v0.4 pilot-study entity")
    get_pilot.add_argument("entity_type", choices=pilot_choices)
    get_pilot.add_argument("entity_id")

    pilot_summary = sub.add_parser("pilot-summary", help="Calculate descriptive pilot metrics")
    pilot_summary.add_argument("project_id")

    pilot_demo = sub.add_parser("pilot-demo", help="Run a fully synthetic v0.4 pilot demonstration")
    pilot_demo.add_argument("--project-id", default="demo-pilot-001")

    softwarex = sub.add_parser("export-softwarex-evidence", help="Build a SoftwareX pilot evidence ZIP")
    softwarex.add_argument("project_id")
    softwarex.add_argument("output_zip")

    register_consent = sub.add_parser("register-consent", help="Register a versioned consent document by SHA-256")
    register_consent.add_argument("project_id")
    register_consent.add_argument("document_path")
    register_consent.add_argument("--title", required=True)
    register_consent.add_argument("--version", required=True)
    register_consent.add_argument("--language", required=True)
    register_consent.add_argument("--ethics-ref", default="")
    register_consent.add_argument("--effective-from", required=True)
    register_consent.add_argument("--withdrawal-contact", required=True)
    register_consent.add_argument("--retention-policy", required=True)
    register_consent.add_argument("--document-id")

    import_participants = sub.add_parser("import-participants", help="Import participants without retaining source identifiers")
    import_participants.add_argument("project_id")
    import_participants.add_argument("csv_path")
    import_participants.add_argument("--consent-document-id")
    import_participants.add_argument("--participant-prefix", default="P")

    withdraw = sub.add_parser("withdraw-participant", help="Record withdrawal and prevent new sessions")
    withdraw.add_argument("project_id")
    withdraw.add_argument("participant_id")
    withdraw.add_argument("--withdrawn-at", required=True)
    withdraw.add_argument("--reason", required=True)

    quality = sub.add_parser("quality-check", help="Run missingness, consent, design, and integrity checks")
    quality.add_argument("project_id")
    quality.add_argument("--run-label", default="manual-quality-check")
    quality.add_argument("--report-ref", default="")

    analyze = sub.add_parser("analyze-pilot", help="Write deterministic pilot statistics and checksums")
    analyze.add_argument("project_id")
    analyze.add_argument("output_directory")
    analyze.add_argument("--seed", type=int, default=20260729)

    configure_release = sub.add_parser("configure-release", help="Create or update GitHub/Zenodo/SoftwareX release metadata")
    configure_release.add_argument("project_id")
    configure_release.add_argument("payload_json")

    release_readiness = sub.add_parser("release-readiness", help="Check real-pilot and submission completeness")
    release_readiness.add_argument("project_id")

    v050_choices = sorted(REAL_PILOT_ENTITY_ALIASES)
    list_v050 = sub.add_parser("list-v050-entities", help="List v0.5 consent, enrollment, quality, analysis, or release records")
    list_v050.add_argument("entity_type", choices=v050_choices)
    list_v050.add_argument("project_id")

    get_v050 = sub.add_parser("get-v050-entity", help="Show one v0.5 record")
    get_v050.add_argument("entity_type", choices=v050_choices)
    get_v050.add_argument("entity_id")

    submission = sub.add_parser("export-submission-release", help="Build privacy-safe GitHub/Zenodo/SoftwareX preparation ZIP")
    submission.add_argument("project_id")
    submission.add_argument("output_zip")
    submission.add_argument("--seed", type=int, default=20260729)
    submission.add_argument("--source-root")

    web = sub.add_parser("web", help="Run the local browser interface")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--open-browser", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        engine = HeritageGateEngine(args.db)
        if args.command == "init-db":
            print_json({"database": str(engine.database), "status": "initialized", "schema_version": "0.5.0"})
        elif args.command == "create-project":
            print_json(
                engine.create_project(
                    name=args.name,
                    heritage_name=args.heritage,
                    description=args.description,
                    project_id=args.project_id,
                )
            )
        elif args.command == "list-projects":
            print_json(engine.list_projects())
        elif args.command == "update-project":
            print_json(engine.update_project(
                args.project_id,
                name=args.name,
                heritage_name=args.heritage,
                description=args.description,
            ))
        elif args.command == "status":
            print_json(engine.get_project(args.project_id))
        elif args.command == "pass-gate":
            print_json(engine.pass_gate(args.project_id, args.gate, read_json(args.payload_json)))
        elif args.command == "fail-gate":
            print_json(
                engine.record_failure(
                    args.project_id,
                    args.gate,
                    read_json(args.payload_json),
                    feedback_target=args.feedback_target,
                )
            )
        elif args.command == "rollback":
            print_json(engine.rollback(args.project_id, args.target_gate, args.reason))
        elif args.command == "audit":
            print_json(engine.audit_trail(args.project_id))
        elif args.command == "records":
            print_json(engine.gate_records(args.project_id))
        elif args.command == "export":
            output = Path(args.output_json)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(engine.export_manifest(args.project_id), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print_json({"output": str(output.resolve()), "status": "written"})
        elif args.command == "export-csv":
            print_json(export_csv_directory(engine, args.project_id, args.output_directory))
        elif args.command == "export-research":
            print_json(build_research_bundle(engine, args.project_id, args.output_zip))
        elif args.command == "demo":
            try:
                engine.create_project(
                    name="Synthetic Motif Research Demo",
                    heritage_name="Fictional cloud-lattice motif (not real ICH)",
                    description="Synthetic end-to-end demonstration with no claim about any living community.",
                    project_id=args.project_id,
                )
            except sqlite3.IntegrityError:
                pass
            project = engine.get_project(args.project_id)
            for gate_number in range(project["current_gate"] + 1, 8):
                engine.pass_gate(args.project_id, gate_number, GATE_PAYLOADS[gate_number])
            print_json(engine.export_manifest(args.project_id))
        elif args.command == "add-entity":
            print_json(
                engine.structured.create_entity(
                    args.entity_type, args.project_id, read_json(args.payload_json)
                )
            )
        elif args.command == "update-entity":
            print_json(engine.structured.update_entity(
                args.entity_type, args.project_id, args.entity_id, read_json(args.payload_json)
            ))
        elif args.command == "list-entities":
            print_json(engine.structured.list_entities(args.project_id, args.entity_type))
        elif args.command == "get-entity":
            print_json(engine.structured.get_entity(args.entity_type, args.entity_id))
        elif args.command == "configure-governance":
            print_json(
                engine.structured.configure_governance(
                    args.project_id,
                    governance_owner=args.owner,
                    audit_takedown_ready=args.audit_takedown_ready,
                )
            )
        elif args.command == "structured-readiness":
            print_json(engine.structured.readiness_report(args.project_id, args.gate))
        elif args.command == "pass-structured-gate":
            print_json(engine.pass_structured_gate(args.project_id, args.gate))
        elif args.command == "structured-demo":
            print_json(run_structured_demo(engine, args.project_id))
        elif args.command == "add-pilot-entity":
            print_json(engine.pilot.create_entity(args.entity_type, args.project_id, read_json(args.payload_json)))
        elif args.command == "list-pilot-entities":
            print_json(engine.pilot.list_entities(args.project_id, args.entity_type))
        elif args.command == "get-pilot-entity":
            print_json(engine.pilot.get_entity(args.entity_type, args.entity_id))
        elif args.command == "pilot-summary":
            print_json(engine.pilot.summary(args.project_id))
        elif args.command == "pilot-demo":
            print_json(run_pilot_demo(engine, args.project_id))
        elif args.command == "export-softwarex-evidence":
            print_json(build_softwarex_evidence_package(engine, args.project_id, args.output_zip))
        elif args.command == "register-consent":
            print_json(engine.real_pilot.register_consent_document(
                args.project_id,
                document_path=args.document_path,
                title=args.title,
                version=args.version,
                language=args.language,
                ethics_ref=args.ethics_ref,
                effective_from=args.effective_from,
                withdrawal_contact=args.withdrawal_contact,
                retention_policy=args.retention_policy,
                document_id=args.document_id,
            ))
        elif args.command == "import-participants":
            print_json(engine.real_pilot.import_participants_csv(
                args.project_id,
                args.csv_path,
                consent_document_id=args.consent_document_id,
                participant_prefix=args.participant_prefix,
            ))
        elif args.command == "withdraw-participant":
            print_json(engine.real_pilot.withdraw_participant(
                args.project_id, args.participant_id,
                withdrawn_at=args.withdrawn_at, reason=args.reason,
            ))
        elif args.command == "quality-check":
            print_json(engine.real_pilot.quality_check(
                args.project_id, run_label=args.run_label, report_ref=args.report_ref,
            ))
        elif args.command == "analyze-pilot":
            print_json(engine.real_pilot.write_statistical_report(
                args.project_id, args.output_directory, seed=args.seed,
            ))
        elif args.command == "configure-release":
            print_json(engine.real_pilot.upsert_release_profile(
                args.project_id, read_json(args.payload_json),
            ))
        elif args.command == "release-readiness":
            print_json(engine.real_pilot.release_readiness(args.project_id))
        elif args.command == "list-v050-entities":
            print_json(engine.real_pilot.list_entities(args.project_id, args.entity_type))
        elif args.command == "get-v050-entity":
            print_json(engine.real_pilot.get_entity(args.entity_type, args.entity_id))
        elif args.command == "export-submission-release":
            print_json(build_submission_release_package(
                engine, args.project_id, args.output_zip,
                source_root=args.source_root, seed=args.seed,
            ))
        elif args.command == "web":
            run_server(
                args.db,
                host=args.host,
                port=args.port,
                open_browser=args.open_browser,
            )
        else:
            parser.error(f"Unknown command: {args.command}")
        return 0
    except (
        GateValidationError,
        WorkflowStateError,
        StructuredDataError,
        StructuredReadinessError,
        PilotDataError,
        RealPilotError,
        ValueError,
        KeyError,
        sqlite3.IntegrityError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
