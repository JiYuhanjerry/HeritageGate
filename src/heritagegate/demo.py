"""Synthetic end-to-end demonstration data.

The dataset is fictional and deliberately not associated with any living
heritage community. It demonstrates software behaviour only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .version import __version__
from .realpilot import RealPilotError

if TYPE_CHECKING:
    from .engine import HeritageGateEngine

GATE_PAYLOADS: list[dict[str, Any]] = [
    {
        "permission_status": "permissible",
        "rationale": "Synthetic motif invented for software demonstration; no living-community claim.",
        "reviewers": ["demo cultural reviewer", "demo legal reviewer"],
    },
    {
        "authorization_status": "approved",
        "authorizers": ["synthetic data owner"],
        "permitted_uses": ["research demonstration", "software testing"],
        "prohibited_uses": ["representation as authentic heritage", "commercial sale"],
        "attribution_requirements": "Cite the HeritageGate synthetic demo dataset.",
        "revenue_terms": "No revenue permitted for the v0.1 generic demo assets.",
        "authorization_record_ref": "records/authorization-demo-001.json",
    },
    {
        "dataset_id": "HG-SYNTH-001",
        "source_count": 12,
        "technical_metadata_complete": True,
        "cultural_metadata_complete": True,
        "license_terms": "CC0-1.0 for synthetic demo data",
        "capture_log_ref": "logs/capture-demo-001.jsonl",
    },
    {
        "library_version": "0.1.0-demo",
        "elements_count": 6,
        "bearer_annotation": True,
        "prohibited_combinations_documented": True,
        "element_card_schema_ref": "schemas/cultural-element-card.schema.json",
    },
    {
        "model_name": "SyntheticPatternGenerator",
        "model_version": "0.1-demo",
        "constraint_method": "rule-based adapter simulation",
        "provenance_enabled": True,
        "generated_variants": 24,
        "source_element_ids": ["E001", "E002", "E003"],
        "generation_log_ref": "logs/generation-demo-001.jsonl",
    },
    {
        "bearer_approved": True,
        "design_expert_approved": True,
        "production_feasible": True,
        "review_record_ref": "records/review-demo-001.json",
        "reviewers": ["demo bearer-role reviewer", "demo design reviewer"],
    },
    {
        "sample_size": 36,
        "perceived_authenticity": 4.1,
        "perceived_cultural_value": 4.0,
        "story_comprehension": 4.2,
        "purchase_intention": 3.7,
        "recommendation_intention": 3.9,
        "test_channel": "controlled synthetic usability panel",
        "market_test_report_ref": "reports/market-test-demo-001.json",
    },
    {
        "rights_map_current": True,
        "revenue_protocol_active": True,
        "audit_takedown_ready": True,
        "distribution_records_ref": "records/revenue-demo-001.json",
        "governance_owner": "HeritageGate demo administrator",
        "audit_trail_ref": "exports/audit-demo-001.json",
    },
]

STRUCTURED_IDS = {
    "project": "demo-structured-001",
    "bearer": "holder-demo-bearer",
    "designer": "holder-demo-designer",
    "producer": "holder-demo-producer",
    "authorization": "auth-demo-001",
    "element_1": "element-demo-001",
    "element_2": "element-demo-002",
    "model_run": "run-demo-001",
    "review_bearer": "review-demo-bearer",
    "review_design": "review-demo-design",
    "review_production": "review-demo-production",
    "market_test": "market-demo-001",
    "distribution": "distribution-demo-001",
}


def _ensure_entity(
    engine: "HeritageGateEngine",
    entity_type: str,
    entity_id: str,
    project_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        return engine.structured.get_entity(entity_type, entity_id)
    except KeyError:
        return engine.structured.create_entity(entity_type, project_id, payload)


def run_structured_demo(
    engine: "HeritageGateEngine", project_id: str = STRUCTURED_IDS["project"]
) -> dict[str, Any]:
    """Create normalized entities and run a mixed Gate 0-to-7 demonstration."""
    try:
        engine.create_project(
            name="Structured Synthetic Motif Research Demo",
            heritage_name="Fictional cloud-lattice motif (not real ICH)",
            description=(
                "Synthetic v0.3 demonstration of normalized rights, authorization, "
                "element, model, review, market, and revenue entities."
            ),
            project_id=project_id,
        )
    except Exception as exc:
        if "UNIQUE constraint failed" not in str(exc):
            raise

    state = engine.get_project(project_id)
    if state["current_gate"] < 0:
        engine.pass_gate(project_id, 0, GATE_PAYLOADS[0])

    _ensure_entity(
        engine,
        "rights-holder",
        STRUCTURED_IDS["bearer"],
        project_id,
        {
            "id": STRUCTURED_IDS["bearer"],
            "name": "Synthetic motif steward",
            "holder_type": "bearer",
            "authority_basis": "Fictional stewardship role created only for software testing",
            "jurisdiction": "Synthetic demonstration environment",
            "contact_ref": "synthetic://contacts/bearer",
        },
    )
    _ensure_entity(
        engine,
        "rights-holder",
        STRUCTURED_IDS["designer"],
        project_id,
        {
            "id": STRUCTURED_IDS["designer"],
            "name": "Synthetic design reviewer",
            "holder_type": "designer",
            "authority_basis": "Fictional design-review role",
            "contact_ref": "synthetic://contacts/designer",
        },
    )
    _ensure_entity(
        engine,
        "rights-holder",
        STRUCTURED_IDS["producer"],
        project_id,
        {
            "id": STRUCTURED_IDS["producer"],
            "name": "Synthetic production reviewer",
            "holder_type": "producer",
            "authority_basis": "Fictional production-review role",
            "contact_ref": "synthetic://contacts/producer",
        },
    )
    _ensure_entity(
        engine,
        "authorization",
        STRUCTURED_IDS["authorization"],
        project_id,
        {
            "id": STRUCTURED_IDS["authorization"],
            "status": "approved",
            "parties": [
                {
                    "rights_holder_id": STRUCTURED_IDS["bearer"],
                    "party_role": "authorizer",
                },
                {
                    "rights_holder_id": STRUCTURED_IDS["bearer"],
                    "party_role": "beneficiary",
                },
            ],
            "permitted_uses": ["research demonstration", "software testing"],
            "prohibited_uses": [
                "representation as authentic heritage",
                "external commercial deployment",
            ],
            "attribution_requirements": "Identify all assets as synthetic HeritageGate demo content.",
            "revenue_terms": "Synthetic accounting simulation allocates 60% to the fictional steward.",
            "evidence_ref": "synthetic://authorizations/auth-demo-001",
            "signed_at": "2026-07-29",
        },
    )

    state = engine.get_project(project_id)
    if state["current_gate"] < 1:
        engine.pass_structured_gate(project_id, 1)
    if state["current_gate"] < 2:
        engine.pass_gate(project_id, 2, GATE_PAYLOADS[2])

    common_card = {
        "cultural_meaning": "Fictional geometric meaning used solely to test structured annotation.",
        "source_ref": "synthetic://datasets/HG-SYNTH-002",
        "attribution_text": "Synthetic HeritageGate v0.5.1 demonstration element.",
        "permitted_uses": ["research demonstration", "software testing"],
        "prohibited_uses": ["claim of real cultural authenticity"],
        "prohibited_combinations": ["combination with any real sacred or restricted motif"],
        "sensitivity_level": "controlled",
        "status": "approved",
        "version": "0.5.1-demo",
        "annotators": [
            {
                "rights_holder_id": STRUCTURED_IDS["bearer"],
                "annotation_role": "principal",
            }
        ],
    }
    _ensure_entity(
        engine,
        "element-card",
        STRUCTURED_IDS["element_1"],
        project_id,
        {
            **common_card,
            "id": STRUCTURED_IDS["element_1"],
            "element_code": "SYN-LATTICE-A",
            "name": "Synthetic lattice unit A",
            "technical_features": {"symmetry": "fourfold", "line_weight": "medium"},
        },
    )
    _ensure_entity(
        engine,
        "element-card",
        STRUCTURED_IDS["element_2"],
        project_id,
        {
            **common_card,
            "id": STRUCTURED_IDS["element_2"],
            "element_code": "SYN-LATTICE-B",
            "name": "Synthetic lattice unit B",
            "technical_features": {"symmetry": "bilateral", "line_weight": "light"},
        },
    )

    state = engine.get_project(project_id)
    if state["current_gate"] < 3:
        engine.pass_structured_gate(project_id, 3)

    _ensure_entity(
        engine,
        "model-run",
        STRUCTURED_IDS["model_run"],
        project_id,
        {
            "id": STRUCTURED_IDS["model_run"],
            "model_name": "SyntheticPatternGenerator",
            "model_version": "0.2-demo",
            "constraint_method": "rule-based adapter simulation",
            "model_ref": "synthetic://models/pattern-generator-0.2",
            "parameters": {"seed": 20260729, "constraint_strength": 0.85},
            "source_element_ids": [
                STRUCTURED_IDS["element_1"],
                STRUCTURED_IDS["element_2"],
            ],
            "output_count": 24,
            "provenance_ref": "synthetic://logs/generation-demo-002.jsonl",
            "run_status": "completed",
            "started_at": "2026-07-29T00:00:00+00:00",
            "ended_at": "2026-07-29T00:01:00+00:00",
        },
    )
    state = engine.get_project(project_id)
    if state["current_gate"] < 4:
        engine.pass_structured_gate(project_id, 4)

    review_payloads = [
        (
            "expert-review",
            STRUCTURED_IDS["review_bearer"],
            {
                "id": STRUCTURED_IDS["review_bearer"],
                "model_run_id": STRUCTURED_IDS["model_run"],
                "reviewer_rights_holder_id": STRUCTURED_IDS["bearer"],
                "reviewer_role": "bearer",
                "cultural_score": 4.4,
                "decision": "approved",
                "comments": "Synthetic cultural-coherence approval.",
                "evidence_ref": "synthetic://reviews/bearer",
            },
        ),
        (
            "expert-review",
            STRUCTURED_IDS["review_design"],
            {
                "id": STRUCTURED_IDS["review_design"],
                "model_run_id": STRUCTURED_IDS["model_run"],
                "reviewer_rights_holder_id": STRUCTURED_IDS["designer"],
                "reviewer_role": "design_expert",
                "aesthetic_score": 4.2,
                "decision": "approved",
                "comments": "Synthetic design approval.",
                "evidence_ref": "synthetic://reviews/design",
            },
        ),
        (
            "expert-review",
            STRUCTURED_IDS["review_production"],
            {
                "id": STRUCTURED_IDS["review_production"],
                "model_run_id": STRUCTURED_IDS["model_run"],
                "reviewer_rights_holder_id": STRUCTURED_IDS["producer"],
                "reviewer_role": "production_expert",
                "feasibility_score": 4.0,
                "decision": "approved",
                "comments": "Synthetic production-feasibility approval.",
                "evidence_ref": "synthetic://reviews/production",
            },
        ),
    ]
    for entity_type, entity_id, payload in review_payloads:
        _ensure_entity(engine, entity_type, entity_id, project_id, payload)

    state = engine.get_project(project_id)
    if state["current_gate"] < 5:
        engine.pass_structured_gate(project_id, 5)

    _ensure_entity(
        engine,
        "market-test",
        STRUCTURED_IDS["market_test"],
        project_id,
        {
            "id": STRUCTURED_IDS["market_test"],
            "model_run_id": STRUCTURED_IDS["model_run"],
            "sample_size": 36,
            "test_channel": "controlled synthetic usability panel",
            "perceived_authenticity": 4.1,
            "perceived_cultural_value": 4.0,
            "story_comprehension": 4.2,
            "purchase_intention": 3.7,
            "recommendation_intention": 3.9,
            "recommendation": "revise",
            "report_ref": "synthetic://reports/market-test-demo-002",
        },
    )
    state = engine.get_project(project_id)
    if state["current_gate"] < 6:
        engine.pass_structured_gate(project_id, 6)

    _ensure_entity(
        engine,
        "revenue-distribution",
        STRUCTURED_IDS["distribution"],
        project_id,
        {
            "id": STRUCTURED_IDS["distribution"],
            "authorization_id": STRUCTURED_IDS["authorization"],
            "recipient_rights_holder_id": STRUCTURED_IDS["bearer"],
            "revenue_category": "product",
            "gross_amount": 1000.0,
            "currency": "USD",
            "share_percent": 60.0,
            "distributed_amount": 600.0,
            "period_start": "2026-07-01",
            "period_end": "2026-07-31",
            "evidence_ref": "synthetic://accounting/distribution-demo-001",
            "distributed_at": "2026-07-29",
            "notes": "Fictional accounting record; no real revenue or beneficiary.",
        },
    )
    engine.structured.configure_governance(
        project_id,
        governance_owner="HeritageGate synthetic demo administrator",
        audit_takedown_ready=True,
    )
    state = engine.get_project(project_id)
    if state["current_gate"] < 7:
        engine.pass_structured_gate(project_id, 7)
    return engine.export_manifest(project_id)


def _ensure_pilot_entity(
    engine: "HeritageGateEngine",
    entity_type: str,
    entity_id: str,
    project_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        return engine.pilot.get_entity(entity_type, entity_id)
    except KeyError:
        return engine.pilot.create_entity(entity_type, project_id, payload)


def run_pilot_demo(
    engine: "HeritageGateEngine", project_id: str = "demo-pilot-001"
) -> dict[str, Any]:
    """Create a fully synthetic crossover usability pilot and evidence metrics."""
    run_structured_demo(engine, project_id)

    _ensure_pilot_entity(
        engine,
        "study",
        "study-demo-001",
        project_id,
        {
            "id": "study-demo-001",
            "study_title": "Synthetic HeritageGate usability and workflow pilot",
            "protocol_version": "1.0-synthetic",
            "study_design": "crossover",
            "ethics_status": "exempt",
            "ethics_ref": "synthetic://ethics/exempt-demo",
            "planned_sample_size": 8,
            "primary_outcomes": [
                "task completion rate",
                "task duration",
                "System Usability Scale score",
            ],
            "secondary_outcomes": [
                "installation success",
                "task errors",
                "assistance events",
                "workflow benchmark time",
            ],
            "inclusion_criteria": "Adults able to use a web browser and follow written software tasks.",
            "exclusion_criteria": "No real participants; synthetic records are generated for software testing only.",
            "preregistration_ref": "synthetic://protocols/pilot-demo-001",
        },
    )

    tasks = [
        ("T1", "Create project", "Create a new research project.", "A saved project appears in the dashboard.", 0),
        ("T2", "Record authorization", "Enter rights-holder and authorization evidence.", "An approved authorization is saved.", 1),
        ("T3", "Create element card", "Create a cultural-element card with constraints.", "An approved element card is saved.", 3),
        ("T4", "Record expert review", "Record bearer, design, and production review evidence.", "Review records are visible.", 5),
        ("T5", "Export evidence", "Export a project research or evidence package.", "A ZIP export is created.", 7),
    ]
    task_ids: list[str] = []
    for order, (code, title, description, outcome, gate) in enumerate(tasks, 1):
        task_id = f"task-demo-{order:02d}"
        task_ids.append(task_id)
        _ensure_pilot_entity(
            engine,
            "task",
            task_id,
            project_id,
            {
                "id": task_id,
                "task_code": code,
                "title": title,
                "description": description,
                "expected_outcome": outcome,
                "gate_scope": gate,
                "sequence_order": order,
                "required": True,
            },
        )

    # Fixed, deliberately synthetic observations. HeritageGate times are lower on
    # average and completion is higher so report generation can be exercised.
    baseline_times = [
        [190, 310, 280, 360, 210],
        [175, 295, 265, 345, 205],
        [220, 340, 310, 390, 240],
        [185, 320, 300, 370, 225],
        [200, 330, 290, 365, 215],
        [195, 305, 275, 355, 220],
        [210, 350, 320, 400, 250],
        [180, 300, 270, 350, 208],
    ]
    heritagegate_times = [
        [95, 150, 145, 190, 105],
        [88, 140, 135, 180, 98],
        [110, 165, 155, 205, 120],
        [92, 155, 150, 195, 108],
        [100, 160, 148, 198, 112],
        [96, 145, 138, 185, 102],
        [115, 175, 165, 215, 128],
        [90, 142, 136, 182, 100],
    ]
    sus_sets = [
        [4, 2, 4, 2, 4, 2, 4, 2, 4, 2],
        [5, 1, 4, 2, 5, 1, 4, 2, 5, 1],
        [4, 2, 4, 2, 4, 2, 5, 2, 4, 2],
        [4, 1, 4, 2, 4, 2, 4, 1, 4, 2],
        [5, 2, 4, 2, 4, 2, 4, 2, 5, 2],
        [4, 2, 5, 2, 4, 1, 4, 2, 4, 2],
        [4, 2, 4, 3, 4, 2, 4, 2, 4, 2],
        [5, 1, 5, 1, 4, 2, 5, 1, 4, 2],
    ]

    from datetime import datetime, timedelta, timezone

    base_date = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    for i in range(8):
        participant_id = f"participant-demo-{i+1:02d}"
        _ensure_pilot_entity(
            engine,
            "participant",
            participant_id,
            project_id,
            {
                "id": participant_id,
                "participant_code": f"P{i+1:02d}",
                "participant_role": ["researcher", "designer", "student", "developer"][i % 4],
                "experience_level": ["novice", "intermediate", "advanced"][i % 3],
                "consent_status": "exempt",
                "consent_ref": "synthetic://consent/not-a-real-participant",
                "demographics": {"synthetic": True, "cohort": "demo"},
                "notes": "Fictional participant code generated for test coverage.",
            },
        )
        for condition, times in (("baseline", baseline_times[i]), ("heritagegate", heritagegate_times[i])):
            session_id = f"session-demo-{condition}-{i+1:02d}"
            start = base_date + timedelta(days=i, hours=0 if condition == "baseline" else 4)
            total = sum(times) + 300
            end = start + timedelta(seconds=total)
            _ensure_pilot_entity(
                engine,
                "session",
                session_id,
                project_id,
                {
                    "id": session_id,
                    "participant_id": participant_id,
                    "condition": condition,
                    "session_label": f"P{i+1:02d} {condition} synthetic session",
                    "environment": {
                        "os": "Windows 11 synthetic",
                        "python": "3.13",
                        "browser": "Chromium synthetic",
                    },
                    "started_at": start.isoformat(),
                    "ended_at": end.isoformat(),
                    "session_status": "completed",
                    "notes": "Synthetic crossover record; not a real human-subject session.",
                },
            )
            if condition == "heritagegate":
                install_start = start
                install_seconds = [155, 132, 188, 145, 160, 138, 205, 128][i]
                _ensure_pilot_entity(
                    engine,
                    "installation",
                    f"install-demo-{i+1:02d}",
                    project_id,
                    {
                        "id": f"install-demo-{i+1:02d}",
                        "session_id": session_id,
                        "install_method": "wheel",
                        "software_version": __version__,
                        "started_at": install_start.isoformat(),
                        "ended_at": (install_start + timedelta(seconds=install_seconds)).isoformat(),
                        "success": True,
                        "error_count": 1 if i in {2, 6} else 0,
                        "environment": {"synthetic": True, "python": "3.13"},
                        "evidence_ref": f"synthetic://install/P{i+1:02d}",
                    },
                )
            cursor = start + timedelta(seconds=180)
            for task_index, (task_id, seconds) in enumerate(zip(task_ids, times), 1):
                success = True
                completion_status = "completed"
                error_count = 0 if condition == "heritagegate" else (1 if task_index in {2, 4} and i % 3 == 0 else 0)
                assistance = 0 if condition == "heritagegate" else (1 if task_index in {2, 3, 4} and i % 2 == 0 else 0)
                # Two synthetic baseline failures produce a non-perfect baseline completion rate.
                if condition == "baseline" and ((i == 2 and task_index == 4) or (i == 6 and task_index == 3)):
                    success = False
                    completion_status = "failed"
                    error_count += 2
                attempt_id = f"attempt-demo-{condition}-{i+1:02d}-{task_index:02d}"
                _ensure_pilot_entity(
                    engine,
                    "task-attempt",
                    attempt_id,
                    project_id,
                    {
                        "id": attempt_id,
                        "session_id": session_id,
                        "task_id": task_id,
                        "started_at": cursor.isoformat(),
                        "ended_at": (cursor + timedelta(seconds=seconds)).isoformat(),
                        "success": success,
                        "completion_status": completion_status,
                        "assistance_count": assistance,
                        "error_count": error_count,
                        "evidence_ref": f"synthetic://attempt/{attempt_id}",
                        "notes": "Synthetic timed task record.",
                    },
                )
                cursor += timedelta(seconds=seconds + 30)
            if condition == "heritagegate":
                _ensure_pilot_entity(
                    engine,
                    "sus-response",
                    f"sus-demo-{i+1:02d}",
                    project_id,
                    {
                        "id": f"sus-demo-{i+1:02d}",
                        "session_id": session_id,
                        "responses": sus_sets[i],
                        "submitted_at": end.isoformat(),
                        "notes": "Synthetic SUS answers for software testing only.",
                    },
                )

    benchmarks = [
        ("authorization-recording", "one authorization package", 420, 980, 0, 3, 1),
        ("element-card-preparation", "two element cards", 610, 1420, 1, 5, 2),
        ("review-consolidation", "three expert reviews", 480, 1260, 0, 4, 3),
        ("evidence-export", "one complete evidence package", 95, 760, 0, 2, 1),
    ]
    for index, (label, unit, hg_seconds, base_seconds, hg_errors, base_errors, count) in enumerate(benchmarks, 1):
        _ensure_pilot_entity(
            engine,
            "workflow-benchmark",
            f"benchmark-demo-{index:02d}",
            project_id,
            {
                "id": f"benchmark-demo-{index:02d}",
                "benchmark_label": label,
                "workflow_unit": unit,
                "heritagegate_seconds": hg_seconds,
                "baseline_seconds": base_seconds,
                "heritagegate_errors": hg_errors,
                "baseline_errors": base_errors,
                "records_processed": count,
                "evidence_ref": f"synthetic://benchmark/{index:02d}",
                "notes": "Synthetic benchmark used only to exercise evidence calculations.",
            },
        )

    # v0.4 created participants only in the pilot tables. The v0.5 quality
    # checker additionally requires a participant_enrollments row per
    # participant, so a demonstration built from v0.4 records alone reports one
    # blocking MISSING_ENROLLMENT issue per participant and the generated
    # report is headed "Blocking issues: 8". Enrolling the synthetic
    # participants here keeps the bundled demonstration self-consistent, which
    # matters because it is the first thing a new user runs.
    for i in range(8):
        participant_id = f"participant-demo-{i+1:02d}"
        try:
            engine.real_pilot.enroll_existing_participant(
                project_id,
                participant_id,
                source_token=f"synthetic-demo-source-{i+1:02d}",
                eligibility_status="eligible",
                data_use_scope=["pilot_analysis", "software_validation"],
            )
        except RealPilotError as exc:
            # Re-running the demonstration over an existing database is
            # supported; an already-enrolled participant is not an error.
            if "already" not in str(exc).lower():
                raise

    return {
        "manifest": engine.export_manifest(project_id),
        "pilot_summary": engine.pilot.summary(project_id),
        "quality": engine.real_pilot.quality_check(project_id, run_label="pilot-demo"),
    }
