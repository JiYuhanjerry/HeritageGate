from __future__ import annotations

import json
import sqlite3
from contextlib import closing
import tempfile
import unittest

import heritagegate
import zipfile
from pathlib import Path

from heritagegate import HeritageGateEngine, PilotDataError, calculate_sus_score
from heritagegate.demo import run_pilot_demo
from heritagegate.evidence import build_softwarex_evidence_package
from heritagegate.web import HeritageGateWebApp


class HeritageGateV040Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = HeritageGateEngine(self.root / "test.db")
        self.project_id = "pilot-project"
        self.engine.create_project(
            name="Pilot project",
            heritage_name="Synthetic motif",
            description="Synthetic test project",
            project_id=self.project_id,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def add_participant(self, code: str = "P01", *, consent_status: str = "consented") -> dict:
        return self.engine.pilot.create_entity(
            "participant",
            self.project_id,
            {
                "id": f"participant-{code}",
                "participant_code": code,
                "participant_role": "researcher",
                "experience_level": "novice",
                "consent_status": consent_status,
                "consent_ref": "consent://record" if consent_status == "consented" else "",
                "demographics": {"deidentified": True},
                "notes": "",
            },
        )

    def add_session(self, participant_id: str, condition: str = "heritagegate") -> dict:
        return self.engine.pilot.create_entity(
            "session",
            self.project_id,
            {
                "id": f"session-{condition}",
                "participant_id": participant_id,
                "condition": condition,
                "session_label": f"{condition} session",
                "environment": {"os": "test"},
                "started_at": "2026-07-29T09:00:00+00:00",
                "ended_at": "2026-07-29T10:00:00+00:00",
                "session_status": "completed",
                "notes": "",
            },
        )

    def test_standard_sus_calculation(self) -> None:
        score = calculate_sus_score([4, 2, 4, 2, 4, 2, 4, 2, 4, 2])
        self.assertEqual(score, 75.0)
        with self.assertRaises(PilotDataError):
            calculate_sus_score([4] * 9)

    def test_consent_reference_is_required(self) -> None:
        with self.assertRaises(PilotDataError):
            self.engine.pilot.create_entity(
                "participant",
                self.project_id,
                {
                    "participant_code": "P01",
                    "participant_role": "researcher",
                    "experience_level": "novice",
                    "consent_status": "consented",
                    "consent_ref": "",
                    "demographics": {},
                    "notes": "",
                },
            )

    def test_withdrawn_participant_cannot_start_session(self) -> None:
        participant = self.add_participant(consent_status="withdrawn")
        with self.assertRaises(PilotDataError):
            self.add_session(participant["id"])

    def test_installation_requires_heritagegate_condition(self) -> None:
        participant = self.add_participant()
        session = self.add_session(participant["id"], condition="baseline")
        with self.assertRaises(PilotDataError):
            self.engine.pilot.create_entity(
                "installation",
                self.project_id,
                {
                    "session_id": session["id"],
                    "install_method": "wheel",
                    "software_version": heritagegate.__version__,
                    "started_at": "2026-07-29T09:00:00+00:00",
                    "ended_at": "2026-07-29T09:02:00+00:00",
                    "success": True,
                    "error_count": 0,
                    "environment": {},
                    "evidence_ref": "evidence://install",
                },
            )

    def test_task_attempt_duration_and_success_rules(self) -> None:
        participant = self.add_participant()
        session = self.add_session(participant["id"])
        task = self.engine.pilot.create_entity(
            "task",
            self.project_id,
            {
                "id": "task-1",
                "task_code": "T1",
                "title": "Create project",
                "description": "Create a project",
                "expected_outcome": "Project saved",
                "gate_scope": 0,
                "sequence_order": 1,
                "required": True,
            },
        )
        with self.assertRaises(PilotDataError):
            self.engine.pilot.create_entity(
                "task-attempt",
                self.project_id,
                {
                    "session_id": session["id"],
                    "task_id": task["id"],
                    "started_at": "2026-07-29T09:10:00+00:00",
                    "ended_at": "2026-07-29T09:05:00+00:00",
                    "success": True,
                    "completion_status": "completed",
                    "assistance_count": 0,
                    "error_count": 0,
                    "evidence_ref": "evidence://task",
                    "notes": "",
                },
            )

    def test_pilot_demo_produces_ready_metrics(self) -> None:
        output = run_pilot_demo(self.engine, "demo-pilot")
        summary = output["pilot_summary"]
        self.assertTrue(summary["softwarex_evidence_readiness"]["ready"])
        self.assertEqual(summary["participant_summary"]["total"], 8)
        self.assertEqual(summary["sus_summary"]["responses"], 8)
        self.assertEqual(summary["condition_summary"]["heritagegate"]["task_attempts"], 40)
        self.assertEqual(summary["condition_summary"]["baseline"]["task_attempts"], 40)
        self.assertLess(
            summary["condition_summary"]["heritagegate"]["mean_task_seconds"],
            summary["condition_summary"]["baseline"]["mean_task_seconds"],
        )

    def test_softwarex_evidence_zip_contains_reports_and_figures(self) -> None:
        run_pilot_demo(self.engine, "demo-pilot")
        output = self.root / "evidence.zip"
        metadata = build_softwarex_evidence_package(self.engine, "demo-pilot", output)
        self.assertTrue(metadata["evidence_ready"])
        with zipfile.ZipFile(output) as archive:
            names = archive.namelist()
            self.assertTrue(any(name.endswith("SoftwareX_evidence_report.md") for name in names))
            self.assertTrue(any(name.endswith("softwarex_readiness_checklist.csv") for name in names))
            self.assertTrue(any(name.endswith("figure_task_completion.svg") for name in names))
            self.assertTrue(any(name.endswith("pilot_task_attempts.csv") for name in names))
            report_name = next(name for name in names if name.endswith("SoftwareX_evidence_report.md"))
            report = archive.read(report_name).decode("utf-8")
            self.assertIn("Synthetic demonstration records must not be presented", report)

    def test_v03_database_is_non_destructively_upgraded(self) -> None:
        old = self.root / "old.db"
        with closing(sqlite3.connect(old)) as conn:
            conn.executescript(
                """
                CREATE TABLE projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, heritage_name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '', current_gate INTEGER NOT NULL DEFAULT -1,
                    status TEXT NOT NULL DEFAULT 'active', governance_owner TEXT NOT NULL DEFAULT '',
                    audit_takedown_ready INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE gate_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
                    gate INTEGER NOT NULL, outcome TEXT NOT NULL, payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
                    event_type TEXT NOT NULL, gate INTEGER, details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                INSERT INTO projects VALUES ('old', 'Old', 'Old motif', '', 0, 'active', '', 0, 'x', 'x');
                """
            )
            conn.commit()
        upgraded = HeritageGateEngine(old)
        self.assertEqual(upgraded.get_project("old")["name"], "Old")
        with closing(sqlite3.connect(old)) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            version = conn.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()[0]
        self.assertIn("pilot_studies", tables)
        self.assertIn("sus_responses", tables)
        self.assertEqual(version, "0.5.0")

    def test_web_renderer_contains_pilot_dashboard_and_evidence_export(self) -> None:
        run_pilot_demo(self.engine, "demo-pilot")
        app = HeritageGateWebApp(self.engine.database)
        project_page = app.project_page("demo-pilot")
        pilot_page = app.pilot_page("demo-pilot")
        self.assertIn("Pilot study and SoftwareX evidence", project_page)
        self.assertIn("softwarex-evidence.zip", project_page)
        self.assertIn("mean SUS score", pilot_page)
        self.assertIn("Workflow benchmarks", pilot_page)


if __name__ == "__main__":
    unittest.main()
