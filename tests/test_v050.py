from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
import unittest

import heritagegate
import zipfile
from contextlib import closing
from pathlib import Path

from heritagegate import HeritageGateEngine, RealPilotError
from heritagegate.demo import run_pilot_demo
from heritagegate.release import build_submission_release_package
from heritagegate.web import HeritageGateWebApp


class HeritageGateV050Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = HeritageGateEngine(self.root / "test.db")
        self.project_id = "real-pilot-project"
        self.engine.create_project(
            name="Real pilot project",
            heritage_name="Synthetic motif for tests",
            description="No real participant data in automated tests.",
            project_id=self.project_id,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _consent(self) -> dict:
        path = self.root / "consent.txt"
        path.write_text("Synthetic consent text for software testing only.", encoding="utf-8")
        return self.engine.real_pilot.register_consent_document(
            self.project_id,
            document_path=path,
            title="Pilot consent",
            version="1.0",
            language="en",
            ethics_ref="ETHICS-TEST",
            effective_from="2026-07-01",
            withdrawal_contact="research@example.org",
            retention_policy="Retain de-identified records for five years.",
            document_id="consent-test",
        )

    def _write_participants(self, rows: list[dict], name: str = "participants.csv") -> Path:
        path = self.root / name
        fieldnames = list(rows[0])
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader(); writer.writerows(rows)
        return path

    def _synthetic_ready_data(self, project_id: str = "demo-v050") -> HeritageGateEngine:
        engine = HeritageGateEngine(self.root / f"{project_id}.db")
        run_pilot_demo(engine, project_id)
        participants = engine.pilot.list_entities(project_id, "participant")
        # run_pilot_demo enrolls its own synthetic participants from v0.5.2
        # onwards, so only participants without an enrollment are added here.
        already = {
            row["participant_id"]
            for row in engine.real_pilot.list_entities(project_id, "enrollment")
        }
        for index, participant in enumerate(participants, 1):
            if participant["id"] in already:
                continue
            engine.real_pilot.enroll_existing_participant(
                project_id,
                participant["id"],
                source_token=f"synthetic-local-{index}",
                eligibility_status="eligible",
                data_use_scope=["pilot_analysis"],
            )
        return engine

    @staticmethod
    def _release_payload(evidence_status: str = "synthetic") -> dict:
        return {
            "software_title": "HeritageGate",
            "manuscript_title": "HeritageGate: An open-source platform for rights-aware heritage AI workflows",
            "software_version": heritagegate.__version__,
            "release_status": "candidate",
            "evidence_status": evidence_status,
            "repository_url": "https://example.org/repository",
            "archive_url": "https://example.org/archive",
            "software_doi": "10.0000/example.doi",
            "executable_url": "https://example.org/wheel",
            "documentation_url": "https://example.org/docs",
            "support_email": "support@example.org",
            "license_spdx": "Apache-2.0",
            "authors": [{"name": "Test Author", "affiliation": "Test Institute"}],
            "keywords": ["intangible cultural heritage", "research software", "generative AI"],
            "release_date": "2026-07-29",
            "funding_statement": "No external funding in synthetic tests.",
            "conflict_statement": "The authors declare no competing interests.",
            "ai_use_statement": "Synthetic placeholder for test output.",
            "data_availability_statement": "Only synthetic examples are distributed with tests.",
        }

    def test_consent_file_is_hashed_and_not_embedded(self) -> None:
        record = self._consent()
        self.assertEqual(len(record["body_sha256"]), 64)
        self.assertTrue(record["body_ref"].endswith("consent.txt"))
        self.assertNotIn("Synthetic consent text", json.dumps(record))

    def test_import_refuses_direct_identifier_columns(self) -> None:
        path = self._write_participants([{
            "source_id": "local-1", "name": "Not allowed", "participant_role": "researcher",
            "experience_level": "novice", "consent_status": "exempt",
        }])
        with self.assertRaises(RealPilotError):
            self.engine.real_pilot.import_participants_csv(self.project_id, path)

    def test_anonymous_import_does_not_store_source_identifier(self) -> None:
        consent = self._consent()
        path = self._write_participants([{
            "source_id": "PRIVATE-LOCAL-ID-123", "participant_role": "researcher",
            "experience_level": "novice", "consent_status": "consented",
            "consented_at": "2026-07-02T09:00:00+00:00", "eligibility_status": "eligible",
            "demographics_json": '{"age_band":"25-34"}',
            "data_use_scope_json": '["pilot_analysis","aggregate_publication"]', "notes": "",
        }])
        batch = self.engine.real_pilot.import_participants_csv(
            self.project_id, path, consent_document_id=consent["id"]
        )
        self.assertEqual(batch["imported_count"], 1)
        participants = self.engine.pilot.list_entities(self.project_id, "participant")
        enrollments = self.engine.real_pilot.list_entities(self.project_id, "enrollment")
        self.assertEqual(len(participants), 1)
        self.assertTrue(participants[0]["participant_code"].startswith("P-"))
        database_bytes = (self.root / "test.db").read_bytes()
        self.assertNotIn(b"PRIVATE-LOCAL-ID-123", database_bytes)
        self.assertEqual(len(enrollments[0]["identity_token_hash"]), 64)

    def test_duplicate_import_is_counted_without_duplicate_participant(self) -> None:
        path = self._write_participants([{
            "source_id": "same-local-id", "participant_role": "student",
            "experience_level": "novice", "consent_status": "exempt",
            "consented_at": "", "eligibility_status": "eligible",
            "demographics_json": "{}", "data_use_scope_json": "pilot_analysis", "notes": "",
        }])
        first = self.engine.real_pilot.import_participants_csv(self.project_id, path)
        second = self.engine.real_pilot.import_participants_csv(self.project_id, path)
        self.assertEqual(first["imported_count"], 1)
        self.assertEqual(second["duplicate_count"], 1)
        self.assertEqual(len(self.engine.pilot.list_entities(self.project_id, "participant")), 1)

    def test_withdrawal_prevents_new_sessions(self) -> None:
        path = self._write_participants([{
            "source_id": "withdraw-local", "participant_role": "researcher",
            "experience_level": "intermediate", "consent_status": "exempt",
            "consented_at": "", "eligibility_status": "eligible",
            "demographics_json": "{}", "data_use_scope_json": "pilot_analysis", "notes": "",
        }])
        self.engine.real_pilot.import_participants_csv(self.project_id, path)
        participant = self.engine.pilot.list_entities(self.project_id, "participant")[0]
        self.engine.real_pilot.withdraw_participant(
            self.project_id, participant["id"],
            withdrawn_at="2026-07-03T10:00:00+00:00", reason="Participant request",
        )
        with self.assertRaises(Exception):
            self.engine.pilot.create_entity("session", self.project_id, {
                "participant_id": participant["id"], "condition": "heritagegate",
                "session_label": "After withdrawal", "environment": {},
                "started_at": "2026-07-03T11:00:00+00:00",
                "ended_at": "2026-07-03T12:00:00+00:00",
                "session_status": "completed", "notes": "",
            })

    def test_quality_check_detects_missing_enrollment_and_protocol(self) -> None:
        self.engine.pilot.create_entity("participant", self.project_id, {
            "participant_code": "P01", "participant_role": "researcher",
            "experience_level": "novice", "consent_status": "exempt",
            "consent_ref": "", "demographics": {}, "notes": "",
        })
        report = self.engine.real_pilot.quality_check(self.project_id)
        self.assertFalse(report["passed"])
        codes = {item["code"] for item in report["issues"]}
        self.assertIn("PROTOCOL_COUNT", codes)
        self.assertIn("MISSING_ENROLLMENT", codes)

    def test_deterministic_report_contains_intervals_and_checksums(self) -> None:
        engine = self._synthetic_ready_data("analysis-demo")
        first = engine.real_pilot.write_statistical_report("analysis-demo", self.root / "analysis1", seed=123)
        second = engine.real_pilot.write_statistical_report("analysis-demo", self.root / "analysis2", seed=123)
        self.assertEqual(first["results"]["input_sha256"], second["results"]["input_sha256"])
        one = json.loads((self.root / "analysis1" / "analysis_results.json").read_text(encoding="utf-8"))
        two = json.loads((self.root / "analysis2" / "analysis_results.json").read_text(encoding="utf-8"))
        self.assertEqual(one["paired_comparison"], two["paired_comparison"])
        self.assertTrue((self.root / "analysis1" / "SHA256SUMS.txt").is_file())
        self.assertIn("Wilson 95% interval", (self.root / "analysis1" / "analysis_report.md").read_text(encoding="utf-8"))

    def test_submission_package_excludes_participant_level_records(self) -> None:
        engine = self._synthetic_ready_data("release-demo")
        engine.real_pilot.write_statistical_report("release-demo", self.root / "analysis-release")
        engine.real_pilot.upsert_release_profile("release-demo", self._release_payload())
        output = self.root / "submission.zip"
        metadata = build_submission_release_package(
            engine, "release-demo", output,
            source_root=Path(__file__).resolve().parents[1],
        )
        self.assertFalse(metadata["participant_level_records_included"])
        with zipfile.ZipFile(output) as archive:
            names = archive.namelist()
            self.assertTrue(any(name.endswith("SoftwareX_manuscript_draft.md") for name in names))
            self.assertTrue(any(name.endswith(".zenodo.json") for name in names))
            self.assertTrue(any(name.endswith("codemeta.json") for name in names))
            self.assertFalse(any("pilot_participants.csv" in name for name in names))
            self.assertFalse(any("participant_enrollments.csv" in name for name in names))
            privacy_name = next(name for name in names if name.endswith("PRIVACY_EXCLUSION_LOG.md"))
            self.assertIn("participant codes", archive.read(privacy_name).decode("utf-8"))

    def test_release_readiness_rejects_synthetic_data(self) -> None:
        engine = self._synthetic_ready_data("not-ready")
        engine.real_pilot.quality_check("not-ready")
        engine.real_pilot.write_statistical_report("not-ready", self.root / "not-ready-analysis")
        engine.real_pilot.upsert_release_profile("not-ready", self._release_payload("synthetic"))
        readiness = engine.real_pilot.release_readiness("not-ready")
        self.assertFalse(readiness["ready"])
        self.assertFalse(readiness["checks"]["validated_real_pilot"])
        self.assertFalse(readiness["checks"]["no_synthetic_participants"])

    def test_release_readiness_can_pass_after_author_verified_configuration(self) -> None:
        engine = self._synthetic_ready_data("ready-config")
        with closing(sqlite3.connect(engine.database)) as conn:
            for row in conn.execute("SELECT id FROM pilot_participants WHERE project_id = ?", ("ready-config",)):
                conn.execute(
                    "UPDATE pilot_participants SET demographics_json = ? WHERE id = ?",
                    (json.dumps({"deidentified": True}), row[0]),
                )
            conn.commit()
        quality = engine.real_pilot.quality_check("ready-config")
        self.assertTrue(quality["passed"])
        engine.real_pilot.write_statistical_report("ready-config", self.root / "ready-analysis")
        engine.real_pilot.upsert_release_profile(
            "ready-config", self._release_payload("validated_real_pilot")
        )
        readiness = engine.real_pilot.release_readiness("ready-config")
        self.assertTrue(readiness["ready"])

    def test_v04_database_is_non_destructively_upgraded(self) -> None:
        old = self.root / "old-v04.db"
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
        self.assertIn("participant_enrollments", tables)
        self.assertIn("release_profiles", tables)
        self.assertEqual(version, "0.5.0")

    def test_web_renderer_contains_real_pilot_and_submission_release(self) -> None:
        engine = self._synthetic_ready_data("web-v050")
        engine.real_pilot.quality_check("web-v050")
        engine.real_pilot.write_statistical_report("web-v050", self.root / "web-analysis")
        engine.real_pilot.upsert_release_profile("web-v050", self._release_payload())
        app = HeritageGateWebApp(engine.database)
        project_page = app.project_page("web-v050")
        real_page = app.real_pilot_page("web-v050")
        self.assertIn("Real pilot and submission release", project_page)
        self.assertIn("submission-release.zip", project_page)
        self.assertIn("Privacy-safe submission package", real_page)
        self.assertIn("identity hashes", real_page)


if __name__ == "__main__":
    unittest.main()
