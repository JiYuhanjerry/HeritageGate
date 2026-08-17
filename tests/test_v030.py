from __future__ import annotations

import http.client
import json
import tempfile
import threading
import time
import unittest

import heritagegate
import zipfile
from pathlib import Path

from heritagegate.demo import run_structured_demo
from heritagegate.engine import HeritageGateEngine
from heritagegate.exporter import build_research_bundle, export_csv_directory
from heritagegate.web import HeritageGateHTTPServer, HeritageGateWebApp


class HeritageGateV030Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "v030.db"
        self.engine = HeritageGateEngine(self.db)
        self.manifest = run_structured_demo(self.engine, "demo-v030")
        self.project_id = "demo-v030"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_schema_version_is_v030(self) -> None:
        self.assertEqual(self.manifest["schema_version"], "0.5.0")

    def test_project_metadata_can_be_updated(self) -> None:
        updated = self.engine.update_project(
            self.project_id,
            name="Updated demo",
            heritage_name="Updated synthetic motif",
            description="Updated description",
        )
        self.assertEqual(updated["name"], "Updated demo")
        self.assertEqual(updated["description"], "Updated description")

    def test_rights_holder_can_be_edited(self) -> None:
        holder = self.engine.structured.list_entities(self.project_id, "rights-holder")[0]
        payload = {
            "id": holder["id"],
            "name": "Updated synthetic holder",
            "holder_type": holder["holder_type"],
            "authority_basis": holder["authority_basis"],
            "jurisdiction": holder["jurisdiction"],
            "contact_ref": holder["contact_ref"],
            "notes": "Edited through v0.3",
            "active": True,
        }
        updated = self.engine.structured.update_entity(
            "rights-holder", self.project_id, holder["id"], payload
        )
        self.assertEqual(updated["name"], "Updated synthetic holder")
        self.assertEqual(updated["notes"], "Edited through v0.3")

    def test_element_card_relationships_can_be_edited(self) -> None:
        card = self.engine.structured.list_entities(self.project_id, "element-card")[0]
        payload = dict(card)
        payload.pop("project_id")
        payload.pop("created_at")
        payload.pop("updated_at")
        payload["annotators"] = [
            {
                "rights_holder_id": item["rights_holder_id"],
                "annotation_role": item["annotation_role"],
            }
            for item in card["annotators"]
        ]
        payload["name"] = "Edited element card"
        updated = self.engine.structured.update_entity(
            "element-card", self.project_id, card["id"], payload
        )
        self.assertEqual(updated["name"], "Edited element card")
        self.assertGreaterEqual(len(updated["annotators"]), 1)

    def test_csv_export_contains_analysis_tables(self) -> None:
        output = self.root / "csv"
        metadata = export_csv_directory(self.engine, self.project_id, output)
        self.assertTrue((output / "manifest.json").exists())
        self.assertTrue((output / "gate_summary.csv").exists())
        self.assertTrue((output / "rights_holders.csv").exists())
        self.assertTrue((output / "data_dictionary.csv").exists())
        self.assertTrue((output / "SHA256SUMS.txt").exists())
        self.assertEqual(metadata["row_counts"]["rights_holders"], 3)

    def test_research_zip_is_portable(self) -> None:
        output = self.root / "bundle.zip"
        metadata = build_research_bundle(self.engine, self.project_id, output)
        self.assertTrue(output.exists())
        self.assertEqual(len(metadata["sha256"]), 64)
        with zipfile.ZipFile(output) as archive:
            names = archive.namelist()
        self.assertTrue(any(name.endswith("manifest.json") for name in names))
        self.assertTrue(any(name.endswith("market_tests.csv") for name in names))
        self.assertTrue(any(name.endswith("SHA256SUMS.txt") for name in names))

    def test_web_renderer_contains_dashboard_and_exports(self) -> None:
        app = HeritageGateWebApp(self.db)
        home = app.home()
        dashboard = app.project_page(self.project_id)
        self.assertIn("Research workflow dashboard", home)
        self.assertIn("Synthetic", home)
        self.assertIn("Gate 0–7 progress", dashboard)
        self.assertIn("Download research ZIP", dashboard)
        self.assertIn("Structured gate readiness", dashboard)

    def test_local_http_health_endpoint(self) -> None:
        app = HeritageGateWebApp(self.db)
        server = HeritageGateHTTPServer(("127.0.0.1", 0), app)
        thread = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        thread.start()
        host, port = server.server_address
        deadline = time.monotonic() + 15.0
        last_error: Exception | None = None
        try:
            # Use http.client directly so Windows/system proxy settings cannot
            # intercept a loopback-only health request. Retry briefly to absorb
            # thread-scheduling and endpoint-security delays on Windows.
            while time.monotonic() < deadline:
                connection = http.client.HTTPConnection(host, port, timeout=2.0)
                try:
                    connection.request("GET", "/health", headers={"Connection": "close"})
                    response = connection.getresponse()
                    payload = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(response.status, 200)
                    self.assertEqual(payload["status"], "ok")
                    self.assertEqual(payload["version"], heritagegate.__version__)
                    self.assertEqual(payload["schema_version"], "0.5.0")
                    break
                except (ConnectionError, OSError, TimeoutError, http.client.HTTPException) as exc:
                    last_error = exc
                    time.sleep(0.1)
                finally:
                    connection.close()
            else:
                self.fail(f"Local health endpoint did not respond before timeout: {last_error}")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
