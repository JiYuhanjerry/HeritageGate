from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from heritagegate.demo import GATE_PAYLOADS
from heritagegate.engine import HeritageGateEngine, WorkflowStateError
from heritagegate.validators import GateValidationError


class HeritageGateWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.db"
        self.engine = HeritageGateEngine(self.db)
        self.project_id = "test-project"
        self.engine.create_project(
            "Test project", "Synthetic motif", project_id=self.project_id
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_happy_path_reaches_gate7(self) -> None:
        for gate, payload in enumerate(GATE_PAYLOADS):
            state = self.engine.pass_gate(self.project_id, gate, payload)
        self.assertEqual(state["current_gate"], 7)
        self.assertEqual(state["status"], "completed")
        self.assertEqual(len(self.engine.gate_records(self.project_id)), 8)

    def test_gate_order_is_enforced(self) -> None:
        with self.assertRaises(WorkflowStateError):
            self.engine.pass_gate(self.project_id, 1, GATE_PAYLOADS[1])

    def test_restricted_gate0_cannot_pass(self) -> None:
        payload = dict(GATE_PAYLOADS[0])
        payload["permission_status"] = "restricted"
        with self.assertRaises(GateValidationError):
            self.engine.pass_gate(self.project_id, 0, payload)

    def test_gate4_requires_provenance(self) -> None:
        for gate in range(4):
            self.engine.pass_gate(self.project_id, gate, GATE_PAYLOADS[gate])
        payload = dict(GATE_PAYLOADS[4])
        payload["provenance_enabled"] = False
        with self.assertRaises(GateValidationError):
            self.engine.pass_gate(self.project_id, 4, payload)

    def test_failure_can_return_to_earlier_gate(self) -> None:
        for gate in range(5):
            self.engine.pass_gate(self.project_id, gate, GATE_PAYLOADS[gate])
        state = self.engine.record_failure(
            self.project_id,
            gate=5,
            payload={"reason": "Cultural review requested re-annotation"},
            feedback_target=3,
        )
        self.assertEqual(state["current_gate"], 3)
        self.assertEqual(self.engine.audit_trail(self.project_id)[-1]["event_type"], "gate_failed")


if __name__ == "__main__":
    unittest.main()
