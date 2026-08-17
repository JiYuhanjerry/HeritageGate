"""Analysis-ready JSON/CSV export utilities for HeritageGate v0.5."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable, Mapping

from .engine import HeritageGateEngine
from .structured import ENTITY_ALIASES
from .pilot import PILOT_ENTITY_ALIASES
from .realpilot import REAL_PILOT_ENTITY_ALIASES

ENTITY_TYPES = tuple(ENTITY_ALIASES)
PILOT_ENTITY_TYPES = tuple(PILOT_ENTITY_ALIASES)
REAL_PILOT_ENTITY_TYPES = tuple(REAL_PILOT_ENTITY_ALIASES)



def _safe_slug(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in value)
    cleaned = cleaned.strip("-._")
    return cleaned or "project"

DATA_DICTIONARY: dict[str, str] = {
    "projects": "One row per HeritageGate project, including workflow state and governance readiness.",
    "gate_records": "All passed, failed, and recorded gate evidence events in chronological order.",
    "gate_summary": "One row per Gate 0-7 summarising the latest outcome and event count.",
    "audit_trail": "Immutable project-level audit events with JSON-encoded details.",
    "rights_holders": "Named people, communities, institutions, or other actors with rights or authority claims.",
    "authorization_records": "Prior-authorization decisions, permitted/prohibited uses, attribution, revenue terms, and parties.",
    "cultural_element_cards": "Versioned cultural-semantic and technical annotations used to constrain AI generation.",
    "model_runs": "Generative-model executions with parameters, provenance references, outputs, and source elements.",
    "expert_reviews": "Role-specific bearer, cultural, design, production, legal, or other review decisions.",
    "market_tests": "Cultural-reception and commercial-intention metrics collected at Gate 6.",
    "revenue_distributions": "Revenue allocations linked to approved authorizations and named recipients.",
    "entity_counts": "Counts of normalized governance entity classes for the exported project.",
    "pilot_studies": "Versioned pilot-study protocol and ethics metadata.",
    "pilot_participants": "De-identified pilot participant codes, roles, experience, and consent status.",
    "pilot_tasks": "Standardized usability and workflow tasks.",
    "pilot_sessions": "Participant sessions and experimental conditions.",
    "installation_records": "Timed installation attempts and environment evidence.",
    "pilot_task_attempts": "Task-level duration, completion, error, and assistance records.",
    "sus_responses": "Ten-item System Usability Scale responses and computed 0-100 scores.",
    "workflow_benchmarks": "HeritageGate-versus-baseline time and error comparisons.",
    "pilot_metrics": "Automatically calculated descriptive pilot-study metrics.",
    "consent_documents": "Versioned consent-document metadata and SHA-256 digests; local document paths are excluded from CSV exports.",
    "participant_import_batches": "Participant import provenance and sanitized row-level rejection reasons.",
    "participant_enrollments": "De-identified enrollment, eligibility, withdrawal, and data-use scope; identity hashes are excluded from CSV exports.",
    "data_quality_runs": "Automated consent, missingness, study-design, and integrity checks.",
    "analysis_runs": "Deterministic statistical results with random seed and input SHA-256.",
    "release_profiles": "GitHub, Zenodo, SoftwareX, authorship, license, and release metadata.",
}


def _json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _flatten_row(row: Mapping[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (dict, list, tuple)):
            flat[key] = _json_cell(value)
        elif isinstance(value, bool):
            flat[key] = int(value)
        elif value is None:
            flat[key] = ""
        else:
            flat[key] = value
    return flat


# Spreadsheet applications treat a cell beginning with one of these as a
# formula. Because these exports are written with a UTF-8 BOM specifically so
# that Excel opens them cleanly, and because several fields (notes, titles,
# labels) carry text supplied by collaborators, a value such as
# `=cmd|'/c calc'!A1` would execute on open. Prefixing with an apostrophe is the
# standard neutralisation: Excel and LibreOffice treat the cell as text and do
# not display the apostrophe.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _neutralize_formula(value: Any) -> Any:
    if isinstance(value, str) and value[:1] in _FORMULA_PREFIXES:
        return "'" + value
    return value


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    materialized = [
        {k: _neutralize_formula(v) for k, v in _flatten_row(row).items()}
        for row in rows
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in materialized:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        if not fieldnames:
            handle.write("")
            return 0
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(materialized)
    return len(materialized)


def _gate_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for gate in range(8):
        matching = [record for record in records if int(record["gate"]) == gate]
        latest = matching[-1] if matching else None
        rows.append(
            {
                "gate": gate,
                "record_count": len(matching),
                "latest_outcome": latest["outcome"] if latest else "not_recorded",
                "latest_created_at": latest["created_at"] if latest else "",
                "latest_payload": latest["payload"] if latest else {},
            }
        )
    return rows


def _sanitize_real_rows(table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove local paths and pseudonymization secrets from routine CSV exports."""
    sanitized: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if table == "consent_documents":
            item.pop("body_ref", None)
        if table == "participant_enrollments":
            item.pop("identity_token_hash", None)
            item.pop("source_row_hash", None)
        sanitized.append(item)
    return sanitized


def export_csv_directory(
    engine: HeritageGateEngine, project_id: str, output_dir: str | Path
) -> dict[str, Any]:
    """Write analysis-ready CSV files and a JSON manifest to a directory."""
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    manifest = engine.export_manifest(project_id)
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    counts: dict[str, int] = {}
    counts["projects"] = _write_csv(destination / "projects.csv", [manifest["project"]])
    counts["gate_records"] = _write_csv(
        destination / "gate_records.csv", manifest["gate_records"]
    )
    counts["gate_summary"] = _write_csv(
        destination / "gate_summary.csv", _gate_summary(manifest["gate_records"])
    )
    counts["audit_trail"] = _write_csv(
        destination / "audit_trail.csv", manifest["audit_trail"]
    )

    entities = manifest["structured_entities"]
    for entity_type in ENTITY_TYPES:
        table = ENTITY_ALIASES[entity_type]
        records = entities.get(table, [])
        counts[table] = _write_csv(destination / f"{table}.csv", records)

    pilot_entities = manifest.get("pilot_entities", {})
    for entity_type in PILOT_ENTITY_TYPES:
        table = PILOT_ENTITY_ALIASES[entity_type]
        records = pilot_entities.get(table, [])
        counts[table] = _write_csv(destination / f"{table}.csv", records)

    real_entities = manifest.get("real_pilot_entities", {})
    for entity_type in REAL_PILOT_ENTITY_TYPES:
        table = REAL_PILOT_ENTITY_ALIASES[entity_type]
        records = _sanitize_real_rows(table, real_entities.get(table, []))
        counts[table] = _write_csv(destination / f"{table}.csv", records)

    pilot_summary = manifest.get("pilot_summary", {})
    pilot_metric_rows = []
    for section in ("participant_summary", "installation_summary", "sus_summary", "workflow_benchmark_summary"):
        for metric, value in pilot_summary.get(section, {}).items():
            pilot_metric_rows.append({"section": section, "metric": metric, "value": value})
    for condition, values in pilot_summary.get("condition_summary", {}).items():
        for metric, value in values.items():
            pilot_metric_rows.append({"section": f"condition_{condition}", "metric": metric, "value": value})
    counts["pilot_metrics"] = _write_csv(destination / "pilot_metrics.csv", pilot_metric_rows)

    entity_count_rows = [
        {"entity_table": table, "record_count": len(entities.get(table, []))}
        for table in ENTITY_ALIASES.values()
    ] + [
        {"entity_table": table, "record_count": len(pilot_entities.get(table, []))}
        for table in PILOT_ENTITY_ALIASES.values()
    ] + [
        {"entity_table": table, "record_count": len(real_entities.get(table, []))}
        for table in REAL_PILOT_ENTITY_ALIASES.values()
    ]
    counts["entity_counts"] = _write_csv(
        destination / "entity_counts.csv", entity_count_rows
    )

    dictionary_rows = [
        {"file": f"{name}.csv", "description": description}
        for name, description in DATA_DICTIONARY.items()
    ]
    counts["data_dictionary"] = _write_csv(
        destination / "data_dictionary.csv", dictionary_rows
    )

    readme = f"""HeritageGate research export\n\nProject ID: {project_id}\nSchema version: {manifest['schema_version']}\nProject status: {manifest['project']['status']}\nCurrent gate: {manifest['project']['current_gate']}\n\nContents\n--------\nmanifest.json preserves the complete nested project record.\nCSV files provide analysis-ready tables encoded as UTF-8 with BOM for Excel compatibility.\nNested relationships are represented as compact JSON strings in individual CSV cells.\nAll example records distributed with HeritageGate are synthetic unless explicitly replaced by the user.\n\nDisclosure level\n----------------\nThis is a RESTRICTED export for the research team, not a shareable package.\nThe CSV tables omit consent-file paths and participant identity hashes, but\nmanifest.json in this same bundle preserves the complete record and DOES contain\nparticipant codes, identity-token hashes, source-row hashes, and the local path of\nany registered consent document. Treat this bundle with the same controls as the\ndatabase itself. To produce a package suitable for a repository, a journal, or a\ncollaborator, use export-submission-release instead, which excludes participant-level\nrecords entirely.\n\nEthics and rights\n-----------------\nThis export does not itself establish permission to share heritage data, personal information,\ncontracts, model weights, or financial records. Export only records that may lawfully and\nethically leave the controlled project environment.\n"""
    (destination / "README.txt").write_text(readme, encoding="utf-8")

    checksum_lines: list[str] = []
    for path in sorted(p for p in destination.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt"):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checksum_lines.append(f"{digest}  {path.name}")
    (destination / "SHA256SUMS.txt").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )
    return {
        "project_id": project_id,
        "output_directory": str(destination),
        "schema_version": manifest["schema_version"],
        "files": sorted(path.name for path in destination.iterdir() if path.is_file()),
        "row_counts": counts,
    }


def build_research_bundle(
    engine: HeritageGateEngine, project_id: str, output_zip: str | Path
) -> dict[str, Any]:
    """Create a portable ZIP containing JSON, CSV, documentation, and checksums."""
    output = Path(output_zip).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="heritagegate-export-") as temporary:
        slug = _safe_slug(project_id)
        folder = Path(temporary) / f"heritagegate-{slug}"
        metadata = export_csv_directory(engine, project_id, folder)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=f"heritagegate-{slug}/{path.relative_to(folder)}")
    metadata["output_zip"] = str(output)
    metadata["sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    metadata["size_bytes"] = output.stat().st_size
    return metadata


def copy_research_bundle_to(
    engine: HeritageGateEngine, project_id: str, output: str | Path
) -> Path:
    """Compatibility helper used by the web server to build a download."""
    path = Path(output).expanduser().resolve()
    build_research_bundle(engine, project_id, path)
    return path
