"""Core workflow engine for the eight HeritageGate stages."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from . import db
from .structured import StructuredDataManager
from .pilot import PilotStudyManager
from .realpilot import RealPilotManager
from .validators import GateValidationError, validate_gate


class WorkflowStateError(RuntimeError):
    """Raised when a requested transition violates workflow state rules."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HeritageGateEngine:
    """Persistent workflow engine backed by SQLite.

    ``current_gate`` stores the last successfully completed gate. A new project
    starts at -1. Passing Gate 0 moves it to 0; passing Gate 7 completes it.
    Version 0.5 additionally exposes normalized governance entities through ``structured``, pilot-study evidence through ``pilot``, and privacy-aware real-pilot and release operations through ``real_pilot``.
    """

    def __init__(self, database: str | Path):
        self.database = db.init_db(database)
        self.structured = StructuredDataManager(self.database)
        self.pilot = PilotStudyManager(self.database)
        self.real_pilot = RealPilotManager(self.database)

    def create_project(
        self,
        name: str,
        heritage_name: str,
        description: str = "",
        project_id: str | None = None,
    ) -> dict[str, Any]:
        if not name.strip():
            raise ValueError("Project name must not be empty")
        if not heritage_name.strip():
            raise ValueError("Heritage name must not be empty")
        project_id = project_id or str(uuid.uuid4())
        now = utc_now()
        with db.connect(self.database) as conn:
            conn.execute(
                """
                INSERT INTO projects(
                    id, name, heritage_name, description, current_gate,
                    status, governance_owner, audit_takedown_ready,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, -1, 'active', '', 0, ?, ?)
                """,
                (project_id, name.strip(), heritage_name.strip(), description, now, now),
            )
            self._audit(
                conn,
                project_id,
                event_type="project_created",
                gate=None,
                details={"name": name, "heritage_name": heritage_name},
                created_at=now,
            )
        return self.get_project(project_id)

    def update_project(
        self,
        project_id: str,
        *,
        name: str,
        heritage_name: str,
        description: str = "",
    ) -> dict[str, Any]:
        """Update project descriptive metadata without changing workflow state."""
        if not name.strip():
            raise ValueError("Project name must not be empty")
        if not heritage_name.strip():
            raise ValueError("Heritage name must not be empty")
        now = utc_now()
        with db.connect(self.database) as conn:
            row = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
            if row is None:
                raise KeyError(f"Project not found: {project_id}")
            conn.execute(
                """
                UPDATE projects
                SET name = ?, heritage_name = ?, description = ?, updated_at = ?
                WHERE id = ?
                """,
                (name.strip(), heritage_name.strip(), description, now, project_id),
            )
            self._audit(
                conn,
                project_id,
                event_type="project_updated",
                gate=None,
                details={"name": name.strip(), "heritage_name": heritage_name.strip()},
                created_at=now,
            )
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> dict[str, Any]:
        with db.connect(self.database) as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Project not found: {project_id}")
        item = dict(row)
        item["audit_takedown_ready"] = bool(item.get("audit_takedown_ready", 0))
        return item

    def list_projects(self) -> list[dict[str, Any]]:
        with db.connect(self.database) as conn:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY created_at"
            ).fetchall()
        projects: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["audit_takedown_ready"] = bool(item.get("audit_takedown_ready", 0))
            projects.append(item)
        return projects

    def pass_gate(
        self, project_id: str, gate: int, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        validate_gate(gate, payload)
        now = utc_now()
        with db.connect(self.database) as conn:
            project = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
            if project is None:
                raise KeyError(f"Project not found: {project_id}")
            current_gate = int(project["current_gate"])
            expected_gate = current_gate + 1
            if gate != expected_gate:
                raise WorkflowStateError(
                    f"Project is at Gate {current_gate}; the next passable gate is "
                    f"Gate {expected_gate}, not Gate {gate}"
                )
            conn.execute(
                """
                INSERT INTO gate_records(project_id, gate, outcome, payload_json, created_at)
                VALUES (?, ?, 'passed', ?, ?)
                """,
                (project_id, gate, db.dumps(dict(payload)), now),
            )
            new_status = "completed" if gate == 7 else "active"
            conn.execute(
                """
                UPDATE projects
                SET current_gate = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (gate, new_status, now, project_id),
            )
            self._audit(
                conn,
                project_id,
                event_type="gate_passed",
                gate=gate,
                details={"payload": dict(payload)},
                created_at=now,
            )
        return self.get_project(project_id)

    def pass_structured_gate(self, project_id: str, gate: int) -> dict[str, Any]:
        """Build gate evidence from normalized records and pass the next gate."""
        payload = self.structured.build_gate_payload(project_id, gate)
        return self.pass_gate(project_id, gate, payload)

    def record_failure(
        self,
        project_id: str,
        gate: int,
        payload: Mapping[str, Any],
        feedback_target: int | None = None,
    ) -> dict[str, Any]:
        """Record a failed review without advancing the workflow.

        ``feedback_target`` may point to an earlier completed gate that should be
        revisited. The current gate is moved back to that gate when supplied.
        """
        now = utc_now()
        with db.connect(self.database) as conn:
            project = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
            if project is None:
                raise KeyError(f"Project not found: {project_id}")
            current_gate = int(project["current_gate"])
            if gate != current_gate + 1:
                raise WorkflowStateError(
                    f"A failure can be recorded only for the next gate ({current_gate + 1})"
                )
            if feedback_target is not None:
                if feedback_target < 0 or feedback_target > current_gate:
                    raise WorkflowStateError(
                        "feedback_target must be an already completed gate"
                    )
                current_gate = feedback_target
                conn.execute(
                    "UPDATE projects SET current_gate = ?, status = 'active', updated_at = ? WHERE id = ?",
                    (current_gate, now, project_id),
                )
            conn.execute(
                """
                INSERT INTO gate_records(project_id, gate, outcome, payload_json, created_at)
                VALUES (?, ?, 'failed', ?, ?)
                """,
                (project_id, gate, db.dumps(dict(payload)), now),
            )
            self._audit(
                conn,
                project_id,
                event_type="gate_failed",
                gate=gate,
                details={
                    "payload": dict(payload),
                    "feedback_target": feedback_target,
                },
                created_at=now,
            )
        return self.get_project(project_id)

    def rollback(self, project_id: str, target_gate: int, reason: str) -> dict[str, Any]:
        if not reason.strip():
            raise ValueError("Rollback reason must not be empty")
        now = utc_now()
        with db.connect(self.database) as conn:
            project = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
            if project is None:
                raise KeyError(f"Project not found: {project_id}")
            current_gate = int(project["current_gate"])
            if target_gate < -1 or target_gate >= current_gate:
                raise WorkflowStateError(
                    "Rollback target must be earlier than the current gate"
                )
            conn.execute(
                "UPDATE projects SET current_gate = ?, status = 'active', updated_at = ? WHERE id = ?",
                (target_gate, now, project_id),
            )
            self._audit(
                conn,
                project_id,
                event_type="rollback",
                gate=target_gate,
                details={"from_gate": current_gate, "reason": reason},
                created_at=now,
            )
        return self.get_project(project_id)

    def gate_records(self, project_id: str) -> list[dict[str, Any]]:
        self.get_project(project_id)
        with db.connect(self.database) as conn:
            rows = conn.execute(
                """
                SELECT id, project_id, gate, outcome, payload_json, created_at
                FROM gate_records WHERE project_id = ? ORDER BY id
                """,
                (project_id,),
            ).fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = db.loads(item.pop("payload_json"))
            records.append(item)
        return records

    def audit_trail(self, project_id: str) -> list[dict[str, Any]]:
        self.get_project(project_id)
        with db.connect(self.database) as conn:
            rows = conn.execute(
                """
                SELECT id, project_id, event_type, gate, details_json, created_at
                FROM audit_events WHERE project_id = ? ORDER BY id
                """,
                (project_id,),
            ).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["details"] = db.loads(item.pop("details_json"))
            events.append(item)
        return events

    def export_manifest(self, project_id: str) -> dict[str, Any]:
        project = self.get_project(project_id)
        return {
            "schema_version": db.SCHEMA_VERSION,
            "project": project,
            "gate_records": self.gate_records(project_id),
            "structured_entities": self.structured.export_project_entities(project_id),
            "pilot_entities": self.pilot.export_project_entities(project_id),
            "pilot_summary": self.pilot.summary(project_id),
            "real_pilot_entities": self.real_pilot.export_project_entities(project_id),
            "release_readiness": self.real_pilot.release_readiness(project_id),
            "audit_trail": self.audit_trail(project_id),
        }

    @staticmethod
    def _audit(
        conn: Any,
        project_id: str,
        event_type: str,
        gate: int | None,
        details: Mapping[str, Any],
        created_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO audit_events(project_id, event_type, gate, details_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, event_type, gate, db.dumps(dict(details)), created_at),
        )
