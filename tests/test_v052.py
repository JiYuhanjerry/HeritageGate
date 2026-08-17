"""Regression tests for the v0.5.2 corrections.

Each test here pins one defect that was found by running v0.5.1 rather than by
reading it, so that a future change cannot quietly reintroduce the behaviour.
"""

from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from heritagegate.demo import run_pilot_demo, run_structured_demo
from heritagegate.engine import HeritageGateEngine
from heritagegate.realpilot import (
    IDENTITY_SCHEME_KEYED,
    IDENTITY_SCHEME_LEGACY,
    RUN_CONTEXT_FILENAME,
    RealPilotError,
    identifier_rule_for,
)


class BundledDemonstrationTests(unittest.TestCase):
    """The bundled demonstration must satisfy its own quality checker."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_pilot_demo_passes_quality_check_without_blocking_issues(self) -> None:
        engine = HeritageGateEngine(self.root / "demo.db")
        run_pilot_demo(engine, "demo-pilot-001")
        quality = engine.real_pilot.quality_check("demo-pilot-001")
        self.assertEqual(
            quality["blocking_issue_count"], 0,
            f"bundled demonstration reports blocking issues: "
            f"{[i['code'] for i in quality['issues']]}",
        )
        self.assertTrue(quality["passed"])
        self.assertTrue(quality["checks"]["all_participants_enrolled"])

    def test_pilot_demo_is_rerunnable_over_an_existing_database(self) -> None:
        engine = HeritageGateEngine(self.root / "rerun.db")
        run_pilot_demo(engine, "demo-pilot-001")
        run_pilot_demo(engine, "demo-pilot-001")
        quality = engine.real_pilot.quality_check("demo-pilot-001")
        self.assertEqual(quality["blocking_issue_count"], 0)

    def test_duplicate_enrollment_raises_a_domain_error(self) -> None:
        engine = HeritageGateEngine(self.root / "dup.db")
        run_pilot_demo(engine, "demo-pilot-001")
        # The demonstration's participant IDs are an internal detail (and are
        # now salted with the project ID; see the regression test below), so
        # look one up rather than hardcoding its literal string.
        first_participant = engine.pilot.list_entities("demo-pilot-001", "participant")[0]
        with self.assertRaises(RealPilotError):
            engine.real_pilot.enroll_existing_participant(
                "demo-pilot-001",
                first_participant["id"],
                source_token="a-different-token",
            )

    def test_structured_and_pilot_demo_do_not_collide_across_projects(self) -> None:
        """Fifth-round finding: demonstration entity IDs were fixed literals,
        not scoped to the calling project. Running the demonstration under a
        second project ID against the same database found the first
        project's entities already registered under those IDs and silently
        reused them, leaving the second project without its own
        rights-holder or authorization records — so the first thing a new
        user does after the bundled demo (run it again under a project ID of
        their choosing) failed with 'Gate 1 requires at least one approved
        authorization record'.
        """
        engine = HeritageGateEngine(self.root / "cross_project.db")
        run_structured_demo(engine, "proj-A")
        result = run_pilot_demo(engine, "proj-B")
        self.assertEqual(result["quality"]["blocking_issue_count"], 0, result["quality"]["issues"])
        self.assertTrue(result["quality"]["passed"])
        # Each project must have its own authorization record, not share one.
        auth_a = engine.structured.list_entities("proj-A", "authorization")
        auth_b = engine.structured.list_entities("proj-B", "authorization")
        self.assertEqual(len(auth_a), 1)
        self.assertEqual(len(auth_b), 1)
        self.assertNotEqual(auth_a[0]["id"], auth_b[0]["id"])


class DeterministicArtefactTests(unittest.TestCase):
    """Checksummed analysis artefacts must not embed per-run identifiers."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.engine = HeritageGateEngine(self.root / "analysis.db")
        run_pilot_demo(self.engine, "demo-pilot-001")

    def _digests(self, directory: Path) -> dict[str, str]:
        import hashlib

        return {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.iterdir())
            if p.is_file()
        }

    def test_checksummed_outputs_are_identical_across_runs(self) -> None:
        first = self.root / "run1"
        second = self.root / "run2"
        self.engine.real_pilot.write_statistical_report("demo-pilot-001", first, seed=20260729)
        self.engine.real_pilot.write_statistical_report("demo-pilot-001", second, seed=20260729)
        a, b = self._digests(first), self._digests(second)
        checksummed = set(a) - {RUN_CONTEXT_FILENAME}
        for name in sorted(checksummed):
            self.assertEqual(a[name], b[name], f"{name} differs between identical runs")

    def test_sha256sums_verifies_against_a_later_run(self) -> None:
        import hashlib

        first = self.root / "first"
        second = self.root / "second"
        self.engine.real_pilot.write_statistical_report("demo-pilot-001", first, seed=20260729)
        self.engine.real_pilot.write_statistical_report("demo-pilot-001", second, seed=20260729)
        listed = 0
        for line in (first / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            digest, name = line.split("  ", 1)
            actual = hashlib.sha256((second / name).read_bytes()).hexdigest()
            self.assertEqual(digest, actual, f"{name} fails checksum verification on a later run")
            listed += 1
        self.assertGreaterEqual(listed, 4)

    def test_run_scoped_identifiers_are_retained_but_excluded_from_checksums(self) -> None:
        out = self.root / "ctx"
        self.engine.real_pilot.write_statistical_report("demo-pilot-001", out, seed=20260729)
        context = json.loads((out / RUN_CONTEXT_FILENAME).read_text(encoding="utf-8"))
        self.assertTrue(context["analysis_run_id"])
        self.assertTrue(context["quality_run_id"])
        listed = (out / "SHA256SUMS.txt").read_text(encoding="utf-8")
        self.assertNotIn(RUN_CONTEXT_FILENAME, listed)

    def test_different_seed_changes_results(self) -> None:
        a = self.root / "seed_a"
        b = self.root / "seed_b"
        self.engine.real_pilot.write_statistical_report("demo-pilot-001", a, seed=20260729)
        self.engine.real_pilot.write_statistical_report("demo-pilot-001", b, seed=99)
        self.assertNotEqual(
            (a / "analysis_results.json").read_bytes(),
            (b / "analysis_results.json").read_bytes(),
        )


class IdentifierDetectionTests(unittest.TestCase):
    """The import filter must catch variants and non-ASCII headings."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.engine = HeritageGateEngine(self.root / "import.db")
        self.engine.create_project(name="P", heritage_name="H", project_id="P1")

    def _csv(self, extra_column: str, name: str = "p.csv") -> Path:
        path = self.root / name
        fields = ["source_id", "participant_role", "experience_level",
                  "consent_status", "consented_at", "eligibility_status"]
        if extra_column:
            fields.append(extra_column)
        row = {
            "source_id": "L-1", "participant_role": "researcher",
            "experience_level": "novice", "consent_status": "exempt",
            "consented_at": "", "eligibility_status": "eligible",
        }
        if extra_column:
            row[extra_column] = "X"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader(); writer.writerow(row)
        return path

    def test_rejected_column_names(self) -> None:
        for column in [
            "email", "full_name",              # covered in v0.5.1
            "contact_email", "e-mail", "guardian_phone", "telephone",
            "student_id", "id_card", "social_security_number", "passport_number",
            "date_of_birth", "ip_address", "wechat",
            "姓名", "手机号", "身份证号", "电子邮箱", "联系方式", "学号",
        ]:
            with self.subTest(column=column):
                self.assertIsNotNone(
                    identifier_rule_for(column.strip().lower().replace("-", "_").replace(" ", "_")),
                    f"{column} should be recognized as a direct identifier",
                )
                with self.assertRaises(RealPilotError):
                    self.engine.real_pilot.import_participants_csv(
                        "P1", self._csv(column, f"{abs(hash(column))}.csv")
                    )

    def test_benign_column_names_are_not_rejected(self) -> None:
        for column in ["condition_name", "task_name", "site_code", "cohort", "notes"]:
            with self.subTest(column=column):
                self.assertIsNone(
                    identifier_rule_for(column),
                    f"{column} should not be treated as a direct identifier",
                )

    def test_unrecognized_columns_are_reported_rather_than_silently_dropped(self) -> None:
        batch = self.engine.real_pilot.import_participants_csv("P1", self._csv("site_code"))
        self.assertIn("site_code", batch["dropped_columns"])
        self.assertTrue(batch["warnings"])
        self.assertIn("discarded", batch["warnings"][0])


    def test_batch_warnings_have_the_same_shape_when_read_back(self) -> None:
        batch = self.engine.real_pilot.import_participants_csv("P1", self._csv("site_code"))
        again = self.engine.real_pilot.get_entity("import-batch", batch["id"])
        self.assertEqual(batch["warnings"], again["warnings"])
        self.assertEqual(batch["dropped_columns"], again["dropped_columns"])

    def test_nested_identifiers_are_rejected_at_import_time(self) -> None:
        """Nested identifiers never reach the database at all.

        The row is refused during import, so the value is not stored and the
        later quality check has nothing to find. Asserting on the rejection is
        therefore the correct expectation, not a weaker one.
        """
        path = self.root / "demo.csv"
        fields = ["source_id", "participant_role", "experience_level",
                  "consent_status", "eligibility_status", "demographics_json"]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow({
                "source_id": "L-9", "participant_role": "researcher",
                "experience_level": "novice", "consent_status": "exempt",
                "eligibility_status": "eligible",
                "demographics_json": json.dumps({"profile": {"姓名": "X"}}),
            })
        batch = self.engine.real_pilot.import_participants_csv("P1", path)
        self.assertEqual(batch["imported_count"], 0)
        self.assertEqual(batch["rejected_count"], 1)
        reason = batch["rejected_rows"][0]["reason"]
        self.assertIn("direct-identifier", reason)
        self.assertIn("姓名", reason)
        # The rejection reason must not echo the identifier *value*.
        self.assertNotIn("X", reason.replace("XX", ""))

    def test_quality_check_flags_identifiers_already_in_the_database(self) -> None:
        """A record written through the pilot API is still caught downstream."""
        self.engine.pilot.create_entity("participant", "P1", {
            "id": "participant-z", "participant_code": "P01",
            "participant_role": "researcher", "experience_level": "novice",
            "consent_status": "exempt",
            "demographics": {"profile": {"手机号": "X"}},
        })
        self.engine.real_pilot.enroll_existing_participant(
            "P1", "participant-z", source_token="LOCAL-Z"
        )
        quality = self.engine.real_pilot.quality_check("P1")
        codes = {i["code"] for i in quality["issues"]}
        self.assertIn("DIRECT_IDENTIFIER_KEY", codes)

    def test_shipped_import_template_is_still_accepted(self) -> None:
        """The expanded filter must not reject the package's own template."""
        template = (
            Path(__file__).resolve().parent.parent
            / "examples" / "v050_real_pilot" / "participant_import_template.csv"
        )
        if not template.is_file():
            self.skipTest("template not present in this checkout")
        consent_file = self.root / "consent.txt"
        consent_file.write_text("synthetic consent text", encoding="utf-8")
        consent = self.engine.real_pilot.register_consent_document(
            "P1",
            document_path=consent_file,
            title="Template consent",
            version="1.0",
            language="en",
            ethics_ref="synthetic://ethics/exempt",
            effective_from="2026-01-01",
            withdrawal_contact="research@example.org",
            retention_policy="Retain de-identified data for five years",
        )
        batch = self.engine.real_pilot.import_participants_csv(
            "P1", template, consent_document_id=consent["id"]
        )
        self.assertEqual(batch["rejected_count"], 0, batch.get("rejected_rows"))
        self.assertEqual(batch["imported_count"], 1)


class KeyedPseudonymizationTests(unittest.TestCase):
    """Identity derivation must be keyed, and legacy databases must still work."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_new_database_uses_keyed_scheme_and_writes_key_outside_the_database(self) -> None:
        engine = HeritageGateEngine(self.root / "keyed.db")
        engine.create_project(name="P", heritage_name="H", project_id="P1")
        run_pilot_demo(engine, "demo-pilot-001")
        self.assertEqual(engine.real_pilot.identity_scheme(), IDENTITY_SCHEME_KEYED)
        key_path = engine.real_pilot.identity_key_path()
        self.assertTrue(key_path.exists())
        self.assertNotEqual(key_path.parent / key_path.name, Path(str(engine.database)))

    def test_identity_hash_is_not_reproducible_without_the_key(self) -> None:
        import hashlib

        engine = HeritageGateEngine(self.root / "unguessable.db")
        engine.create_project(name="P", heritage_name="H", project_id="P1")
        engine.pilot.create_entity("participant", "P1", {
            "id": "participant-x", "participant_code": "P01",
            "participant_role": "researcher", "experience_level": "novice",
            "consent_status": "exempt", "demographics": {},
        })
        engine.real_pilot.enroll_existing_participant(
            "P1", "participant-x", source_token="LOCAL-001"
        )
        rows = engine.real_pilot.list_entities("P1", "enrollment")
        stored = rows[0]["identity_token_hash"]
        naive = hashlib.sha256("P1|LOCAL-001".encode("utf-8")).hexdigest()
        self.assertNotEqual(
            stored, naive,
            "identity hash is reproducible from public information alone",
        )

    def test_existing_legacy_database_keeps_the_legacy_scheme(self) -> None:
        import hashlib

        from heritagegate import db as dbmod

        engine = HeritageGateEngine(self.root / "legacy.db")
        engine.create_project(name="P", heritage_name="H", project_id="P1")
        engine.pilot.create_entity("participant", "P1", {
            "id": "participant-y", "participant_code": "P01",
            "participant_role": "researcher", "experience_level": "novice",
            "consent_status": "exempt", "demographics": {},
        })
        # Simulate a database written by v0.5.1: an enrollment exists and no
        # scheme marker has been recorded.
        legacy_hash = hashlib.sha256("P1|LEGACY-1".encode("utf-8")).hexdigest()
        now = "2026-01-01T00:00:00+00:00"
        with dbmod.connect(engine.database) as conn:
            conn.execute(
                "INSERT INTO participant_enrollments(id, project_id, participant_id,"
                " consent_document_id, import_batch_id, eligibility_status, consented_at,"
                " withdrawn_at, identity_token_hash, source_row_hash, data_use_scope_json,"
                " created_at, updated_at)"
                " VALUES (?,?,?,NULL,NULL,'eligible','','',?,?,?,?,?)",
                (f"enrollment-{legacy_hash[:16]}", "P1", "participant-y",
                 legacy_hash, "rowhash", dbmod.dumps(["pilot_analysis"]), now, now),
            )
            conn.execute("DELETE FROM schema_metadata WHERE key = 'identity_hash_scheme'")
        self.assertEqual(engine.real_pilot.identity_scheme(), IDENTITY_SCHEME_LEGACY)


class KeyIntegrityTests(unittest.TestCase):
    """Findings from the v0.5.2 self-audit."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _engine(self, name: str = "k.db"):
        engine = HeritageGateEngine(self.root / name)
        engine.create_project(name="P", heritage_name="H", project_id="P1")
        return engine

    def _participant(self, engine, pid: str, code: str) -> None:
        engine.pilot.create_entity("participant", "P1", {
            "id": pid, "participant_code": code,
            "participant_role": "researcher", "experience_level": "novice",
            "consent_status": "exempt", "demographics": {},
        })

    def test_substituted_key_is_refused_rather_than_silently_accepted(self) -> None:
        engine = self._engine()
        self._participant(engine, "pt1", "P01")
        engine.real_pilot.enroll_existing_participant("P1", "pt1", source_token="LOCAL-1")
        engine.real_pilot.identity_key_path().write_text("00" * 32 + "\n", encoding="utf-8")
        fresh = HeritageGateEngine(self.root / "k.db")
        self._participant(fresh, "pt2", "P02")
        with self.assertRaises(RealPilotError) as ctx:
            fresh.real_pilot.enroll_existing_participant("P1", "pt2", source_token="LOCAL-2")
        self.assertIn("does not match", str(ctx.exception))

    def test_empty_key_file_is_refused(self) -> None:
        engine = self._engine("e.db")
        self._participant(engine, "pt", "P01")
        engine.real_pilot.identity_key_path().write_text("", encoding="utf-8")
        with self.assertRaises(RealPilotError):
            engine.real_pilot.enroll_existing_participant("P1", "pt", source_token="X")

    def test_in_memory_database_refuses_keyed_derivation(self) -> None:
        # ":memory:" cannot be passed to the engine constructor on Windows,
        # where a colon is invalid in file names and init_db fails before the
        # guard under test is reached; on POSIX the construction also leaves a
        # literal file of that name behind. Point an otherwise valid manager
        # at the sentinel instead, so the guard itself is exercised on every
        # platform without touching the filesystem.
        engine = self._engine("mem_guard.db")
        engine.real_pilot.database = ":memory:"
        with self.assertRaises(RealPilotError) as ctx:
            engine.real_pilot.identity_key_path()
        self.assertIn("stable location", str(ctx.exception))

    def test_bulk_import_does_not_reopen_the_database_per_row(self) -> None:
        """The scheme lookup is cached; without it each row cost two extra connections."""
        from heritagegate import db as dbmod

        engine = self._engine("bulk.db")
        path = self.root / "bulk.csv"
        fields = ["source_id", "participant_role", "experience_level",
                  "consent_status", "eligibility_status"]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for i in range(30):
                writer.writerow({
                    "source_id": f"L-{i}", "participant_role": "researcher",
                    "experience_level": "novice", "consent_status": "exempt",
                    "eligibility_status": "eligible",
                })
        original = dbmod.connect
        calls = {"n": 0}

        def counting(*args, **kwargs):
            calls["n"] += 1
            return original(*args, **kwargs)

        dbmod.connect = counting
        try:
            engine.real_pilot.import_participants_csv("P1", path)
        finally:
            dbmod.connect = original
        self.assertLess(
            calls["n"] / 30, 2.0,
            f"{calls['n'] / 30:.1f} database connections per row suggests the "
            "scheme or key lookup is no longer cached",
        )

    def test_shipped_release_template_matches_the_package_version(self) -> None:
        import json as _json

        template = (
            Path(__file__).resolve().parent.parent
            / "examples" / "v050_real_pilot" / "release_profile_template.json"
        )
        if not template.is_file():
            self.skipTest("template not present in this checkout")
        profile = _json.loads(template.read_text(encoding="utf-8"))
        import heritagegate

        self.assertEqual(
            profile["software_version"], heritagegate.__version__,
            "the shipped release template would fail the release-readiness check",
        )


class ThirdRoundAuditTests(unittest.TestCase):
    """Findings from the third audit round."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _engine(self, name="t.db"):
        engine = HeritageGateEngine(self.root / name)
        engine.create_project(name="P", heritage_name="H", project_id="P1")
        return engine

    def test_missing_key_for_an_existing_database_is_refused_without_creating_one(self) -> None:
        """A database copied without its key must not silently get a new one."""
        engine = self._engine("orig.db")
        engine.pilot.create_entity("participant", "P1", {
            "id": "pt", "participant_code": "P01", "participant_role": "researcher",
            "experience_level": "novice", "consent_status": "exempt", "demographics": {},
        })
        engine.real_pilot.enroll_existing_participant("P1", "pt", source_token="LOCAL-1")
        moved = self.root / "moved"
        moved.mkdir()
        shutil.copy(self.root / "orig.db", moved / "orig.db")
        relocated = HeritageGateEngine(moved / "orig.db")
        relocated.pilot.create_entity("participant", "P1", {
            "id": "pt2", "participant_code": "P02", "participant_role": "researcher",
            "experience_level": "novice", "consent_status": "exempt", "demographics": {},
        })
        with self.assertRaises(RealPilotError) as ctx:
            relocated.real_pilot.enroll_existing_participant("P1", "pt2", source_token="LOCAL-2")
        self.assertIn("missing", str(ctx.exception).lower())
        self.assertFalse(
            (moved / "orig.db.key").exists(),
            "a misleading key file was created for a database whose key is absent",
        )

    def test_import_batch_decodes_when_mapping_is_not_an_object(self) -> None:
        """A hand-edited or legacy record must not crash the read path."""
        from heritagegate import db as dbmod

        engine = self._engine("decode.db")
        with dbmod.connect(engine.database) as conn:
            conn.execute(
                "INSERT INTO participant_import_batches(id, project_id, source_name,"
                " source_sha256, imported_count, rejected_count, duplicate_count,"
                " mapping_json, rejected_rows_json, created_at)"
                " VALUES ('b1','P1','x.csv','abc',0,0,0,?,?,'2026-01-01')",
                ('["not","a","dict"]', "[]"),
            )
        batch = engine.real_pilot.get_entity("import-batch", "b1")
        self.assertEqual(batch["warnings"], [])
        self.assertEqual(batch["dropped_columns"], [])

    def test_research_export_states_that_it_is_restricted(self) -> None:
        """The research bundle carries identity hashes and must say so."""
        import zipfile

        engine = self._engine("res.db")
        archive = self.root / "research.zip"
        from heritagegate.exporter import build_research_bundle

        build_research_bundle(engine, "P1", archive)
        with zipfile.ZipFile(archive) as zf:
            name = next(n for n in zf.namelist() if n.endswith("README.txt"))
            readme = zf.read(name).decode("utf-8")
        self.assertIn("RESTRICTED", readme)
        self.assertIn("manifest.json", readme)
        self.assertIn("export-submission-release", readme)


class FourthRoundAuditTests(unittest.TestCase):
    """Findings from the fourth audit round."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_csv_exports_neutralize_spreadsheet_formulas(self) -> None:
        """Exports are written for Excel, so formula-leading cells must be inert."""
        from heritagegate.exporter import export_csv_directory

        engine = HeritageGateEngine(self.root / "inject.db")
        engine.create_project(name="P", heritage_name="H", project_id="P1")
        engine.pilot.create_entity("participant", "P1", {
            "id": "pt", "participant_code": "P01", "participant_role": "researcher",
            "experience_level": "novice", "consent_status": "exempt",
            "demographics": {}, "notes": "=cmd|'/c calc'!A1",
        })
        out = self.root / "csvout"
        export_csv_directory(engine, "P1", out)
        def is_number(text: str) -> bool:
            try:
                float(text)
            except ValueError:
                return False
            return True

        offenders = []
        for path in out.rglob("*.csv"):
            for row in csv.reader(path.open(encoding="utf-8-sig")):
                for cell in row:
                    # A plain negative number is not an injection risk; a
                    # spreadsheet treats it as a value, not a formula.
                    if len(cell) > 1 and cell[0] in "=+-@" and not is_number(cell):
                        offenders.append((path.name, cell[:40]))
        self.assertEqual(offenders, [], f"formula-leading cells exported: {offenders}")

    def test_gate_evidence_rejects_nan_and_infinity(self) -> None:
        """Non-finite numbers are neither valid evidence nor valid JSON."""
        from heritagegate.validators import GateValidationError, validate_gate

        base = {
            "dataset_id": "D", "technical_metadata_complete": True,
            "cultural_metadata_complete": True, "license_terms": "L",
            "capture_log_ref": "c",
        }
        for bad in (float("inf"), float("-inf"), float("nan")):
            with self.subTest(value=bad):
                with self.assertRaises(GateValidationError):
                    validate_gate(2, {**base, "source_count": bad})
        validate_gate(2, {**base, "source_count": 10})

    def test_market_test_scores_reject_non_finite(self) -> None:
        from heritagegate.validators import GateValidationError, validate_gate

        payload = {
            "sample_size": 30, "perceived_authenticity": 4,
            "perceived_cultural_value": 4, "story_comprehension": 4,
            "purchase_intention": 4, "recommendation_intention": 4,
            "test_channel": "online", "market_test_report_ref": "r",
        }
        with self.assertRaises(GateValidationError):
            validate_gate(6, {**payload, "perceived_authenticity": float("nan")})
        validate_gate(6, payload)


if __name__ == "__main__":
    unittest.main()
