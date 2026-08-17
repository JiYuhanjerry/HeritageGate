"""SoftwareX-oriented pilot evidence packages for HeritageGate v0.4."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable, Mapping

from .engine import HeritageGateEngine
from .pilot import PILOT_ENTITY_ALIASES
from .exporter import _neutralize_formula


def _slug(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in value)
    return cleaned.strip("-._") or "project"


def _json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _flatten(row: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (list, dict, tuple)):
            result[key] = _json_cell(value)
        elif isinstance(value, bool):
            result[key] = int(value)
        elif value is None:
            result[key] = ""
        else:
            result[key] = value
    return result


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    materialized = [_flatten(row) for row in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in materialized:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        if not fields:
            return 0
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{k: _neutralize_formula(v) for k, v in row.items()} for row in materialized])
    return len(materialized)


def _fmt(value: Any, digits: int = 1) -> str:
    if value is None:
        return "not available"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value)


def _bar_svg(title: str, labels: list[str], values: list[float], unit: str, *, max_value: float | None = None) -> str:
    width, height = 900, 520
    left, right, top, bottom = 230, 70, 90, 80
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_v = max_value if max_value is not None else (max(values) if values else 1.0)
    max_v = max(max_v, 1e-9)
    n = max(len(values), 1)
    row_h = plot_h / n
    bars = []
    for index, (label, value) in enumerate(zip(labels, values)):
        y = top + index * row_h + row_h * 0.18
        bar_h = row_h * 0.56
        bar_w = max(0, min(plot_w, plot_w * value / max_v))
        bars.append(
            f'<text x="{left-14}" y="{y+bar_h*0.72:.1f}" text-anchor="end" font-size="22">{_xml(label)}</text>'
            f'<rect x="{left}" y="{y:.1f}" width="{plot_w}" height="{bar_h:.1f}" rx="8" fill="#e8eceb"/>'
            f'<rect x="{left}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" rx="8" fill="#315b52"/>'
            f'<text x="{min(left+bar_w+12, width-right+6):.1f}" y="{y+bar_h*0.72:.1f}" font-size="22" font-weight="600">{value:.1f}{_xml(unit)}</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{_xml(title)}">
<rect width="100%" height="100%" fill="white"/>
<text x="{width/2}" y="48" text-anchor="middle" font-size="30" font-family="Times New Roman, serif" font-weight="700">{_xml(title)}</text>
<g font-family="Times New Roman, serif" fill="#1b2428">{''.join(bars)}</g>
<text x="{left+plot_w/2}" y="{height-26}" text-anchor="middle" font-family="Times New Roman, serif" font-size="20">{_xml(unit.strip())}</text>
</svg>'''


def _xml(value: Any) -> str:
    text = str(value)
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _metric_rows(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in ("participant_summary", "installation_summary", "sus_summary", "workflow_benchmark_summary"):
        for metric, value in summary.get(section, {}).items():
            rows.append({"section": section, "metric": metric, "value": value})
    for condition, values in summary.get("condition_summary", {}).items():
        for metric, value in values.items():
            rows.append({"section": f"condition_{condition}", "metric": metric, "value": value})
    return rows


def _readiness_rows(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    checks = summary["softwarex_evidence_readiness"]["checks"]
    descriptions = {
        "protocol_recorded": "A versioned pilot protocol is stored in the project database.",
        "ethics_resolved": "The protocol records approved, exempt, or not-required ethics status.",
        "at_least_5_participants": "At least five consented or exempt participants are recorded.",
        "at_least_5_completed_sessions": "At least five completed pilot sessions are recorded.",
        "installation_evidence": "At least one timed installation record is available.",
        "at_least_10_task_attempts": "At least ten task attempts support task-level analysis.",
        "at_least_5_sus_responses": "At least five SUS responses support a preliminary usability summary.",
        "workflow_comparison_evidence": "At least one HeritageGate-versus-baseline benchmark is available.",
    }
    return [
        {"check": key, "passed": bool(value), "description": descriptions[key]}
        for key, value in checks.items()
    ]


def _report_markdown(project: Mapping[str, Any], summary: Mapping[str, Any], entities: Mapping[str, Any]) -> str:
    hg = summary["condition_summary"]["heritagegate"]
    base = summary["condition_summary"]["baseline"]
    install = summary["installation_summary"]
    sus = summary["sus_summary"]
    bench = summary["workflow_benchmark_summary"]
    study = entities.get("pilot_studies", [])
    protocol = study[0] if study else None
    protocol_text = "No protocol record was available."
    if protocol:
        protocol_text = (
            f"The recorded protocol is **{protocol['study_title']}** (version {protocol['protocol_version']}), "
            f"using a {protocol['study_design'].replace('_', ' ')} design with a planned sample of "
            f"{protocol['planned_sample_size']}. Ethics status is recorded as **{protocol['ethics_status']}**."
        )
    return f"""# HeritageGate SoftwareX pilot evidence report

## Project and provenance

- Project: **{project['name']}**
- Project ID: `{project['id']}`
- Research object: {project['heritage_name']}
- HeritageGate schema: {summary['schema_version']}

This report is generated automatically from the project SQLite database. HeritageGate verifies data structure and arithmetic consistency, but it cannot independently verify whether entries describe real participants, valid consent, or authentic external evidence. Synthetic demonstration records must not be presented as empirical findings.

## Pilot protocol

{protocol_text}

## Installation feasibility

The database contains **{install['records']}** timed installation records. The observed installation success rate is **{_fmt(install['success_rate_pct'])}%**, with a mean duration of **{_fmt(install['mean_seconds'])} seconds** and a median duration of **{_fmt(install['median_seconds'])} seconds**. A total of **{install['total_errors']}** installation errors were recorded.

## Task performance

Under the HeritageGate condition, **{hg['successful_attempts']} of {hg['task_attempts']}** task attempts were successful, corresponding to a completion rate of **{_fmt(hg['task_completion_rate_pct'])}%**. Mean task time was **{_fmt(hg['mean_task_seconds'])} seconds**, with **{_fmt(hg['mean_errors_per_attempt'], 2)}** errors and **{_fmt(hg['mean_assistance_per_attempt'], 2)}** assistance events per attempt.

Under the baseline condition, **{base['successful_attempts']} of {base['task_attempts']}** attempts were successful, corresponding to **{_fmt(base['task_completion_rate_pct'])}%**. Mean task time was **{_fmt(base['mean_task_seconds'])} seconds**, with **{_fmt(base['mean_errors_per_attempt'], 2)}** errors per attempt.

These summaries are descriptive and should not be interpreted as causal estimates unless the underlying study design, allocation process, and inferential analysis support such claims.

## System Usability Scale

The evidence set contains **{sus['responses']}** SUS questionnaires. The mean SUS score is **{_fmt(sus['mean_score'])}**, the median is **{_fmt(sus['median_score'])}**, and the observed range is **{_fmt(sus['minimum'])}–{_fmt(sus['maximum'])}**.

## Workflow benchmark

Across **{bench['records']}** workflow benchmark records, the mean HeritageGate time is **{_fmt(bench['mean_heritagegate_seconds'])} seconds**, compared with **{_fmt(bench['mean_baseline_seconds'])} seconds** for the baseline. The mean within-record time reduction is **{_fmt(bench['mean_time_reduction_pct'])}%**. Where baseline errors were non-zero, the mean error reduction is **{_fmt(bench['mean_error_reduction_pct'])}%**.

## SoftwareX evidence readiness

The automated checklist passes **{summary['softwarex_evidence_readiness']['passed']} of {summary['softwarex_evidence_readiness']['total']}** evidence conditions. This checklist is a preparation aid, not a guarantee of editorial suitability or acceptance.

## Recommended manuscript use

Use the installation, task, SUS, and benchmark results in the *Illustrative examples* and *Impact* sections. Report the participant and study design transparently, distinguish synthetic from empirical records, describe the hardware and operating environment, and avoid inferential claims when the pilot is descriptive or underpowered.
"""


def _snippets(summary: Mapping[str, Any]) -> str:
    hg = summary["condition_summary"]["heritagegate"]
    base = summary["condition_summary"]["baseline"]
    install = summary["installation_summary"]
    sus = summary["sus_summary"]
    bench = summary["workflow_benchmark_summary"]
    return f"""# Candidate SoftwareX evidence sentences

These sentences are generated from database values and require author verification before manuscript use.

## Installation

In the recorded pilot sessions, HeritageGate was installed successfully in {_fmt(install['success_rate_pct'])}% of attempts, with a median installation time of {_fmt(install['median_seconds'])} s.

## Task completion

Users completed {_fmt(hg['task_completion_rate_pct'])}% of recorded tasks under the HeritageGate condition, compared with {_fmt(base['task_completion_rate_pct'])}% under the baseline condition.

## Task time

Mean task duration was {_fmt(hg['mean_task_seconds'])} s with HeritageGate and {_fmt(base['mean_task_seconds'])} s under the baseline workflow.

## Usability

The mean System Usability Scale score across {sus['responses']} responses was {_fmt(sus['mean_score'])} (range {_fmt(sus['minimum'])}–{_fmt(sus['maximum'])}).

## Workflow impact

Across {bench['records']} recorded benchmark units, HeritageGate reduced workflow time by a mean of {_fmt(bench['mean_time_reduction_pct'])}% relative to the documented baseline.

## Required limitation sentence

These pilot results are descriptive, depend on the recorded study design and sample, and should not be generalized beyond the evaluated tasks and environments without further independent testing.
"""


def build_softwarex_evidence_package(
    engine: HeritageGateEngine, project_id: str, output_zip: str | Path
) -> dict[str, Any]:
    """Create a portable SoftwareX pilot evidence package."""
    output = Path(output_zip).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    project = engine.get_project(project_id)
    summary = engine.pilot.summary(project_id)
    entities = engine.pilot.export_project_entities(project_id)
    manifest = engine.export_manifest(project_id)

    with tempfile.TemporaryDirectory(prefix="heritagegate-softwarex-") as temp:
        root = Path(temp) / f"heritagegate-{_slug(project_id)}-softwarex-evidence"
        data_dir = root / "pilot_data"
        figure_dir = root / "figures"
        data_dir.mkdir(parents=True, exist_ok=True)
        figure_dir.mkdir(parents=True, exist_ok=True)

        (root / "project_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        (root / "softwarex_evidence_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        (root / "SoftwareX_evidence_report.md").write_text(
            _report_markdown(project, summary, entities), encoding="utf-8"
        )
        (root / "SoftwareX_results_snippets.md").write_text(_snippets(summary), encoding="utf-8")
        _write_csv(root / "softwarex_readiness_checklist.csv", _readiness_rows(summary))
        _write_csv(root / "pilot_metrics.csv", _metric_rows(summary))

        counts: dict[str, int] = {}
        for entity_type, table in PILOT_ENTITY_ALIASES.items():
            rows = entities.get(table, [])
            counts[table] = _write_csv(data_dir / f"{table}.csv", rows)

        install = summary["installation_summary"]
        hg = summary["condition_summary"]["heritagegate"]
        base = summary["condition_summary"]["baseline"]
        sus = summary["sus_summary"]
        bench = summary["workflow_benchmark_summary"]
        (figure_dir / "figure_installation_success.svg").write_text(
            _bar_svg("Installation success rate", ["HeritageGate"], [float(install["success_rate_pct"] or 0)], "%", max_value=100), encoding="utf-8"
        )
        (figure_dir / "figure_task_completion.svg").write_text(
            _bar_svg("Task completion by condition", ["HeritageGate", "Baseline"], [float(hg["task_completion_rate_pct"] or 0), float(base["task_completion_rate_pct"] or 0)], "%", max_value=100), encoding="utf-8"
        )
        (figure_dir / "figure_mean_task_time.svg").write_text(
            _bar_svg("Mean task duration", ["HeritageGate", "Baseline"], [float(hg["mean_task_seconds"] or 0), float(base["mean_task_seconds"] or 0)], " s"), encoding="utf-8"
        )
        (figure_dir / "figure_sus_score.svg").write_text(
            _bar_svg("Mean System Usability Scale score", ["HeritageGate"], [float(sus["mean_score"] or 0)], "/100", max_value=100), encoding="utf-8"
        )
        (figure_dir / "figure_workflow_time.svg").write_text(
            _bar_svg("Workflow benchmark time", ["HeritageGate", "Baseline"], [float(bench["mean_heritagegate_seconds"] or 0), float(bench["mean_baseline_seconds"] or 0)], " s"), encoding="utf-8"
        )

        metadata = {
            "project_id": project_id,
            "schema_version": summary["schema_version"],
            "package_purpose": "SoftwareX pilot evidence preparation",
            "record_counts": counts,
            "evidence_ready": summary["softwarex_evidence_readiness"]["ready"],
            "data_verification_notice": "HeritageGate validates structure and calculations but cannot verify external truth or consent validity.",
        }
        (root / "package_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        (root / "README.txt").write_text(
            "HeritageGate SoftwareX evidence package\n\n"
            "This package contains pilot protocol records, de-identified participant codes, timed installation and task evidence, SUS scores, workflow benchmarks, analysis-ready CSV files, vector figures, manuscript-ready descriptive sentences, and checksums.\n\n"
            "Do not submit synthetic demonstration records as empirical evidence. Verify consent, ethics status, source references, environments, and all manuscript claims before publication.\n",
            encoding="utf-8",
        )

        checksum_lines: list[str] = []
        for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt"):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            checksum_lines.append(f"{digest}  {path.relative_to(root).as_posix()}")
        (root / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=f"{root.name}/{path.relative_to(root)}")

    return {
        "project_id": project_id,
        "output_zip": str(output),
        "schema_version": summary["schema_version"],
        "evidence_ready": summary["softwarex_evidence_readiness"]["ready"],
        "readiness_passed": summary["softwarex_evidence_readiness"]["passed"],
        "readiness_total": summary["softwarex_evidence_readiness"]["total"],
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "size_bytes": output.stat().st_size,
    }
