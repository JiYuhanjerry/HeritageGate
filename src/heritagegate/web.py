"""Dependency-free local web interface for HeritageGate v0.5."""

from __future__ import annotations

import html
import json
import tempfile
import threading
import webbrowser
from http import HTTPStatus

from .version import __version__
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, quote, unquote, urlparse

from .engine import HeritageGateEngine
from .exporter import build_research_bundle
from .evidence import build_softwarex_evidence_package
from .release import build_submission_release_package
from .structured import ENTITY_ALIASES
from .pilot import PILOT_ENTITY_ALIASES

GATE_NAMES = {
    0: "Red-line classification",
    1: "Prior authorization",
    2: "Digital capture",
    3: "Cultural-element modelling",
    4: "Constrained AI generation",
    5: "Bearer and expert validation",
    6: "Market testing",
    7: "Asset and revenue governance",
}
STRUCTURED_GATES = {1, 3, 4, 5, 6, 7}
ENTITY_LABELS = {
    "rights-holder": "Rights holders",
    "authorization": "Authorization records",
    "element-card": "Cultural-element cards",
    "model-run": "Model runs",
    "expert-review": "Expert reviews",
    "market-test": "Market tests",
    "revenue-distribution": "Revenue distributions",
}


PILOT_LABELS = {
    "study": "Pilot protocol",
    "participant": "Pilot participants",
    "task": "Pilot tasks",
    "session": "Pilot sessions",
    "installation": "Installation records",
    "task-attempt": "Task attempts",
    "sus-response": "SUS responses",
    "workflow-benchmark": "Workflow benchmarks",
}

PILOT_TEMPLATES: dict[str, dict[str, Any]] = {
    "study": {
        "study_title": "",
        "protocol_version": "1.0",
        "study_design": "crossover",
        "ethics_status": "pending",
        "ethics_ref": "",
        "planned_sample_size": 8,
        "primary_outcomes": ["task completion rate", "task duration", "SUS score"],
        "secondary_outcomes": ["installation success", "errors", "assistance"],
        "inclusion_criteria": "",
        "exclusion_criteria": "",
        "preregistration_ref": "",
    },
    "participant": {
        "participant_code": "P01",
        "participant_role": "researcher",
        "experience_level": "novice",
        "consent_status": "consented",
        "consent_ref": "",
        "demographics": {},
        "notes": "",
    },
    "task": {
        "task_code": "T1",
        "title": "",
        "description": "",
        "expected_outcome": "",
        "gate_scope": None,
        "sequence_order": 1,
        "required": True,
    },
    "session": {
        "participant_id": "REPLACE_WITH_PARTICIPANT_ID",
        "condition": "heritagegate",
        "session_label": "",
        "environment": {"os": "", "python": "", "browser": ""},
        "started_at": "2026-07-29T09:00:00+00:00",
        "ended_at": "2026-07-29T10:00:00+00:00",
        "session_status": "completed",
        "notes": "",
    },
    "installation": {
        "session_id": "REPLACE_WITH_SESSION_ID",
        "install_method": "wheel",
        "software_version": __version__,
        "started_at": "2026-07-29T09:00:00+00:00",
        "ended_at": "2026-07-29T09:03:00+00:00",
        "success": True,
        "error_count": 0,
        "environment": {"os": "", "python": ""},
        "evidence_ref": "",
    },
    "task-attempt": {
        "session_id": "REPLACE_WITH_SESSION_ID",
        "task_id": "REPLACE_WITH_TASK_ID",
        "started_at": "2026-07-29T09:05:00+00:00",
        "ended_at": "2026-07-29T09:08:00+00:00",
        "success": True,
        "completion_status": "completed",
        "assistance_count": 0,
        "error_count": 0,
        "evidence_ref": "",
        "notes": "",
    },
    "sus-response": {
        "session_id": "REPLACE_WITH_SESSION_ID",
        "responses": [4, 2, 4, 2, 4, 2, 4, 2, 4, 2],
        "submitted_at": "2026-07-29T10:00:00+00:00",
        "notes": "",
    },
    "workflow-benchmark": {
        "benchmark_label": "",
        "workflow_unit": "one workflow unit",
        "heritagegate_seconds": 300,
        "baseline_seconds": 600,
        "heritagegate_errors": 0,
        "baseline_errors": 1,
        "records_processed": 1,
        "evidence_ref": "",
        "notes": "",
    },
}

ENTITY_TEMPLATES: dict[str, dict[str, Any]] = {
    "rights-holder": {
        "name": "",
        "holder_type": "bearer",
        "authority_basis": "",
        "jurisdiction": "",
        "contact_ref": "",
        "notes": "",
        "active": True,
    },
    "authorization": {
        "status": "approved",
        "permitted_uses": ["research prototype"],
        "prohibited_uses": ["unattributed commercial reuse"],
        "attribution_requirements": "",
        "revenue_terms": "",
        "evidence_ref": "",
        "valid_from": "",
        "valid_until": "",
        "signed_at": "",
        "revoked_at": "",
        "parties": [{"rights_holder_id": "REPLACE_WITH_HOLDER_ID", "party_role": "authorizer"}],
    },
    "element-card": {
        "element_code": "",
        "name": "",
        "cultural_meaning": "",
        "source_ref": "",
        "attribution_text": "",
        "permitted_uses": ["research prototype"],
        "prohibited_uses": ["misattributed reuse"],
        "technical_features": {"format": "PNG", "dimensions": ""},
        "prohibited_combinations": ["document at least one restricted combination"],
        "sensitivity_level": "controlled",
        "status": "approved",
        "version": "1.0.0",
        "annotators": [{"rights_holder_id": "REPLACE_WITH_HOLDER_ID", "annotation_role": "principal"}],
    },
    "model-run": {
        "model_name": "",
        "model_version": "",
        "constraint_method": "adapter-based generation",
        "model_ref": "",
        "parameters": {"seed": 1},
        "output_count": 1,
        "provenance_ref": "",
        "run_status": "completed",
        "started_at": "",
        "ended_at": "",
        "source_element_ids": ["REPLACE_WITH_ELEMENT_ID"],
    },
    "expert-review": {
        "model_run_id": "REPLACE_WITH_MODEL_RUN_ID",
        "reviewer_rights_holder_id": "REPLACE_WITH_HOLDER_ID",
        "reviewer_role": "bearer",
        "cultural_score": 4.0,
        "aesthetic_score": None,
        "feasibility_score": None,
        "decision": "approved",
        "comments": "",
        "revision_target_gate": None,
        "evidence_ref": "",
    },
    "market-test": {
        "model_run_id": "REPLACE_WITH_MODEL_RUN_ID",
        "sample_size": 30,
        "test_channel": "pilot panel",
        "perceived_authenticity": 4.0,
        "perceived_cultural_value": 4.0,
        "story_comprehension": 4.0,
        "purchase_intention": 4.0,
        "recommendation_intention": 4.0,
        "recommendation": "revise",
        "report_ref": "",
    },
    "revenue-distribution": {
        "authorization_id": "REPLACE_WITH_AUTHORIZATION_ID",
        "recipient_rights_holder_id": "REPLACE_WITH_HOLDER_ID",
        "revenue_category": "product",
        "gross_amount": 100.0,
        "currency": "USD",
        "share_percent": 10.0,
        "distributed_amount": 10.0,
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
        "evidence_ref": "",
        "distributed_at": "",
        "notes": "",
    },
}

CSS = """
:root{--ink:#17212b;--muted:#5d6874;--line:#d9dee4;--paper:#fff;--soft:#f5f7f8;--accent:#315b52;--accent2:#e8f0ed;--ok:#2b6b4d;--warn:#8a5a19;--bad:#9c3c3c}*{box-sizing:border-box}body{margin:0;background:var(--soft);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif;line-height:1.5}a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}.top{background:#152f2b;color:#fff}.top-inner{max-width:1180px;margin:auto;padding:18px 22px;display:flex;align-items:center;justify-content:space-between;gap:20px}.brand{font-size:1.35rem;font-weight:700;letter-spacing:.01em}.top a{color:#fff}.container{max-width:1180px;margin:0 auto;padding:26px 22px 60px}.hero,.panel{background:var(--paper);border:1px solid var(--line);border-radius:14px}.hero{padding:24px}.panel{padding:20px;margin-top:18px}.grid{display:grid;gap:16px}.grid-2{grid-template-columns:repeat(2,minmax(0,1fr))}.grid-3{grid-template-columns:repeat(3,minmax(0,1fr))}.grid-4{grid-template-columns:repeat(4,minmax(0,1fr))}.metric{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:15px}.metric strong{display:block;font-size:1.45rem}.muted{color:var(--muted)}.small{font-size:.88rem}.row{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.btn{display:inline-block;border:1px solid var(--accent);background:var(--accent);color:#fff;padding:9px 13px;border-radius:9px;font-weight:600;cursor:pointer}.btn.secondary{background:#fff;color:var(--accent)}.btn.danger{background:var(--bad);border-color:var(--bad)}.btn:hover{text-decoration:none;filter:brightness(.97)}.badge{display:inline-block;border-radius:999px;padding:4px 9px;font-size:.82rem;font-weight:650;background:var(--accent2);color:var(--accent)}.badge.ok{background:#e4f1e8;color:var(--ok)}.badge.warn{background:#f8eddc;color:var(--warn)}.badge.bad{background:#f6e5e5;color:var(--bad)}.gate-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.gate{border:1px solid var(--line);border-radius:12px;padding:14px;background:#fff;min-height:124px}.gate.done{border-color:#8fb8a4;background:#f4faf7}.gate.next{border:2px solid var(--accent)}.gate-number{font-size:.82rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}.gate h3{font-size:1rem;margin:5px 0 8px}.progress{height:10px;border-radius:99px;background:#e5e8eb;overflow:hidden}.progress span{display:block;height:100%;background:var(--accent)}table{width:100%;border-collapse:collapse;background:#fff}th,td{text-align:left;padding:11px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:.85rem;color:var(--muted);background:#fafbfb}code,pre,textarea{font-family:Consolas,Monaco,monospace}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#10161c;color:#e8eef2;border-radius:10px;padding:14px}label{font-weight:650;display:block;margin:13px 0 5px}input[type=text],input[type=number],textarea,select{width:100%;border:1px solid #bfc7ce;border-radius:9px;padding:10px 11px;background:#fff;color:var(--ink);font-size:1rem}textarea{min-height:360px;resize:vertical}.flash{border-radius:10px;padding:12px 14px;margin-bottom:16px;background:#e8f1ec;color:#215b40}.flash.error{background:#f7e6e6;color:#8b3030}.breadcrumbs{font-size:.9rem;margin-bottom:14px}.empty{padding:28px;text-align:center;color:var(--muted);border:1px dashed #bdc6cd;border-radius:12px}.entity-links{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.entity-link{border:1px solid var(--line);border-radius:10px;padding:12px;background:#fff}.entity-link strong{display:block;font-size:1.2rem}.footer{color:var(--muted);font-size:.85rem;margin-top:30px}@media(max-width:850px){.grid-4,.gate-grid,.entity-links{grid-template-columns:repeat(2,minmax(0,1fr))}.grid-3{grid-template-columns:1fr}.grid-2{grid-template-columns:1fr}}@media(max-width:520px){.grid-4,.gate-grid,.entity-links{grid-template-columns:1fr}.top-inner{align-items:flex-start;flex-direction:column}.container{padding:18px 12px 40px}}
"""


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)



def safe_filename(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in value)
    cleaned = cleaned.strip("-._")
    return cleaned or "project"


def href_project(project_id: str) -> str:
    return f"/projects/{quote(project_id, safe='')}"


def _form_payload(entity_type: str, record: Mapping[str, Any]) -> dict[str, Any]:
    """Remove read-only expansion fields before rendering an edit form."""
    payload = dict(record)
    for field in ("project_id", "created_at", "updated_at"):
        payload.pop(field, None)
    if entity_type == "authorization":
        payload["parties"] = [
            {"rights_holder_id": item["rights_holder_id"], "party_role": item["party_role"]}
            for item in payload.get("parties", [])
        ]
    elif entity_type == "element-card":
        payload["annotators"] = [
            {"rights_holder_id": item["rights_holder_id"], "annotation_role": item["annotation_role"]}
            for item in payload.get("annotators", [])
        ]
    elif entity_type == "model-run":
        payload.pop("source_elements", None)
    return payload


class HeritageGateWebApp:
    """HTML renderer and action layer shared by the HTTP handler and tests."""

    def __init__(self, database: str | Path):
        self.engine = HeritageGateEngine(database)

    def layout(self, title: str, body: str, *, flash: str = "", error: bool = False) -> str:
        flash_html = ""
        if flash:
            flash_html = f'<div class="flash{" error" if error else ""}">{esc(flash)}</div>'
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · HeritageGate</title><style>{CSS}</style></head><body><header class="top"><div class="top-inner"><div class="brand"><a href="/">HeritageGate</a> <span class="small">v{__version__}</span></div><nav><a href="/projects/new">New project</a> &nbsp; <a href="/health">Health</a></nav></div></header><main class="container">{flash_html}{body}<div class="footer">Local research software interface. Default binding is 127.0.0.1; do not expose confidential heritage or financial records to an untrusted network.</div></main></body></html>"""

    def home(self, *, flash: str = "", error: bool = False) -> str:
        projects = self.engine.list_projects()
        cards = ""
        for project in projects:
            pct = max(0, (int(project["current_gate"]) + 1) / 8 * 100)
            cards += f"""<div class="panel"><div class="row"><div><h2 style="margin:0 0 4px"><a href="{href_project(project['id'])}">{esc(project['name'])}</a></h2><div class="muted">{esc(project['heritage_name'])}</div></div><span class="badge {'ok' if project['status']=='completed' else 'warn'}">{esc(project['status'])}</span></div><div style="margin-top:14px" class="progress"><span style="width:{pct:.1f}%"></span></div><div class="small muted" style="margin-top:7px">Current gate: {project['current_gate']} · Project ID: {esc(project['id'])}</div></div>"""
        if not cards:
            cards = '<div class="empty">No projects yet. Create a project or run the structured demo from the command line.</div>'
        body = f"""<section class="hero"><div class="row"><div><h1 style="margin:0">Research workflow dashboard</h1><p class="muted">Manage rights, authorization, provenance, review, market testing, and revenue evidence across Gate 0–7.</p></div><a class="btn" href="/projects/new">Create project</a></div></section>{cards}"""
        return self.layout("Projects", body, flash=flash, error=error)

    def new_project(self, *, flash: str = "", error: bool = False) -> str:
        body = """<div class="breadcrumbs"><a href="/">Projects</a> / New project</div><section class="panel"><h1>Create project</h1><form method="post" action="/projects"><label>Project name</label><input type="text" name="name" required><label>Heritage name or research object</label><input type="text" name="heritage_name" required><label>Description</label><textarea name="description" style="min-height:130px"></textarea><label>Optional project ID</label><input type="text" name="project_id" placeholder="Leave blank to generate a UUID"><p><button class="btn" type="submit">Create project</button></p></form></section>"""
        return self.layout("New project", body, flash=flash, error=error)

    def project_page(self, project_id: str, *, flash: str = "", error: bool = False) -> str:
        project = self.engine.get_project(project_id)
        records = self.engine.gate_records(project_id)
        audit = self.engine.audit_trail(project_id)
        entities = self.engine.structured.export_project_entities(project_id)
        counts = {key: len(value) for key, value in entities.items()}
        gate_html = ""
        current = int(project["current_gate"])
        latest_by_gate = {gate: [r for r in records if int(r["gate"]) == gate][-1] for gate in range(8) if any(int(r["gate"]) == gate for r in records)}
        for gate in range(8):
            latest = latest_by_gate.get(gate)
            done = gate <= current
            next_gate = gate == current + 1
            outcome = latest["outcome"] if latest else ("next" if next_gate else "not recorded")
            badge_class = "ok" if outcome == "passed" else ("warn" if next_gate else "")
            gate_html += f"""<div class="gate{' done' if done else ''}{' next' if next_gate else ''}"><div class="gate-number">Gate {gate}</div><h3>{esc(GATE_NAMES[gate])}</h3><span class="badge {badge_class}">{esc(outcome)}</span>{'<div class="small muted" style="margin-top:9px">Next required transition</div>' if next_gate else ''}</div>"""
        pct = max(0, (current + 1) / 8 * 100)
        entity_links = ""
        for entity_type, label in ENTITY_LABELS.items():
            table = ENTITY_ALIASES[entity_type]
            entity_links += f'<a class="entity-link" href="{href_project(project_id)}/entities/{quote(entity_type)}"><strong>{counts.get(table,0)}</strong>{esc(label)}</a>'
        readiness_rows = ""
        for gate in sorted(STRUCTURED_GATES):
            report = self.engine.structured.readiness_report(project_id, gate)
            status = "Ready" if report["ready"] else "Not ready"
            reason = "Structured records satisfy the gate evidence builder." if report["ready"] else report.get("reason", "")
            readiness_rows += f"<tr><td>Gate {gate}</td><td><span class=\"badge {'ok' if report['ready'] else 'warn'}\">{status}</span></td><td>{esc(reason)}</td></tr>"
        next_action = self._next_gate_action(project)
        pilot_summary = self.engine.pilot.summary(project_id)
        pilot_ready = pilot_summary["softwarex_evidence_readiness"]
        pilot_records = sum(pilot_summary["record_counts"].values())
        release_readiness = self.engine.real_pilot.release_readiness(project_id)
        quality_run = self.engine.real_pilot.latest_quality_run(project_id)
        analysis_run = self.engine.real_pilot.latest_analysis_run(project_id)
        recent_audit = "".join(
            f"<tr><td>{esc(item['created_at'])}</td><td>{esc(item['event_type'])}</td><td>{'' if item['gate'] is None else item['gate']}</td></tr>"
            for item in audit[-8:][::-1]
        ) or '<tr><td colspan="3">No audit events.</td></tr>'
        body = f"""<div class="breadcrumbs"><a href="/">Projects</a> / {esc(project['name'])}</div><section class="hero"><div class="row"><div><h1 style="margin:0">{esc(project['name'])}</h1><div class="muted">{esc(project['heritage_name'])}</div></div><div><span class="badge {'ok' if project['status']=='completed' else 'warn'}">{esc(project['status'])}</span> <a class="btn secondary" href="{href_project(project_id)}/edit">Edit project</a></div></div><p>{esc(project['description'])}</p><div class="progress"><span style="width:{pct:.1f}%"></span></div><div class="small muted" style="margin-top:7px">Project ID: {esc(project_id)} · Current gate: {current} · Schema 0.5.0</div></section><section class="panel"><h2>Gate 0–7 progress</h2><div class="gate-grid">{gate_html}</div>{next_action}</section><section class="panel"><div class="row"><h2>Structured evidence</h2><a class="btn secondary" href="{href_project(project_id)}/governance">Configure governance</a></div><div class="entity-links">{entity_links}</div></section><section class="panel"><h2>Structured gate readiness</h2><table><thead><tr><th>Gate</th><th>Status</th><th>Reason</th></tr></thead><tbody>{readiness_rows}</tbody></table></section><section class="panel"><div class="row"><div><h2>Pilot study and SoftwareX evidence</h2><p class="muted">Capture timed installations, task attempts, SUS responses, and baseline workflow comparisons.</p></div><span class="badge {'ok' if pilot_ready['ready'] else 'warn'}">{pilot_ready['passed']}/{pilot_ready['total']} checks</span></div><div class="grid grid-4"><div class="metric"><strong>{pilot_records}</strong><span class="muted">pilot records</span></div><div class="metric"><strong>{pilot_summary['participant_summary']['total']}</strong><span class="muted">participants</span></div><div class="metric"><strong>{pilot_summary['sus_summary']['responses']}</strong><span class="muted">SUS responses</span></div><div class="metric"><strong>{pilot_summary['workflow_benchmark_summary']['records']}</strong><span class="muted">benchmarks</span></div></div><p><a class="btn" href="{href_project(project_id)}/pilot">Open pilot dashboard</a> <a class="btn secondary" href="{href_project(project_id)}/export/softwarex-evidence.zip">Download SoftwareX evidence ZIP</a></p></section><section class="panel"><div class="row"><div><h2>Real pilot and submission release</h2><p class="muted">Register consent metadata, import de-identified participants, check missingness, generate reproducible statistics, and prepare GitHub, Zenodo, and SoftwareX materials.</p></div><span class="badge {'ok' if release_readiness['ready'] else 'warn'}">{release_readiness['passed']}/{release_readiness['total']} checks</span></div><div class="grid grid-4"><div class="metric"><strong>{len(self.engine.real_pilot.list_entities(project_id, 'enrollment'))}</strong><span class="muted">enrollments</span></div><div class="metric"><strong>{'Pass' if quality_run and quality_run['passed'] else 'Pending'}</strong><span class="muted">data quality</span></div><div class="metric"><strong>{1 if analysis_run else 0}</strong><span class="muted">analysis runs</span></div><div class="metric"><strong>{'Ready' if release_readiness['ready'] else 'Draft'}</strong><span class="muted">submission status</span></div></div><p><a class="btn" href="{href_project(project_id)}/real-pilot">Open real-pilot dashboard</a> <a class="btn secondary" href="{href_project(project_id)}/export/submission-release.zip">Download submission-release ZIP</a></p></section><section class="panel"><h2>Research exports</h2><p class="muted">Manifest JSON preserves nested provenance. The research ZIP adds analysis-ready governance and pilot CSV tables, a data dictionary, and SHA-256 checksums.</p><a class="btn" href="{href_project(project_id)}/export/research.zip">Download research ZIP</a> <a class="btn secondary" href="{href_project(project_id)}/export/manifest.json">Download manifest JSON</a></section><section class="panel"><h2>Recent audit events</h2><table><thead><tr><th>Time</th><th>Event</th><th>Gate</th></tr></thead><tbody>{recent_audit}</tbody></table></section>"""
        return self.layout(project["name"], body, flash=flash, error=error)

    def _next_gate_action(self, project: Mapping[str, Any]) -> str:
        current = int(project["current_gate"])
        gate = current + 1
        if gate > 7:
            return '<div class="flash" style="margin-top:16px">All eight gates are complete.</div>'
        project_id = str(project["id"])
        if gate in STRUCTURED_GATES:
            report = self.engine.structured.readiness_report(project_id, gate)
            disabled = "" if report["ready"] else " disabled"
            reason = "Ready to build evidence from normalized records." if report["ready"] else report.get("reason", "Not ready")
            return f"""<div class="panel" style="background:#fafcfb"><h3>Next action: Gate {gate}</h3><p>{esc(reason)}</p><form method="post" action="{href_project(project_id)}/gates/{gate}/pass"><button class="btn" type="submit"{disabled}>Pass Gate {gate} from structured evidence</button></form></div>"""
        template = {
            0: {"permission_status": "permissible", "rationale": "", "reviewers": ["cultural reviewer", "legal reviewer"]},
            2: {"dataset_id": "", "source_count": 1, "technical_metadata_complete": True, "cultural_metadata_complete": True, "license_terms": "", "capture_log_ref": ""},
        }[gate]
        return f"""<div class="panel" style="background:#fafcfb"><h3>Next action: Gate {gate}</h3><form method="post" action="{href_project(project_id)}/gates/{gate}/pass"><label>Gate evidence JSON</label><textarea name="payload">{esc(json_text(template))}</textarea><p><button class="btn" type="submit">Validate and pass Gate {gate}</button></p></form></div>"""

    def edit_project(self, project_id: str, *, flash: str = "", error: bool = False) -> str:
        project = self.engine.get_project(project_id)
        body = f"""<div class="breadcrumbs"><a href="/">Projects</a> / <a href="{href_project(project_id)}">{esc(project['name'])}</a> / Edit</div><section class="panel"><h1>Edit project</h1><form method="post" action="{href_project(project_id)}/edit"><label>Project name</label><input type="text" name="name" value="{esc(project['name'])}" required><label>Heritage name or research object</label><input type="text" name="heritage_name" value="{esc(project['heritage_name'])}" required><label>Description</label><textarea name="description" style="min-height:150px">{esc(project['description'])}</textarea><p><button class="btn" type="submit">Save project</button></p></form></section>"""
        return self.layout("Edit project", body, flash=flash, error=error)

    def governance_form(self, project_id: str, *, flash: str = "", error: bool = False) -> str:
        project = self.engine.get_project(project_id)
        checked = " checked" if project["audit_takedown_ready"] else ""
        body = f"""<div class="breadcrumbs"><a href="{href_project(project_id)}">{esc(project['name'])}</a> / Governance</div><section class="panel"><h1>Gate 7 governance configuration</h1><form method="post" action="{href_project(project_id)}/governance"><label>Named governance owner</label><input type="text" name="governance_owner" value="{esc(project['governance_owner'])}" required><label style="font-weight:400"><input type="checkbox" name="audit_takedown_ready" value="1"{checked}> Audit and takedown procedure is documented and operational</label><p><button class="btn" type="submit">Save governance configuration</button></p></form></section>"""
        return self.layout("Governance", body, flash=flash, error=error)

    def entity_list(self, project_id: str, entity_type: str, *, flash: str = "", error: bool = False) -> str:
        project = self.engine.get_project(project_id)
        if entity_type not in ENTITY_ALIASES:
            raise KeyError("Unknown entity type")
        records = self.engine.structured.list_entities(project_id, entity_type)
        rows = ""
        for record in records:
            summary = self._entity_summary(entity_type, record)
            eid = str(record["id"])
            rows += f"<tr><td><code>{esc(eid)}</code></td><td>{esc(summary)}</td><td><a class=\"btn secondary\" href=\"{href_project(project_id)}/entities/{quote(entity_type)}/{quote(eid, safe='')}/edit\">Edit JSON</a></td></tr>"
        if not rows:
            rows = '<tr><td colspan="3">No records yet.</td></tr>'
        body = f"""<div class="breadcrumbs"><a href="{href_project(project_id)}">{esc(project['name'])}</a> / {esc(ENTITY_LABELS[entity_type])}</div><section class="panel"><div class="row"><h1>{esc(ENTITY_LABELS[entity_type])}</h1><a class="btn" href="{href_project(project_id)}/entities/{quote(entity_type)}/new">Add record</a></div><table><thead><tr><th>ID</th><th>Summary</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table></section>"""
        return self.layout(ENTITY_LABELS[entity_type], body, flash=flash, error=error)

    @staticmethod
    def _entity_summary(entity_type: str, record: Mapping[str, Any]) -> str:
        fields = {
            "rights-holder": ("name", "holder_type"),
            "authorization": ("status", "evidence_ref"),
            "element-card": ("element_code", "name", "status"),
            "model-run": ("model_name", "model_version", "run_status"),
            "expert-review": ("reviewer_role", "decision", "model_run_id"),
            "market-test": ("test_channel", "recommendation", "sample_size"),
            "revenue-distribution": ("currency", "distributed_amount", "recipient_rights_holder_id"),
        }[entity_type]
        return " · ".join(str(record.get(field, "")) for field in fields)

    def entity_form(self, project_id: str, entity_type: str, entity_id: str | None = None, *, flash: str = "", error: bool = False, payload_text: str | None = None) -> str:
        project = self.engine.get_project(project_id)
        if entity_type not in ENTITY_ALIASES:
            raise KeyError("Unknown entity type")
        editing = entity_id is not None
        if payload_text is None:
            if editing:
                record = self.engine.structured.get_entity(entity_type, entity_id or "")
                payload_text = json_text(_form_payload(entity_type, record))
            else:
                payload_text = json_text(ENTITY_TEMPLATES[entity_type])
        action = f"{href_project(project_id)}/entities/{quote(entity_type)}"
        if editing:
            action += f"/{quote(entity_id or '', safe='')}/edit"
        body = f"""<div class="breadcrumbs"><a href="{href_project(project_id)}">{esc(project['name'])}</a> / <a href="{href_project(project_id)}/entities/{quote(entity_type)}">{esc(ENTITY_LABELS[entity_type])}</a> / {'Edit' if editing else 'Add'}</div><section class="panel"><h1>{'Edit' if editing else 'Add'} {esc(ENTITY_LABELS[entity_type])}</h1><p class="muted">The form uses validated JSON so all structured fields and relationships remain explicit and reproducible. Identifiers referenced in the JSON must already exist in this project.</p><form method="post" action="{action}"><label>Entity JSON</label><textarea name="payload" spellcheck="false">{esc(payload_text)}</textarea><p><button class="btn" type="submit">{'Update record' if editing else 'Create record'}</button></p></form></section>"""
        return self.layout("Entity editor", body, flash=flash, error=error)

    def pilot_page(self, project_id: str, *, flash: str = "", error: bool = False) -> str:
        project = self.engine.get_project(project_id)
        summary = self.engine.pilot.summary(project_id)
        counts = summary["record_counts"]
        links = "".join(
            f'<a class="entity-link" href="{href_project(project_id)}/pilot/{quote(entity_type)}"><strong>{counts.get(table, 0)}</strong>{esc(PILOT_LABELS[entity_type])}</a>'
            for entity_type, table in PILOT_ENTITY_ALIASES.items()
        )
        hg = summary["condition_summary"]["heritagegate"]
        baseline = summary["condition_summary"]["baseline"]
        install = summary["installation_summary"]
        sus = summary["sus_summary"]
        benchmark = summary["workflow_benchmark_summary"]
        readiness_rows = "".join(
            f'<tr><td>{esc(key)}</td><td><span class="badge {"ok" if value else "warn"}">{"Pass" if value else "Missing"}</span></td></tr>'
            for key, value in summary["softwarex_evidence_readiness"]["checks"].items()
        )
        body = f"""<div class="breadcrumbs"><a href="{href_project(project_id)}">{esc(project['name'])}</a> / Pilot study</div><section class="hero"><div class="row"><div><h1 style="margin:0">Pilot study and SoftwareX evidence</h1><p class="muted">Descriptive installation, task, usability, and workflow-comparison evidence.</p></div><span class="badge {'ok' if summary['softwarex_evidence_readiness']['ready'] else 'warn'}">{summary['softwarex_evidence_readiness']['passed']}/{summary['softwarex_evidence_readiness']['total']} checks</span></div></section><section class="panel"><h2>Pilot records</h2><div class="entity-links">{links}</div></section><section class="panel"><h2>Key metrics</h2><div class="grid grid-4"><div class="metric"><strong>{esc(install['success_rate_pct'])}%</strong><span class="muted">installation success</span></div><div class="metric"><strong>{esc(hg['task_completion_rate_pct'])}%</strong><span class="muted">HeritageGate completion</span></div><div class="metric"><strong>{esc(sus['mean_score'])}</strong><span class="muted">mean SUS score</span></div><div class="metric"><strong>{esc(benchmark['mean_time_reduction_pct'])}%</strong><span class="muted">mean benchmark time reduction</span></div></div><table style="margin-top:18px"><thead><tr><th>Condition</th><th>Attempts</th><th>Completion</th><th>Mean seconds</th><th>Mean errors</th></tr></thead><tbody><tr><td>HeritageGate</td><td>{hg['task_attempts']}</td><td>{esc(hg['task_completion_rate_pct'])}%</td><td>{esc(hg['mean_task_seconds'])}</td><td>{esc(hg['mean_errors_per_attempt'])}</td></tr><tr><td>Baseline</td><td>{baseline['task_attempts']}</td><td>{esc(baseline['task_completion_rate_pct'])}%</td><td>{esc(baseline['mean_task_seconds'])}</td><td>{esc(baseline['mean_errors_per_attempt'])}</td></tr></tbody></table></section><section class="panel"><h2>Evidence readiness</h2><table><thead><tr><th>Check</th><th>Status</th></tr></thead><tbody>{readiness_rows}</tbody></table></section><section class="panel"><h2>SoftwareX evidence package</h2><p class="muted">The package contains raw pilot CSV files, computed metrics, a manuscript evidence report, candidate sentences, vector figures, a readiness checklist, and SHA-256 checksums.</p><a class="btn" href="{href_project(project_id)}/export/softwarex-evidence.zip">Download SoftwareX evidence ZIP</a></section>"""
        return self.layout("Pilot study", body, flash=flash, error=error)

    def real_pilot_page(self, project_id: str, *, flash: str = "", error: bool = False) -> str:
        project = self.engine.get_project(project_id)
        readiness = self.engine.real_pilot.release_readiness(project_id)
        quality = self.engine.real_pilot.latest_quality_run(project_id)
        analysis = self.engine.real_pilot.latest_analysis_run(project_id)
        counts = {table: len(rows) for table, rows in self.engine.real_pilot.export_project_entities(project_id).items()}
        readiness_rows = "".join(
            f'<tr><td>{esc(key)}</td><td><span class="badge {"ok" if value else "warn"}">{"Pass" if value else "Action required"}</span></td></tr>'
            for key, value in readiness["checks"].items()
        )
        body = f"""<div class="breadcrumbs"><a href="{href_project(project_id)}">{esc(project['name'])}</a> / Real pilot and release</div><section class="hero"><div class="row"><div><h1 style="margin:0">Real pilot and submission release</h1><p class="muted">Privacy-aware enrollment, withdrawals, integrity checks, deterministic statistics, and publication preparation.</p></div><span class="badge {'ok' if readiness['ready'] else 'warn'}">{readiness['passed']}/{readiness['total']} checks</span></div></section><section class="panel"><h2>Operational records</h2><div class="grid grid-4"><div class="metric"><strong>{counts.get('consent_documents',0)}</strong><span class="muted">consent documents</span></div><div class="metric"><strong>{counts.get('participant_enrollments',0)}</strong><span class="muted">enrollments</span></div><div class="metric"><strong>{counts.get('data_quality_runs',0)}</strong><span class="muted">quality runs</span></div><div class="metric"><strong>{counts.get('analysis_runs',0)}</strong><span class="muted">analysis runs</span></div></div><p class="muted">Consent files and participant CSV imports are intentionally handled through the local command line so browsers do not retain or transmit restricted source files.</p></section><section class="panel"><h2>Latest validation</h2><table><tbody><tr><th>Data quality</th><td>{'Passed' if quality and quality['passed'] else 'No passing run recorded'}</td></tr><tr><th>Blocking issues</th><td>{quality['blocking_issue_count'] if quality else '—'}</td></tr><tr><th>Analysis input SHA-256</th><td><code>{analysis['input_sha256'] if analysis else '—'}</code></td></tr><tr><th>Release evidence status</th><td>{esc(readiness['profile']['evidence_status']) if readiness['profile'] else 'No release profile'}</td></tr></tbody></table></section><section class="panel"><h2>Submission readiness</h2><table><thead><tr><th>Check</th><th>Status</th></tr></thead><tbody>{readiness_rows}</tbody></table></section><section class="panel"><h2>Privacy-safe submission package</h2><p class="muted">The package excludes participant rows, participant codes, consent files, identity hashes, and raw session evidence. It contains aggregate analysis, GitHub and Zenodo metadata, SoftwareX tables, highlights, a manuscript draft, and checksums.</p><a class="btn" href="{href_project(project_id)}/export/submission-release.zip">Download submission-release ZIP</a></section>"""
        return self.layout("Real pilot and release", body, flash=flash, error=error)

    def pilot_entity_list(self, project_id: str, entity_type: str, *, flash: str = "", error: bool = False) -> str:
        project = self.engine.get_project(project_id)
        if entity_type not in PILOT_ENTITY_ALIASES:
            raise KeyError("Unknown pilot entity type")
        records = self.engine.pilot.list_entities(project_id, entity_type)
        rows = ""
        for record in records:
            eid = str(record["id"])
            summary_fields = {
                "study": ("study_title", "protocol_version", "ethics_status"),
                "participant": ("participant_code", "participant_role", "experience_level"),
                "task": ("task_code", "title", "gate_scope"),
                "session": ("session_label", "condition", "session_status"),
                "installation": ("software_version", "duration_seconds", "success"),
                "task-attempt": ("session_id", "task_id", "success", "duration_seconds"),
                "sus-response": ("session_id", "sus_score"),
                "workflow-benchmark": ("benchmark_label", "heritagegate_seconds", "baseline_seconds"),
            }[entity_type]
            text = " · ".join(str(record.get(field, "")) for field in summary_fields)
            rows += f"<tr><td><code>{esc(eid)}</code></td><td>{esc(text)}</td></tr>"
        if not rows:
            rows = '<tr><td colspan="2">No records yet.</td></tr>'
        body = f"""<div class="breadcrumbs"><a href="{href_project(project_id)}">{esc(project['name'])}</a> / <a href="{href_project(project_id)}/pilot">Pilot</a> / {esc(PILOT_LABELS[entity_type])}</div><section class="panel"><div class="row"><h1>{esc(PILOT_LABELS[entity_type])}</h1><a class="btn" href="{href_project(project_id)}/pilot/{quote(entity_type)}/new">Add record</a></div><table><thead><tr><th>ID</th><th>Summary</th></tr></thead><tbody>{rows}</tbody></table></section>"""
        return self.layout(PILOT_LABELS[entity_type], body, flash=flash, error=error)

    def pilot_entity_form(self, project_id: str, entity_type: str, *, flash: str = "", error: bool = False, payload_text: str | None = None) -> str:
        project = self.engine.get_project(project_id)
        if entity_type not in PILOT_ENTITY_ALIASES:
            raise KeyError("Unknown pilot entity type")
        if payload_text is None:
            payload_text = json_text(PILOT_TEMPLATES[entity_type])
        action = f"{href_project(project_id)}/pilot/{quote(entity_type)}"
        body = f"""<div class="breadcrumbs"><a href="{href_project(project_id)}">{esc(project['name'])}</a> / <a href="{href_project(project_id)}/pilot">Pilot</a> / <a href="{href_project(project_id)}/pilot/{quote(entity_type)}">{esc(PILOT_LABELS[entity_type])}</a> / Add</div><section class="panel"><h1>Add {esc(PILOT_LABELS[entity_type])}</h1><p class="muted">Use de-identified participant codes. Do not store names, contact details, or confidential consent documents in demonstration databases.</p><form method="post" action="{action}"><label>Pilot record JSON</label><textarea name="payload" spellcheck="false">{esc(payload_text)}</textarea><p><button class="btn" type="submit">Create pilot record</button></p></form></section>"""
        return self.layout("Pilot record editor", body, flash=flash, error=error)

    def softwarex_evidence_zip_bytes(self, project_id: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix="heritagegate-softwarex-web-") as temp:
            output = Path(temp) / f"heritagegate-{project_id}-softwarex-evidence.zip"
            build_softwarex_evidence_package(self.engine, project_id, output)
            return output.read_bytes()

    def submission_release_zip_bytes(self, project_id: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix="heritagegate-submission-web-") as temp:
            output = Path(temp) / f"heritagegate-{project_id}-submission-release.zip"
            build_submission_release_package(self.engine, project_id, output)
            return output.read_bytes()

    def manifest_bytes(self, project_id: str) -> bytes:
        return json.dumps(self.engine.export_manifest(project_id), ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")

    def research_zip_bytes(self, project_id: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix="heritagegate-web-") as temp:
            output = Path(temp) / f"heritagegate-{project_id}-research.zip"
            build_research_bundle(self.engine, project_id, output)
            return output.read_bytes()


class HeritageGateRequestHandler(BaseHTTPRequestHandler):
    server_version = f"HeritageGate/{__version__}"

    @property
    def app(self) -> HeritageGateWebApp:
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        # Keep concise standard logs while avoiding accidental form-body logging.
        super().log_message(format, *args)

    def _send(self, content: bytes, content_type: str, status: int = 200, headers: Mapping[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(content)

    def _html(self, page: str, status: int = 200) -> None:
        self._send(page.encode("utf-8"), "text/html; charset=utf-8", status)

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def _form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 2_000_000:
            raise ValueError("Form is too large")
        body = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(body, keep_blank_values=True)
        return {key: values[-1] for key, values in parsed.items()}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            if path == "/":
                self._html(self.app.home())
                return
            if path == "/projects/new":
                self._html(self.app.new_project())
                return
            if path == "/health":
                content = json.dumps({"status": "ok", "version": __version__, "schema_version": "0.5.0"}).encode()
                self._send(content, "application/json; charset=utf-8")
                return
            if path == "/api/projects":
                self._send(json.dumps(self.app.engine.list_projects(), ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8")
                return
            parts = [unquote(part) for part in path.split("/") if part]
            if len(parts) >= 2 and parts[0] == "projects":
                project_id = parts[1]
                base = href_project(project_id)
                if len(parts) == 2:
                    self._html(self.app.project_page(project_id))
                    return
                if parts[2:] == ["edit"]:
                    self._html(self.app.edit_project(project_id))
                    return
                if parts[2:] == ["governance"]:
                    self._html(self.app.governance_form(project_id))
                    return
                if parts[2:] == ["pilot"]:
                    self._html(self.app.pilot_page(project_id))
                    return
                if parts[2:] == ["real-pilot"]:
                    self._html(self.app.real_pilot_page(project_id))
                    return
                if len(parts) == 4 and parts[2] == "pilot":
                    self._html(self.app.pilot_entity_list(project_id, parts[3]))
                    return
                if len(parts) == 5 and parts[2] == "pilot" and parts[4] == "new":
                    self._html(self.app.pilot_entity_form(project_id, parts[3]))
                    return
                if parts[2:] == ["export", "manifest.json"]:
                    data = self.app.manifest_bytes(project_id)
                    self._send(data, "application/json; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="heritagegate-{safe_filename(project_id)}-manifest.json"'})
                    return
                if parts[2:] == ["export", "research.zip"]:
                    data = self.app.research_zip_bytes(project_id)
                    self._send(data, "application/zip", headers={"Content-Disposition": f'attachment; filename="heritagegate-{safe_filename(project_id)}-research.zip"'})
                    return
                if parts[2:] == ["export", "softwarex-evidence.zip"]:
                    data = self.app.softwarex_evidence_zip_bytes(project_id)
                    self._send(data, "application/zip", headers={"Content-Disposition": f'attachment; filename="heritagegate-{safe_filename(project_id)}-softwarex-evidence.zip"'})
                    return
                if parts[2:] == ["export", "submission-release.zip"]:
                    data = self.app.submission_release_zip_bytes(project_id)
                    self._send(data, "application/zip", headers={"Content-Disposition": f'attachment; filename="heritagegate-{safe_filename(project_id)}-submission-release.zip"'})
                    return
                if len(parts) == 4 and parts[2] == "entities":
                    self._html(self.app.entity_list(project_id, parts[3]))
                    return
                if len(parts) == 5 and parts[2] == "entities" and parts[4] == "new":
                    self._html(self.app.entity_form(project_id, parts[3]))
                    return
                if len(parts) == 6 and parts[2] == "entities" and parts[5] == "edit":
                    self._html(self.app.entity_form(project_id, parts[3], parts[4]))
                    return
                if parts[2:] == ["api"]:
                    self._send(json.dumps(self.app.engine.export_manifest(project_id), ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8")
                    return
            self._html(self.app.layout("Not found", '<section class="panel"><h1>Not found</h1><p>The requested page does not exist.</p></section>'), 404)
        except Exception as exc:
            self._html(self.app.layout("Error", f'<section class="panel"><h1>Request failed</h1><p>{esc(exc)}</p><p><a href="/">Return to projects</a></p></section>', flash=str(exc), error=True), 500)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        form: dict[str, str] = {}
        try:
            form = self._form()
            if path == "/projects":
                project = self.app.engine.create_project(
                    name=form.get("name", ""),
                    heritage_name=form.get("heritage_name", ""),
                    description=form.get("description", ""),
                    project_id=form.get("project_id") or None,
                )
                self._redirect(href_project(project["id"]))
                return
            parts = [unquote(part) for part in path.split("/") if part]
            if len(parts) >= 2 and parts[0] == "projects":
                project_id = parts[1]
                base = href_project(project_id)
                if parts[2:] == ["edit"]:
                    self.app.engine.update_project(
                        project_id,
                        name=form.get("name", ""),
                        heritage_name=form.get("heritage_name", ""),
                        description=form.get("description", ""),
                    )
                    self._redirect(base)
                    return
                if parts[2:] == ["governance"]:
                    self.app.engine.structured.configure_governance(
                        project_id,
                        governance_owner=form.get("governance_owner", ""),
                        audit_takedown_ready=form.get("audit_takedown_ready") == "1",
                    )
                    self._redirect(base)
                    return
                if len(parts) == 5 and parts[2] == "gates" and parts[4] == "pass":
                    gate = int(parts[3])
                    if gate in STRUCTURED_GATES:
                        self.app.engine.pass_structured_gate(project_id, gate)
                    else:
                        payload = json.loads(form.get("payload", "{}"))
                        if not isinstance(payload, dict):
                            raise ValueError("Gate payload must be a JSON object")
                        self.app.engine.pass_gate(project_id, gate, payload)
                    self._redirect(base)
                    return
                if len(parts) == 4 and parts[2] == "pilot":
                    entity_type = parts[3]
                    payload = json.loads(form.get("payload", "{}"))
                    self.app.engine.pilot.create_entity(entity_type, project_id, payload)
                    self._redirect(f"{base}/pilot/{quote(entity_type)}")
                    return
                if len(parts) == 4 and parts[2] == "entities":
                    entity_type = parts[3]
                    payload = json.loads(form.get("payload", "{}"))
                    self.app.engine.structured.create_entity(entity_type, project_id, payload)
                    self._redirect(f"{base}/entities/{quote(entity_type)}")
                    return
                if len(parts) == 6 and parts[2] == "entities" and parts[5] == "edit":
                    entity_type, entity_id = parts[3], parts[4]
                    payload = json.loads(form.get("payload", "{}"))
                    self.app.engine.structured.update_entity(entity_type, project_id, entity_id, payload)
                    self._redirect(f"{base}/entities/{quote(entity_type)}")
                    return
            self._html(self.app.layout("Not found", '<section class="panel"><h1>Not found</h1></section>'), 404)
        except Exception as exc:
            # Preserve submitted JSON on entity forms to make correction easier.
            parts = [unquote(part) for part in path.split("/") if part]
            if len(parts) >= 4 and parts[0] == "projects" and parts[2] == "pilot":
                self._html(self.app.pilot_entity_form(parts[1], parts[3], flash=str(exc), error=True, payload_text=form.get("payload", "{}")), 400)
            elif len(parts) >= 4 and parts[0] == "projects" and parts[2] == "entities":
                entity_id = parts[4] if len(parts) >= 6 and parts[-1] == "edit" else None
                self._html(self.app.entity_form(parts[1], parts[3], entity_id, flash=str(exc), error=True, payload_text=form.get("payload", "{}")), 400)
            elif path == "/projects":
                self._html(self.app.new_project(flash=str(exc), error=True), 400)
            elif len(parts) >= 2 and parts[0] == "projects":
                self._html(self.app.project_page(parts[1], flash=str(exc), error=True), 400)
            else:
                self._html(self.app.layout("Error", '<section class="panel"><h1>Request failed</h1></section>', flash=str(exc), error=True), 400)


class HeritageGateHTTPServer(ThreadingHTTPServer):
    # Request threads must not prevent clean shutdown on Windows.
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], app: HeritageGateWebApp):
        super().__init__(address, HeritageGateRequestHandler)
        self.app = app


def run_server(
    database: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
) -> None:
    """Run the local web application until interrupted."""
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    app = HeritageGateWebApp(database)
    server = HeritageGateHTTPServer((host, port), app)
    url = f"http://{host}:{port}/"
    print(f"HeritageGate v{__version__} web interface: {url}")
    print(f"Database: {Path(database).expanduser().resolve()}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping HeritageGate web interface.")
    finally:
        server.server_close()
