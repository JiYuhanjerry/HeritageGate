"""SQLite persistence layer for HeritageGate."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = "0.5.0"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    heritage_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    current_gate INTEGER NOT NULL DEFAULT -1 CHECK (current_gate BETWEEN -1 AND 7),
    status TEXT NOT NULL DEFAULT 'active',
    governance_owner TEXT NOT NULL DEFAULT '',
    audit_takedown_ready INTEGER NOT NULL DEFAULT 0 CHECK (audit_takedown_ready IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gate_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    gate INTEGER NOT NULL CHECK (gate BETWEEN 0 AND 7),
    outcome TEXT NOT NULL CHECK (outcome IN ('passed', 'failed', 'recorded')),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    gate INTEGER,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rights_holders (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    holder_type TEXT NOT NULL CHECK (
        holder_type IN (
            'bearer', 'community', 'cultural_authority', 'institution',
            'designer', 'platform', 'producer', 'other'
        )
    ),
    authority_basis TEXT NOT NULL,
    jurisdiction TEXT NOT NULL DEFAULT '',
    contact_ref TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS authorization_records (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('approved', 'pending', 'restricted', 'revoked')),
    permitted_uses_json TEXT NOT NULL,
    prohibited_uses_json TEXT NOT NULL,
    attribution_requirements TEXT NOT NULL,
    revenue_terms TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    valid_from TEXT NOT NULL DEFAULT '',
    valid_until TEXT NOT NULL DEFAULT '',
    signed_at TEXT NOT NULL DEFAULT '',
    revoked_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS authorization_parties (
    authorization_id TEXT NOT NULL,
    rights_holder_id TEXT NOT NULL,
    party_role TEXT NOT NULL DEFAULT 'authorizer' CHECK (
        party_role IN ('authorizer', 'beneficiary', 'representative')
    ),
    PRIMARY KEY (authorization_id, rights_holder_id, party_role),
    FOREIGN KEY (authorization_id) REFERENCES authorization_records(id) ON DELETE CASCADE,
    FOREIGN KEY (rights_holder_id) REFERENCES rights_holders(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS cultural_element_cards (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    element_code TEXT NOT NULL,
    name TEXT NOT NULL,
    cultural_meaning TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    attribution_text TEXT NOT NULL,
    permitted_uses_json TEXT NOT NULL,
    prohibited_uses_json TEXT NOT NULL,
    technical_features_json TEXT NOT NULL,
    prohibited_combinations_json TEXT NOT NULL,
    sensitivity_level TEXT NOT NULL CHECK (
        sensitivity_level IN ('open', 'controlled', 'restricted', 'unknown')
    ),
    status TEXT NOT NULL CHECK (status IN ('draft', 'approved', 'retired')),
    version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, element_code, version),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS element_annotators (
    element_card_id TEXT NOT NULL,
    rights_holder_id TEXT NOT NULL,
    annotation_role TEXT NOT NULL DEFAULT 'co-annotator' CHECK (
        annotation_role IN ('principal', 'co-annotator', 'reviewer')
    ),
    PRIMARY KEY (element_card_id, rights_holder_id, annotation_role),
    FOREIGN KEY (element_card_id) REFERENCES cultural_element_cards(id) ON DELETE CASCADE,
    FOREIGN KEY (rights_holder_id) REFERENCES rights_holders(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS model_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    constraint_method TEXT NOT NULL,
    model_ref TEXT NOT NULL DEFAULT '',
    parameters_json TEXT NOT NULL,
    output_count INTEGER NOT NULL CHECK (output_count >= 0),
    provenance_ref TEXT NOT NULL,
    run_status TEXT NOT NULL CHECK (run_status IN ('completed', 'failed', 'rejected')),
    started_at TEXT NOT NULL DEFAULT '',
    ended_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS model_run_elements (
    model_run_id TEXT NOT NULL,
    element_card_id TEXT NOT NULL,
    PRIMARY KEY (model_run_id, element_card_id),
    FOREIGN KEY (model_run_id) REFERENCES model_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (element_card_id) REFERENCES cultural_element_cards(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS expert_reviews (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    model_run_id TEXT NOT NULL,
    reviewer_rights_holder_id TEXT NOT NULL,
    reviewer_role TEXT NOT NULL CHECK (
        reviewer_role IN (
            'bearer', 'cultural_expert', 'design_expert',
            'production_expert', 'legal_expert', 'other'
        )
    ),
    cultural_score REAL CHECK (cultural_score IS NULL OR cultural_score BETWEEN 1 AND 5),
    aesthetic_score REAL CHECK (aesthetic_score IS NULL OR aesthetic_score BETWEEN 1 AND 5),
    feasibility_score REAL CHECK (feasibility_score IS NULL OR feasibility_score BETWEEN 1 AND 5),
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'revise', 'rejected')),
    comments TEXT NOT NULL DEFAULT '',
    revision_target_gate INTEGER CHECK (
        revision_target_gate IS NULL OR revision_target_gate BETWEEN 0 AND 4
    ),
    evidence_ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (model_run_id) REFERENCES model_runs(id) ON DELETE RESTRICT,
    FOREIGN KEY (reviewer_rights_holder_id) REFERENCES rights_holders(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS market_tests (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    model_run_id TEXT NOT NULL,
    sample_size INTEGER NOT NULL CHECK (sample_size > 0),
    test_channel TEXT NOT NULL,
    perceived_authenticity REAL NOT NULL CHECK (perceived_authenticity BETWEEN 1 AND 5),
    perceived_cultural_value REAL NOT NULL CHECK (perceived_cultural_value BETWEEN 1 AND 5),
    story_comprehension REAL NOT NULL CHECK (story_comprehension BETWEEN 1 AND 5),
    purchase_intention REAL NOT NULL CHECK (purchase_intention BETWEEN 1 AND 5),
    recommendation_intention REAL NOT NULL CHECK (recommendation_intention BETWEEN 1 AND 5),
    recommendation TEXT NOT NULL CHECK (recommendation IN ('scale', 'revise', 'discontinue')),
    report_ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (model_run_id) REFERENCES model_runs(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS revenue_distributions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    authorization_id TEXT NOT NULL,
    recipient_rights_holder_id TEXT NOT NULL,
    revenue_category TEXT NOT NULL CHECK (
        revenue_category IN ('product', 'content_education', 'licensing', 'digital_ai_service', 'other')
    ),
    gross_amount REAL NOT NULL CHECK (gross_amount >= 0),
    currency TEXT NOT NULL,
    share_percent REAL NOT NULL CHECK (share_percent BETWEEN 0 AND 100),
    distributed_amount REAL NOT NULL CHECK (distributed_amount >= 0),
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    distributed_at TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (authorization_id) REFERENCES authorization_records(id) ON DELETE RESTRICT,
    FOREIGN KEY (recipient_rights_holder_id) REFERENCES rights_holders(id) ON DELETE RESTRICT
);


CREATE TABLE IF NOT EXISTS pilot_studies (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL UNIQUE,
    study_title TEXT NOT NULL,
    protocol_version TEXT NOT NULL,
    study_design TEXT NOT NULL CHECK (
        study_design IN ('single_group', 'crossover', 'parallel', 'observational')
    ),
    ethics_status TEXT NOT NULL CHECK (
        ethics_status IN ('approved', 'exempt', 'pending', 'not_required')
    ),
    ethics_ref TEXT NOT NULL DEFAULT '',
    planned_sample_size INTEGER NOT NULL CHECK (planned_sample_size > 0),
    primary_outcomes_json TEXT NOT NULL,
    secondary_outcomes_json TEXT NOT NULL,
    inclusion_criteria TEXT NOT NULL,
    exclusion_criteria TEXT NOT NULL,
    preregistration_ref TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pilot_participants (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    participant_code TEXT NOT NULL,
    participant_role TEXT NOT NULL CHECK (
        participant_role IN (
            'researcher', 'bearer', 'cultural_expert', 'designer',
            'developer', 'student', 'other'
        )
    ),
    experience_level TEXT NOT NULL CHECK (
        experience_level IN ('novice', 'intermediate', 'advanced')
    ),
    consent_status TEXT NOT NULL CHECK (
        consent_status IN ('consented', 'exempt', 'withdrawn')
    ),
    consent_ref TEXT NOT NULL DEFAULT '',
    demographics_json TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(project_id, participant_code),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pilot_tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_code TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    expected_outcome TEXT NOT NULL,
    gate_scope INTEGER CHECK (gate_scope IS NULL OR gate_scope BETWEEN 0 AND 7),
    sequence_order INTEGER NOT NULL CHECK (sequence_order > 0),
    required INTEGER NOT NULL DEFAULT 1 CHECK (required IN (0, 1)),
    created_at TEXT NOT NULL,
    UNIQUE(project_id, task_code),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pilot_sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    participant_id TEXT NOT NULL,
    condition_name TEXT NOT NULL CHECK (condition_name IN ('heritagegate', 'baseline')),
    session_label TEXT NOT NULL,
    environment_json TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT '',
    ended_at TEXT NOT NULL DEFAULT '',
    session_status TEXT NOT NULL CHECK (
        session_status IN ('planned', 'in_progress', 'completed', 'abandoned')
    ),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_id) REFERENCES pilot_participants(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS installation_records (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL UNIQUE,
    install_method TEXT NOT NULL CHECK (
        install_method IN ('editable', 'wheel', 'source', 'docker', 'other')
    ),
    software_version TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    duration_seconds REAL NOT NULL CHECK (duration_seconds >= 0),
    success INTEGER NOT NULL CHECK (success IN (0, 1)),
    error_count INTEGER NOT NULL CHECK (error_count >= 0),
    environment_json TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES pilot_sessions(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS pilot_task_attempts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    duration_seconds REAL NOT NULL CHECK (duration_seconds >= 0),
    success INTEGER NOT NULL CHECK (success IN (0, 1)),
    completion_status TEXT NOT NULL CHECK (
        completion_status IN ('completed', 'failed', 'abandoned')
    ),
    assistance_count INTEGER NOT NULL CHECK (assistance_count >= 0),
    error_count INTEGER NOT NULL CHECK (error_count >= 0),
    evidence_ref TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(session_id, task_id),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES pilot_sessions(id) ON DELETE RESTRICT,
    FOREIGN KEY (task_id) REFERENCES pilot_tasks(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS sus_responses (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL UNIQUE,
    responses_json TEXT NOT NULL,
    sus_score REAL NOT NULL CHECK (sus_score BETWEEN 0 AND 100),
    submitted_at TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES pilot_sessions(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS workflow_benchmarks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    benchmark_label TEXT NOT NULL,
    workflow_unit TEXT NOT NULL,
    heritagegate_seconds REAL NOT NULL CHECK (heritagegate_seconds >= 0),
    baseline_seconds REAL NOT NULL CHECK (baseline_seconds > 0),
    heritagegate_errors INTEGER NOT NULL CHECK (heritagegate_errors >= 0),
    baseline_errors INTEGER NOT NULL CHECK (baseline_errors >= 0),
    records_processed INTEGER NOT NULL CHECK (records_processed > 0),
    evidence_ref TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS consent_documents (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    document_title TEXT NOT NULL,
    document_version TEXT NOT NULL,
    language TEXT NOT NULL,
    ethics_ref TEXT NOT NULL DEFAULT '',
    body_ref TEXT NOT NULL,
    body_sha256 TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    withdrawal_contact TEXT NOT NULL,
    retention_policy TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, document_version, language),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS participant_import_batches (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    imported_count INTEGER NOT NULL CHECK (imported_count >= 0),
    rejected_count INTEGER NOT NULL CHECK (rejected_count >= 0),
    duplicate_count INTEGER NOT NULL CHECK (duplicate_count >= 0),
    mapping_json TEXT NOT NULL,
    rejected_rows_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS participant_enrollments (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    participant_id TEXT NOT NULL UNIQUE,
    consent_document_id TEXT,
    import_batch_id TEXT,
    eligibility_status TEXT NOT NULL CHECK (
        eligibility_status IN ('eligible', 'ineligible', 'pending')
    ),
    consented_at TEXT NOT NULL DEFAULT '',
    withdrawn_at TEXT NOT NULL DEFAULT '',
    identity_token_hash TEXT NOT NULL,
    source_row_hash TEXT NOT NULL,
    data_use_scope_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, identity_token_hash),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_id) REFERENCES pilot_participants(id) ON DELETE RESTRICT,
    FOREIGN KEY (consent_document_id) REFERENCES consent_documents(id) ON DELETE RESTRICT,
    FOREIGN KEY (import_batch_id) REFERENCES participant_import_batches(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS data_quality_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    run_label TEXT NOT NULL,
    checks_json TEXT NOT NULL,
    issues_json TEXT NOT NULL,
    issue_count INTEGER NOT NULL CHECK (issue_count >= 0),
    blocking_issue_count INTEGER NOT NULL CHECK (blocking_issue_count >= 0),
    passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
    report_ref TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    analysis_version TEXT NOT NULL,
    random_seed INTEGER NOT NULL,
    input_sha256 TEXT NOT NULL,
    results_json TEXT NOT NULL,
    report_ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS release_profiles (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL UNIQUE,
    software_title TEXT NOT NULL,
    manuscript_title TEXT NOT NULL,
    software_version TEXT NOT NULL,
    release_status TEXT NOT NULL CHECK (
        release_status IN ('draft', 'candidate', 'released')
    ),
    evidence_status TEXT NOT NULL CHECK (
        evidence_status IN ('synthetic', 'real_pilot', 'validated_real_pilot')
    ),
    repository_url TEXT NOT NULL DEFAULT '',
    archive_url TEXT NOT NULL DEFAULT '',
    software_doi TEXT NOT NULL DEFAULT '',
    executable_url TEXT NOT NULL DEFAULT '',
    documentation_url TEXT NOT NULL DEFAULT '',
    support_email TEXT NOT NULL DEFAULT '',
    license_spdx TEXT NOT NULL,
    authors_json TEXT NOT NULL,
    keywords_json TEXT NOT NULL,
    release_date TEXT NOT NULL DEFAULT '',
    funding_statement TEXT NOT NULL DEFAULT '',
    conflict_statement TEXT NOT NULL DEFAULT '',
    ai_use_statement TEXT NOT NULL DEFAULT '',
    data_availability_statement TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_consent_documents_project
ON consent_documents(project_id);
CREATE INDEX IF NOT EXISTS idx_participant_import_batches_project
ON participant_import_batches(project_id);
CREATE INDEX IF NOT EXISTS idx_participant_enrollments_project
ON participant_enrollments(project_id);
CREATE INDEX IF NOT EXISTS idx_data_quality_runs_project
ON data_quality_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_project
ON analysis_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_release_profiles_project
ON release_profiles(project_id);

CREATE INDEX IF NOT EXISTS idx_pilot_participants_project
ON pilot_participants(project_id);
CREATE INDEX IF NOT EXISTS idx_pilot_sessions_project_condition
ON pilot_sessions(project_id, condition_name);
CREATE INDEX IF NOT EXISTS idx_installation_records_project
ON installation_records(project_id);
CREATE INDEX IF NOT EXISTS idx_pilot_attempts_project
ON pilot_task_attempts(project_id);
CREATE INDEX IF NOT EXISTS idx_sus_responses_project
ON sus_responses(project_id);
CREATE INDEX IF NOT EXISTS idx_workflow_benchmarks_project
ON workflow_benchmarks(project_id);

CREATE INDEX IF NOT EXISTS idx_gate_records_project_gate
ON gate_records(project_id, gate);
CREATE INDEX IF NOT EXISTS idx_audit_events_project
ON audit_events(project_id);
CREATE INDEX IF NOT EXISTS idx_rights_holders_project
ON rights_holders(project_id);
CREATE INDEX IF NOT EXISTS idx_authorizations_project_status
ON authorization_records(project_id, status);
CREATE INDEX IF NOT EXISTS idx_element_cards_project_status
ON cultural_element_cards(project_id, status);
CREATE INDEX IF NOT EXISTS idx_model_runs_project_status
ON model_runs(project_id, run_status);
CREATE INDEX IF NOT EXISTS idx_reviews_project_role
ON expert_reviews(project_id, reviewer_role, decision);
CREATE INDEX IF NOT EXISTS idx_market_tests_project
ON market_tests(project_id);
CREATE INDEX IF NOT EXISTS idx_revenue_project
ON revenue_distributions(project_id);
"""


def normalize_db_path(path: str | Path) -> Path:
    db_path = Path(path).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


@contextmanager
def connect(path: str | Path) -> Iterator[sqlite3.Connection]:
    db_path = normalize_db_path(path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_project_columns(conn: sqlite3.Connection) -> None:
    """Add v0.2 project columns when opening a v0.1 database."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(projects)")}
    if "governance_owner" not in columns:
        conn.execute(
            "ALTER TABLE projects ADD COLUMN governance_owner TEXT NOT NULL DEFAULT ''"
        )
    if "audit_takedown_ready" not in columns:
        conn.execute(
            "ALTER TABLE projects ADD COLUMN audit_takedown_ready INTEGER NOT NULL DEFAULT 0"
        )


def init_db(path: str | Path) -> Path:
    db_path = normalize_db_path(path)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _ensure_project_columns(conn)
        conn.execute(
            """
            INSERT INTO schema_metadata(key, value) VALUES ('schema_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (SCHEMA_VERSION,),
        )
    return db_path


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def loads(value: str) -> Any:
    return json.loads(value)
