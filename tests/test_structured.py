from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from heritagegate.demo import GATE_PAYLOADS, run_structured_demo
from heritagegate.engine import HeritageGateEngine
from heritagegate.structured import StructuredDataError


class HeritageGateStructuredDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "structured.db"
        self.engine = HeritageGateEngine(self.db)
        self.project_id = "structured-test"
        self.engine.create_project(
            "Structured test", "Synthetic motif", project_id=self.project_id
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def add_holder(
        self, holder_id: str, holder_type: str = "bearer", name: str | None = None
    ) -> dict:
        return self.engine.structured.add_rights_holder(
            self.project_id,
            {
                "id": holder_id,
                "name": name or holder_id,
                "holder_type": holder_type,
                "authority_basis": "Synthetic test authority",
            },
        )

    def add_authorization(self, holder_id: str = "holder-bearer") -> dict:
        try:
            self.engine.structured.get_entity("rights-holder", holder_id)
        except KeyError:
            self.add_holder(holder_id)
        return self.engine.structured.add_authorization(
            self.project_id,
            {
                "id": "auth-1",
                "status": "approved",
                "parties": [
                    {"rights_holder_id": holder_id, "party_role": "authorizer"},
                    {"rights_holder_id": holder_id, "party_role": "beneficiary"},
                ],
                "permitted_uses": ["research"],
                "prohibited_uses": ["false authenticity claim"],
                "attribution_requirements": "Synthetic attribution",
                "revenue_terms": "50% synthetic allocation",
                "evidence_ref": "synthetic://auth/1",
            },
        )

    def add_element(self, element_id: str = "element-1", status: str = "approved") -> dict:
        try:
            self.engine.structured.get_entity("rights-holder", "holder-bearer")
        except KeyError:
            self.add_holder("holder-bearer")
        return self.engine.structured.add_element_card(
            self.project_id,
            {
                "id": element_id,
                "element_code": element_id.upper(),
                "name": "Synthetic element",
                "cultural_meaning": "Synthetic meaning",
                "source_ref": "synthetic://source",
                "attribution_text": "Synthetic attribution",
                "permitted_uses": ["research"],
                "prohibited_uses": ["misrepresentation"],
                "technical_features": {"symmetry": "bilateral"},
                "prohibited_combinations": ["real restricted motifs"],
                "sensitivity_level": "controlled",
                "status": status,
                "version": "0.2-test",
                "annotators": [
                    {
                        "rights_holder_id": "holder-bearer",
                        "annotation_role": "principal",
                    }
                ],
            },
        )

    def add_model_run(self, element_id: str = "element-1") -> dict:
        return self.engine.structured.add_model_run(
            self.project_id,
            {
                "id": "run-1",
                "model_name": "SyntheticGenerator",
                "model_version": "0.2-test",
                "constraint_method": "adapter simulation",
                "parameters": {"seed": 1},
                "source_element_ids": [element_id],
                "output_count": 5,
                "provenance_ref": "synthetic://runs/1",
                "run_status": "completed",
            },
        )

    def test_rights_holder_is_independent_entity(self) -> None:
        holder = self.add_holder("holder-1")
        self.assertEqual(holder["id"], "holder-1")
        self.assertTrue(holder["active"])
        self.assertEqual(
            len(self.engine.structured.list_entities(self.project_id, "rights-holder")),
            1,
        )

    def test_authorization_requires_existing_rights_holder(self) -> None:
        with self.assertRaises(StructuredDataError):
            self.engine.structured.add_authorization(
                self.project_id,
                {
                    "status": "approved",
                    "parties": [
                        {"rights_holder_id": "missing", "party_role": "authorizer"}
                    ],
                    "permitted_uses": ["research"],
                    "prohibited_uses": ["misuse"],
                    "attribution_requirements": "required",
                    "revenue_terms": "specified",
                    "evidence_ref": "synthetic://missing",
                },
            )

    def test_gate1_payload_is_built_from_authorization_entities(self) -> None:
        self.add_authorization()
        report = self.engine.structured.readiness_report(self.project_id, 1)
        self.assertTrue(report["ready"])
        self.assertEqual(report["payload"]["authorization_status"], "approved")
        self.assertIn("holder-bearer", report["payload"]["authorizers"])

    def test_gate3_requires_bearer_annotation_and_prohibited_combinations(self) -> None:
        self.add_element()
        report = self.engine.structured.readiness_report(self.project_id, 3)
        self.assertTrue(report["ready"])
        self.assertEqual(report["payload"]["elements_count"], 1)

    def test_completed_model_run_rejects_draft_element(self) -> None:
        self.add_element(status="draft")
        with self.assertRaises(StructuredDataError):
            self.add_model_run()

    def test_gate4_payload_preserves_element_provenance(self) -> None:
        self.add_element()
        self.add_model_run()
        payload = self.engine.structured.build_gate_payload(self.project_id, 4)
        self.assertTrue(payload["provenance_enabled"])
        self.assertEqual(payload["source_element_ids"], ["element-1"])

    def test_gate5_requires_three_approval_roles(self) -> None:
        self.add_element()
        self.add_model_run()
        self.add_holder("holder-design", "designer")
        self.add_holder("holder-producer", "producer")
        base = {
            "model_run_id": "run-1",
            "decision": "approved",
            "evidence_ref": "synthetic://review",
        }
        self.engine.structured.add_expert_review(
            self.project_id,
            {
                **base,
                "id": "review-bearer",
                "reviewer_rights_holder_id": "holder-bearer",
                "reviewer_role": "bearer",
                "cultural_score": 4.0,
            },
        )
        self.assertFalse(self.engine.structured.readiness_report(self.project_id, 5)["ready"])
        self.engine.structured.add_expert_review(
            self.project_id,
            {
                **base,
                "id": "review-design",
                "reviewer_rights_holder_id": "holder-design",
                "reviewer_role": "design_expert",
                "aesthetic_score": 4.0,
            },
        )
        self.engine.structured.add_expert_review(
            self.project_id,
            {
                **base,
                "id": "review-production",
                "reviewer_rights_holder_id": "holder-producer",
                "reviewer_role": "production_expert",
                "feasibility_score": 4.0,
            },
        )
        self.assertTrue(self.engine.structured.readiness_report(self.project_id, 5)["ready"])

    def test_market_test_scores_are_bounded(self) -> None:
        self.add_element()
        self.add_model_run()
        with self.assertRaises(StructuredDataError):
            self.engine.structured.add_market_test(
                self.project_id,
                {
                    "model_run_id": "run-1",
                    "sample_size": 20,
                    "test_channel": "synthetic panel",
                    "perceived_authenticity": 6.0,
                    "perceived_cultural_value": 4.0,
                    "story_comprehension": 4.0,
                    "purchase_intention": 4.0,
                    "recommendation_intention": 4.0,
                    "recommendation": "revise",
                    "report_ref": "synthetic://market",
                },
            )

    def test_revenue_shares_cannot_exceed_one_hundred_percent(self) -> None:
        self.add_authorization()
        common = {
            "authorization_id": "auth-1",
            "recipient_rights_holder_id": "holder-bearer",
            "revenue_category": "product",
            "gross_amount": 100.0,
            "currency": "USD",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "evidence_ref": "synthetic://distribution",
        }
        self.engine.structured.add_revenue_distribution(
            self.project_id,
            {
                **common,
                "id": "distribution-1",
                "share_percent": 60.0,
                "distributed_amount": 60.0,
            },
        )
        with self.assertRaises(StructuredDataError):
            self.engine.structured.add_revenue_distribution(
                self.project_id,
                {
                    **common,
                    "id": "distribution-2",
                    "share_percent": 50.0,
                    "distributed_amount": 40.0,
                },
            )

    def test_structured_demo_reaches_gate7_and_exports_entities(self) -> None:
        demo_db = Path(self.tmp.name) / "demo.db"
        engine = HeritageGateEngine(demo_db)
        manifest = run_structured_demo(engine)
        self.assertEqual(manifest["project"]["status"], "completed")
        self.assertEqual(manifest["project"]["current_gate"], 7)
        self.assertEqual(manifest["schema_version"], "0.5.0")
        entities = manifest["structured_entities"]
        self.assertEqual(len(entities["rights_holders"]), 3)
        self.assertEqual(len(entities["authorization_records"]), 1)
        self.assertEqual(len(entities["cultural_element_cards"]), 2)
        self.assertEqual(len(entities["model_runs"]), 1)
        self.assertEqual(len(entities["expert_reviews"]), 3)
        self.assertEqual(len(entities["market_tests"]), 1)
        self.assertEqual(len(entities["revenue_distributions"]), 1)

    def test_v01_database_is_non_destructively_upgraded(self) -> None:
        legacy_db = Path(self.tmp.name) / "legacy.db"
        conn = sqlite3.connect(legacy_db)
        conn.execute(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, heritage_name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '', current_gate INTEGER NOT NULL DEFAULT -1,
                status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO projects VALUES ('legacy', 'Legacy', 'Synthetic', '', -1, 'active', 'x', 'x')"
        )
        conn.commit()
        conn.close()
        upgraded = HeritageGateEngine(legacy_db)
        project = upgraded.get_project("legacy")
        self.assertIn("governance_owner", project)
        self.assertIn("audit_takedown_ready", project)
        self.assertEqual(project["name"], "Legacy")


if __name__ == "__main__":
    unittest.main()
