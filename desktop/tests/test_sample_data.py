import os
import tempfile
import unittest

from stele_app import create_app
from stele_app.db import project


class SampleDataLifecycleTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, "database", "project.gpkg")
        self.app = create_app(self.db_path)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_dashboard_discloses_ai_generated_mock_data(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"AI-generated mock data", response.data)
        self.assertIn(b"Delete all sample data", response.data)

    def test_removal_requires_exact_confirmation(self):
        response = self.client.post(
            "/api/project/remove-sample-data",
            json={"confirmation": "delete"},
        )
        self.assertEqual(response.status_code, 400)
        conn = project.open_project(self.db_path)
        try:
            self.assertTrue(project.has_sample_data(conn))
        finally:
            conn.close()

    def test_removal_creates_backup_and_clean_project(self):
        response = self.client.post(
            "/api/project/remove-sample-data",
            json={"confirmation": "REMOVE SAMPLE DATA"},
        )
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertTrue(os.path.isfile(result["backup_path"]))

        conn = project.open_project(self.db_path)
        try:
            self.assertFalse(project.has_sample_data(conn))
            self.assertEqual(conn.execute("SELECT count(*) FROM object").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT count(*) FROM text_document").fetchone()[0], 0)
            self.assertGreater(conn.execute("SELECT count(*) FROM relation_type").fetchone()[0], 0)
        finally:
            conn.close()

        dashboard = self.client.get("/")
        self.assertNotIn(b"AI-generated mock data", dashboard.data)
        self.assertNotIn(b"Delete all sample data", dashboard.data)


if __name__ == "__main__":
    unittest.main()
