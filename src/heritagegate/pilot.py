"""Pilot-study data capture and SoftwareX evidence metrics for HeritageGate v0.4."""

from __future__ import annotations

import math
import sqlite3
import statistics
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from . import db


class PilotDataError(ValueError):
    """Raised when pilot-study evidence is invalid or inconsistent."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise PilotDataError(f"Field must be a non-empty string: {field}")
    return value.strip()


def _optional_text(payload: Mapping[str, Any], field: str, default: str = "") -> str:
    value = payload.get(field, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise PilotDataError(f"Field must be a string: {field}")
    return value.strip()


def _choice(payload: Mapping[str, Any], field: str, choices: set[str]) -> str:
    value = _required_text(payload, field)
    if value not in choices:
        raise PilotDataError(f"Field {field} must be one of: {', '.join(sorted(choices))}")
    return value


def _boolean(payload: Mapping[str, Any], field: str, default: bool | None = None) -> bool:
    value = payload.get(field, default)
    if not isinstance(value, bool):
        raise PilotDataError(f"Field must be boolean: {field}")
    return value


def _positive_int(payload: Mapping[str, Any], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PilotDataError(f"Field must be a positive integer: {field}")
    return value


def _nonnegative_int(payload: Mapping[str, Any], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PilotDataError(f"Field must be a non-negative integer: {field}")
    return value


def _nonnegative_number(payload: Mapping[str, Any], field: str) -> float:
    value = payload.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise PilotDataError(f"Field must be a non-negative number: {field}")
    return float(value)


def _object(payload: Mapping[str, Any], field: str, *, allow_empty: bool = True) -> dict[str, Any]:
    value = payload.get(field)
    if not isinstance(value, dict) or (not value and not allow_empty):
        requirement = "an object" if allow_empty else "a non-empty object"
        raise PilotDataError(f"Field must be {requirement}: {field}")
    return dict(value)


def _list_of_text(payload: Mapping[str, Any], field: str, *, allow_empty: bool = False) -> list[str]:
    value = payload.get(field)
    if not isinstance(value, list) or (not value and not allow_empty):
        requirement = "a list" if allow_empty else "a non-empty list"
        raise PilotDataError(f"Field must be {requirement}: {field}")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise PilotDataError(f"All values in {field} must be non-empty strings")
        result.append(item.strip())
    return result


def _parse_time(value: str, field: str) -> datetime:
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PilotDataError(f"Field must be an ISO-8601 datetime: {field}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _time_pair(payload: Mapping[str, Any], start_field: str, end_field: str) -> tuple[str, str, float]:
    start = _required_text(payload, start_field)
    end = _required_text(payload, end_field)
    start_dt = _parse_time(start, start_field)
    end_dt = _parse_time(end, end_field)
    seconds = (end_dt - start_dt).total_seconds()
    if seconds < 0:
        raise PilotDataError(f"{end_field} must not be earlier than {start_field}")
    return start, end, seconds


def calculate_sus_score(responses: list[int]) -> float:
    """Calculate the standard 0-100 System Usability Scale score."""
    if len(responses) != 10:
        raise PilotDataError("SUS responses must contain exactly 10 items")
    adjusted = 0
    for index, value in enumerate(responses):
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
            raise PilotDataError("Each SUS response must be an integer from 1 to 5")
        adjusted += value - 1 if index % 2 == 0 else 5 - value
    return adjusted * 2.5


def _audit(conn: sqlite3.Connection, project_id: str, event_type: str, details: Mapping[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO audit_events(project_id, event_type, gate, details_json, created_at)
        VALUES (?, ?, NULL, ?, ?)
        """,
        (project_id, event_type, db.dumps(dict(details)), utc_now()),
    )


PILOT_ENTITY_ALIASES = {
    "study": "pilot_studies",
    "participant": "pilot_participants",
    "task": "pilot_tasks",
    "session": "pilot_sessions",
    "installation": "installation_records",
    "task-attempt": "pilot_task_attempts",
    "sus-response": "sus_responses",
    "workflow-benchmark": "workflow_benchmarks",
}


class PilotStudyManager:
    """Capture pilot protocol, usability observations, and comparison evidence."""

    def __init__(self, database: str | Path):
        self.database = db.init_db(database)

    def _require_project(self, conn: sqlite3.Connection, project_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(f"Project not found: {project_id}")
        return row

    def _require_reference(
        self, conn: sqlite3.Connection, table: str, entity_id: str, project_id: str, label: str
    ) -> sqlite3.Row:
        row = conn.execute(
            f"SELECT * FROM {table} WHERE id = ? AND project_id = ?", (entity_id, project_id)
        ).fetchone()
        if row is None:
            raise PilotDataError(f"{label} not found in project {project_id}: {entity_id}")
        return row

    def create_entity(
        self, entity_type: str, project_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        dispatch: dict[str, Callable[[str, Mapping[str, Any]], dict[str, Any]]] = {
            "study": self.add_study,
            "participant": self.add_participant,
            "task": self.add_task,
            "session": self.add_session,
            "installation": self.add_installation,
            "task-attempt": self.add_task_attempt,
            "sus-response": self.add_sus_response,
            "workflow-benchmark": self.add_workflow_benchmark,
        }
        if entity_type not in dispatch:
            raise PilotDataError(f"Unknown pilot entity type: {entity_type}")
        if not isinstance(payload, Mapping):
            raise PilotDataError("Pilot entity payload must be a JSON object")
        return dispatch[entity_type](project_id, payload)

    def add_study(self, project_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        entity_id = _optional_text(payload, "id") or _new_id("study")
        planned_sample_size = _positive_int(payload, "planned_sample_size")
        primary = _list_of_text(payload, "primary_outcomes")
        secondary = _list_of_text(payload, "secondary_outcomes", allow_empty=True)
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            conn.execute(
                """
                INSERT INTO pilot_studies(
                    id, project_id, study_title, protocol_version, study_design,
                    ethics_status, ethics_ref, planned_sample_size,
                    primary_outcomes_json, secondary_outcomes_json,
                    inclusion_criteria, exclusion_criteria, preregistration_ref,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    project_id,
                    _required_text(payload, "study_title"),
                    _required_text(payload, "protocol_version"),
                    _choice(payload, "study_design", {"single_group", "crossover", "parallel", "observational"}),
                    _choice(payload, "ethics_status", {"approved", "exempt", "pending", "not_required"}),
                    _optional_text(payload, "ethics_ref"),
                    planned_sample_size,
                    db.dumps(primary),
                    db.dumps(secondary),
                    _required_text(payload, "inclusion_criteria"),
                    _required_text(payload, "exclusion_criteria"),
                    _optional_text(payload, "preregistration_ref"),
                    now,
                    now,
                ),
            )
            _audit(conn, project_id, "pilot_study_created", {"id": entity_id})
        return self.get_entity("study", entity_id)

    def add_participant(self, project_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        entity_id = _optional_text(payload, "id") or _new_id("participant")
        consent_status = _choice(payload, "consent_status", {"consented", "exempt", "withdrawn"})
        consent_ref = _optional_text(payload, "consent_ref")
        if consent_status == "consented" and not consent_ref:
            raise PilotDataError("Consented participants require consent_ref")
        demographics = _object(payload, "demographics", allow_empty=True)
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            conn.execute(
                """
                INSERT INTO pilot_participants(
                    id, project_id, participant_code, participant_role,
                    experience_level, consent_status, consent_ref,
                    demographics_json, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    project_id,
                    _required_text(payload, "participant_code"),
                    _choice(payload, "participant_role", {"researcher", "bearer", "cultural_expert", "designer", "developer", "student", "other"}),
                    _choice(payload, "experience_level", {"novice", "intermediate", "advanced"}),
                    consent_status,
                    consent_ref,
                    db.dumps(demographics),
                    _optional_text(payload, "notes"),
                    now,
                ),
            )
            _audit(conn, project_id, "pilot_participant_created", {"id": entity_id})
        return self.get_entity("participant", entity_id)

    def add_task(self, project_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        entity_id = _optional_text(payload, "id") or _new_id("task")
        gate_scope = payload.get("gate_scope")
        if gate_scope is not None:
            if not isinstance(gate_scope, int) or isinstance(gate_scope, bool) or not 0 <= gate_scope <= 7:
                raise PilotDataError("gate_scope must be null or an integer from 0 to 7")
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            conn.execute(
                """
                INSERT INTO pilot_tasks(
                    id, project_id, task_code, title, description, expected_outcome,
                    gate_scope, sequence_order, required, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    project_id,
                    _required_text(payload, "task_code"),
                    _required_text(payload, "title"),
                    _required_text(payload, "description"),
                    _required_text(payload, "expected_outcome"),
                    gate_scope,
                    _positive_int(payload, "sequence_order"),
                    int(_boolean(payload, "required", True)),
                    now,
                ),
            )
            _audit(conn, project_id, "pilot_task_created", {"id": entity_id})
        return self.get_entity("task", entity_id)

    def add_session(self, project_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        entity_id = _optional_text(payload, "id") or _new_id("session")
        participant_id = _required_text(payload, "participant_id")
        status = _choice(payload, "session_status", {"planned", "in_progress", "completed", "abandoned"})
        started_at = _optional_text(payload, "started_at")
        ended_at = _optional_text(payload, "ended_at")
        if status in {"in_progress", "completed", "abandoned"} and not started_at:
            raise PilotDataError(f"{status} sessions require started_at")
        if status in {"completed", "abandoned"} and not ended_at:
            raise PilotDataError(f"{status} sessions require ended_at")
        if started_at and ended_at:
            _time_pair({"started_at": started_at, "ended_at": ended_at}, "started_at", "ended_at")
        environment = _object(payload, "environment", allow_empty=True)
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            participant = self._require_reference(conn, "pilot_participants", participant_id, project_id, "Pilot participant")
            if participant["consent_status"] == "withdrawn":
                raise PilotDataError("Withdrawn participants cannot be assigned a new pilot session")
            conn.execute(
                """
                INSERT INTO pilot_sessions(
                    id, project_id, participant_id, condition_name, session_label,
                    environment_json, started_at, ended_at, session_status, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    project_id,
                    participant_id,
                    _choice(payload, "condition", {"heritagegate", "baseline"}),
                    _required_text(payload, "session_label"),
                    db.dumps(environment),
                    started_at,
                    ended_at,
                    status,
                    _optional_text(payload, "notes"),
                    now,
                ),
            )
            _audit(conn, project_id, "pilot_session_created", {"id": entity_id, "status": status})
        return self.get_entity("session", entity_id)

    def add_installation(self, project_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        entity_id = _optional_text(payload, "id") or _new_id("install")
        session_id = _required_text(payload, "session_id")
        start, end, duration = _time_pair(payload, "started_at", "ended_at")
        success = _boolean(payload, "success")
        error_count = _nonnegative_int(payload, "error_count")
        if success and error_count < 0:
            raise PilotDataError("Invalid error count")
        environment = _object(payload, "environment", allow_empty=True)
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            session = self._require_reference(conn, "pilot_sessions", session_id, project_id, "Pilot session")
            if session["condition_name"] != "heritagegate":
                raise PilotDataError("Installation records must be linked to a HeritageGate session")
            conn.execute(
                """
                INSERT INTO installation_records(
                    id, project_id, session_id, install_method, software_version,
                    started_at, ended_at, duration_seconds, success, error_count,
                    environment_json, evidence_ref, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    project_id,
                    session_id,
                    _choice(payload, "install_method", {"editable", "wheel", "source", "docker", "other"}),
                    _required_text(payload, "software_version"),
                    start,
                    end,
                    duration,
                    int(success),
                    error_count,
                    db.dumps(environment),
                    _required_text(payload, "evidence_ref"),
                    now,
                ),
            )
            _audit(conn, project_id, "installation_record_created", {"id": entity_id, "success": success})
        return self.get_entity("installation", entity_id)

    def add_task_attempt(self, project_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        entity_id = _optional_text(payload, "id") or _new_id("attempt")
        session_id = _required_text(payload, "session_id")
        task_id = _required_text(payload, "task_id")
        start, end, duration = _time_pair(payload, "started_at", "ended_at")
        completion_status = _choice(payload, "completion_status", {"completed", "failed", "abandoned"})
        success = _boolean(payload, "success")
        if success and completion_status != "completed":
            raise PilotDataError("A successful task attempt must have completion_status='completed'")
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            self._require_reference(conn, "pilot_sessions", session_id, project_id, "Pilot session")
            self._require_reference(conn, "pilot_tasks", task_id, project_id, "Pilot task")
            conn.execute(
                """
                INSERT INTO pilot_task_attempts(
                    id, project_id, session_id, task_id, started_at, ended_at,
                    duration_seconds, success, completion_status, assistance_count,
                    error_count, evidence_ref, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    project_id,
                    session_id,
                    task_id,
                    start,
                    end,
                    duration,
                    int(success),
                    completion_status,
                    _nonnegative_int(payload, "assistance_count"),
                    _nonnegative_int(payload, "error_count"),
                    _required_text(payload, "evidence_ref"),
                    _optional_text(payload, "notes"),
                    now,
                ),
            )
            _audit(conn, project_id, "pilot_task_attempt_created", {"id": entity_id, "success": success})
        return self.get_entity("task-attempt", entity_id)

    def add_sus_response(self, project_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        entity_id = _optional_text(payload, "id") or _new_id("sus")
        session_id = _required_text(payload, "session_id")
        raw = payload.get("responses")
        if not isinstance(raw, list):
            raise PilotDataError("Field responses must be a list of 10 integers")
        responses = list(raw)
        score = calculate_sus_score(responses)
        submitted_at = _required_text(payload, "submitted_at")
        _parse_time(submitted_at, "submitted_at")
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            session = self._require_reference(conn, "pilot_sessions", session_id, project_id, "Pilot session")
            if session["condition_name"] != "heritagegate":
                raise PilotDataError("SUS responses must be linked to a HeritageGate session")
            conn.execute(
                """
                INSERT INTO sus_responses(
                    id, project_id, session_id, responses_json, sus_score,
                    submitted_at, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    project_id,
                    session_id,
                    db.dumps(responses),
                    score,
                    submitted_at,
                    _optional_text(payload, "notes"),
                    now,
                ),
            )
            _audit(conn, project_id, "sus_response_created", {"id": entity_id, "sus_score": score})
        return self.get_entity("sus-response", entity_id)

    def add_workflow_benchmark(self, project_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        entity_id = _optional_text(payload, "id") or _new_id("benchmark")
        hg_seconds = _nonnegative_number(payload, "heritagegate_seconds")
        baseline_seconds = _nonnegative_number(payload, "baseline_seconds")
        if baseline_seconds <= 0:
            raise PilotDataError("baseline_seconds must be greater than zero")
        records_processed = _positive_int(payload, "records_processed")
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            conn.execute(
                """
                INSERT INTO workflow_benchmarks(
                    id, project_id, benchmark_label, workflow_unit,
                    heritagegate_seconds, baseline_seconds,
                    heritagegate_errors, baseline_errors, records_processed,
                    evidence_ref, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    project_id,
                    _required_text(payload, "benchmark_label"),
                    _required_text(payload, "workflow_unit"),
                    hg_seconds,
                    baseline_seconds,
                    _nonnegative_int(payload, "heritagegate_errors"),
                    _nonnegative_int(payload, "baseline_errors"),
                    records_processed,
                    _required_text(payload, "evidence_ref"),
                    _optional_text(payload, "notes"),
                    now,
                ),
            )
            _audit(conn, project_id, "workflow_benchmark_created", {"id": entity_id})
        return self.get_entity("workflow-benchmark", entity_id)

    def list_entities(self, project_id: str, entity_type: str) -> list[dict[str, Any]]:
        if entity_type not in PILOT_ENTITY_ALIASES:
            raise PilotDataError(f"Unknown pilot entity type: {entity_type}")
        table = PILOT_ENTITY_ALIASES[entity_type]
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE project_id = ? ORDER BY created_at, id", (project_id,)
            ).fetchall()
        return [self._decode(entity_type, dict(row)) for row in rows]

    def get_entity(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        if entity_type not in PILOT_ENTITY_ALIASES:
            raise PilotDataError(f"Unknown pilot entity type: {entity_type}")
        table = PILOT_ENTITY_ALIASES[entity_type]
        with db.connect(self.database) as conn:
            row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (entity_id,)).fetchone()
        if row is None:
            raise KeyError(f"Pilot entity not found: {entity_id}")
        return self._decode(entity_type, dict(row))

    @staticmethod
    def _decode(entity_type: str, item: dict[str, Any]) -> dict[str, Any]:
        json_fields = {
            "study": ("primary_outcomes_json", "secondary_outcomes_json"),
            "participant": ("demographics_json",),
            "session": ("environment_json",),
            "installation": ("environment_json",),
            "sus-response": ("responses_json",),
        }.get(entity_type, ())
        for field in json_fields:
            value = item.pop(field)
            clean = field.removesuffix("_json")
            item[clean] = db.loads(value)
        for field in ("required", "success"):
            if field in item:
                item[field] = bool(item[field])
        if entity_type == "session" and "condition_name" in item:
            item["condition"] = item.pop("condition_name")
        if entity_type == "study":
            item["primary_outcomes"] = item.pop("primary_outcomes")
            item["secondary_outcomes"] = item.pop("secondary_outcomes")
        if entity_type == "participant":
            item["demographics"] = item.pop("demographics")
        if entity_type in {"session", "installation"}:
            item["environment"] = item.pop("environment")
        if entity_type == "sus-response":
            item["responses"] = item.pop("responses")
        return item

    def export_project_entities(self, project_id: str) -> dict[str, list[dict[str, Any]]]:
        return {
            table: self.list_entities(project_id, entity_type)
            for entity_type, table in PILOT_ENTITY_ALIASES.items()
        }

    @staticmethod
    def _mean(values: list[float]) -> float | None:
        return round(statistics.mean(values), 3) if values else None

    @staticmethod
    def _median(values: list[float]) -> float | None:
        return round(statistics.median(values), 3) if values else None

    def summary(self, project_id: str) -> dict[str, Any]:
        entities = self.export_project_entities(project_id)
        studies = entities["pilot_studies"]
        participants = entities["pilot_participants"]
        sessions = entities["pilot_sessions"]
        installs = entities["installation_records"]
        attempts = entities["pilot_task_attempts"]
        sus = entities["sus_responses"]
        benchmarks = entities["workflow_benchmarks"]

        session_condition = {row["id"]: row["condition"] for row in sessions}
        condition_summary: dict[str, dict[str, Any]] = {}
        for condition in ("heritagegate", "baseline"):
            condition_sessions = [row for row in sessions if row["condition"] == condition]
            ids = {row["id"] for row in condition_sessions}
            condition_attempts = [row for row in attempts if row["session_id"] in ids]
            durations = [float(row["duration_seconds"]) for row in condition_attempts]
            successes = sum(1 for row in condition_attempts if row["success"])
            condition_summary[condition] = {
                "sessions": len(condition_sessions),
                "completed_sessions": sum(1 for row in condition_sessions if row["session_status"] == "completed"),
                "task_attempts": len(condition_attempts),
                "successful_attempts": successes,
                "task_completion_rate_pct": round(100 * successes / len(condition_attempts), 2) if condition_attempts else None,
                "mean_task_seconds": self._mean(durations),
                "median_task_seconds": self._median(durations),
                "mean_errors_per_attempt": self._mean([float(row["error_count"]) for row in condition_attempts]),
                "mean_assistance_per_attempt": self._mean([float(row["assistance_count"]) for row in condition_attempts]),
            }

        install_durations = [float(row["duration_seconds"]) for row in installs]
        sus_scores = [float(row["sus_score"]) for row in sus]
        benchmark_time_reductions = [
            100 * (float(row["baseline_seconds"]) - float(row["heritagegate_seconds"])) / float(row["baseline_seconds"])
            for row in benchmarks
        ]
        benchmark_error_reductions = [
            100 * (float(row["baseline_errors"]) - float(row["heritagegate_errors"])) / float(row["baseline_errors"])
            for row in benchmarks
            if float(row["baseline_errors"]) > 0
        ]

        consented = [row for row in participants if row["consent_status"] in {"consented", "exempt"}]
        readiness_checks = {
            "protocol_recorded": bool(studies),
            "ethics_resolved": bool(studies) and studies[0]["ethics_status"] in {"approved", "exempt", "not_required"},
            "at_least_5_participants": len(consented) >= 5,
            "at_least_5_completed_sessions": sum(1 for row in sessions if row["session_status"] == "completed") >= 5,
            "installation_evidence": bool(installs),
            "at_least_10_task_attempts": len(attempts) >= 10,
            "at_least_5_sus_responses": len(sus) >= 5,
            "workflow_comparison_evidence": bool(benchmarks),
        }

        return {
            "schema_version": db.SCHEMA_VERSION,
            "project_id": project_id,
            "record_counts": {table: len(rows) for table, rows in entities.items()},
            "participant_summary": {
                "total": len(participants),
                "consented_or_exempt": len(consented),
                "withdrawn": sum(1 for row in participants if row["consent_status"] == "withdrawn"),
            },
            "installation_summary": {
                "records": len(installs),
                "successes": sum(1 for row in installs if row["success"]),
                "success_rate_pct": round(100 * sum(1 for row in installs if row["success"]) / len(installs), 2) if installs else None,
                "mean_seconds": self._mean(install_durations),
                "median_seconds": self._median(install_durations),
                "total_errors": sum(int(row["error_count"]) for row in installs),
            },
            "condition_summary": condition_summary,
            "sus_summary": {
                "responses": len(sus_scores),
                "mean_score": self._mean(sus_scores),
                "median_score": self._median(sus_scores),
                "minimum": round(min(sus_scores), 3) if sus_scores else None,
                "maximum": round(max(sus_scores), 3) if sus_scores else None,
                "population_sd": round(statistics.pstdev(sus_scores), 3) if len(sus_scores) > 1 else (0.0 if sus_scores else None),
            },
            "workflow_benchmark_summary": {
                "records": len(benchmarks),
                "mean_heritagegate_seconds": self._mean([float(row["heritagegate_seconds"]) for row in benchmarks]),
                "mean_baseline_seconds": self._mean([float(row["baseline_seconds"]) for row in benchmarks]),
                "mean_time_reduction_pct": self._mean(benchmark_time_reductions),
                "mean_error_reduction_pct": self._mean(benchmark_error_reductions),
            },
            "softwarex_evidence_readiness": {
                "checks": readiness_checks,
                "passed": sum(readiness_checks.values()),
                "total": len(readiness_checks),
                "ready": all(readiness_checks.values()),
            },
        }
