"""Test per la gestione dei work (opere intellettuali astratte)."""
import json, os, sys, sqlite3, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from stele_app.db import project
from stele_app import create_app, models

DB = "/tmp/test_works.gpkg"


class WorksTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        project.create_project(DB, with_demo=True, overwrite=True)
        cls.app = create_app(DB)
        cls.client = cls.app.test_client()
        cls.conn = sqlite3.connect(DB)
        cls.conn.row_factory = sqlite3.Row

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    # ── Schema ─────────────────────────────────────────────────────

    def test_work_table_exists(self):
        r = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='work'"
        ).fetchone()
        self.assertIsNotNone(r)

    def test_text_document_has_work_id(self):
        cols = [r["name"] for r in self.conn.execute("PRAGMA table_info(text_document)")]
        self.assertIn("work_id", cols)
        self.assertIn("witness_siglum", cols)

    # ── Demo data ──────────────────────────────────────────────────

    def test_demo_has_works(self):
        n = self.conn.execute("SELECT COUNT(*) FROM work").fetchone()[0]
        self.assertGreaterEqual(n, 5)

    def test_demo_has_linked_witnesses(self):
        n = self.conn.execute(
            "SELECT COUNT(*) FROM text_document WHERE work_id IS NOT NULL"
        ).fetchone()[0]
        # Almeno 20 testimoni collegati
        self.assertGreaterEqual(n, 20)

    def test_iuppiter_work_has_multiple_witnesses(self):
        w = self.conn.execute(
            "SELECT id FROM work WHERE title LIKE '%Iuppiter%'"
        ).fetchone()
        self.assertIsNotNone(w)
        n = self.conn.execute(
            "SELECT COUNT(*) FROM text_document WHERE work_id = ?", (w[0],)
        ).fetchone()[0]
        self.assertGreater(n, 1, "Iuppiter deve avere >1 testimoni")

    def test_witnesses_have_siglum(self):
        """I testimoni collegati al demo devono avere un witness_siglum."""
        rows = self.conn.execute("""
            SELECT witness_siglum FROM text_document
             WHERE work_id IS NOT NULL AND witness_siglum IS NULL
        """).fetchall()
        self.assertEqual(len(rows), 0, "Ogni testimone deve avere witness_siglum")

    # ── Models ─────────────────────────────────────────────────────

    def test_list_works(self):
        works = models.list_works(self.conn)
        self.assertGreater(len(works), 0)
        for w in works:
            self.assertIn("title", w)
            self.assertIn("witness_count", w)

    def test_get_work_returns_witnesses(self):
        w_id = self.conn.execute(
            "SELECT id FROM work WHERE title LIKE '%Iuppiter%'"
        ).fetchone()[0]
        w = models.get_work(self.conn, w_id)
        self.assertIsNotNone(w)
        self.assertIn("witnesses", w)
        self.assertGreater(len(w["witnesses"]), 0)
        for wt in w["witnesses"]:
            self.assertIn("id", wt)
            self.assertIn("n_versions", wt)

    def test_get_work_nonexistent(self):
        w = models.get_work(self.conn, 99999)
        self.assertIsNone(w)

    def test_create_work(self):
        new_id = models.create_work(
            self.conn,
            title="Test Work",
            work_type="test",
            language="la",
            description="Solo per test")
        self.assertIsNotNone(new_id)
        w = models.get_work(self.conn, new_id)
        self.assertEqual(w["title"], "Test Work")

    def test_update_work(self):
        new_id = models.create_work(
            self.conn, title="Update Me", work_type="test")
        models.update_work(self.conn, new_id,
                            title="Updated Title", author="New Author")
        w = models.get_work(self.conn, new_id)
        self.assertEqual(w["title"], "Updated Title")
        self.assertEqual(w["author"], "New Author")

    def test_link_document_to_work(self):
        # Prendo un document senza work
        doc = self.conn.execute("""
            SELECT id FROM text_document WHERE work_id IS NULL LIMIT 1
        """).fetchone()
        self.assertIsNotNone(doc)
        # Prendo un work
        w_id = self.conn.execute("SELECT id FROM work LIMIT 1").fetchone()[0]
        # Collego
        models.link_document_to_work(self.conn, doc[0], w_id, "TestSig")
        # Verifico
        r = self.conn.execute(
            "SELECT work_id, witness_siglum FROM text_document WHERE id = ?", (doc[0],)
        ).fetchone()
        self.assertEqual(r["work_id"], w_id)
        self.assertEqual(r["witness_siglum"], "TestSig")
        # Scollego
        models.link_document_to_work(self.conn, doc[0], None, None)
        r = self.conn.execute(
            "SELECT work_id FROM text_document WHERE id = ?", (doc[0],)
        ).fetchone()
        self.assertIsNone(r["work_id"])

    def test_documents_without_work(self):
        docs = models.documents_without_work(self.conn, limit=50)
        self.assertIsInstance(docs, list)
        # Alcuni document devono essere senza work
        self.assertGreater(len(docs), 0)

    # ── API endpoints ──────────────────────────────────────────────

    def test_api_works_list(self):
        r = self.client.get("/api/works")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_api_work_detail(self):
        w_id = self.conn.execute("SELECT id FROM work LIMIT 1").fetchone()[0]
        r = self.client.get(f"/api/works/{w_id}")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn("witnesses", data)

    def test_api_work_detail_404(self):
        r = self.client.get("/api/works/99999")
        self.assertEqual(r.status_code, 404)

    def test_api_create_work(self):
        r = self.client.post("/api/works", json={
            "title": "API Created Work",
            "work_type": "formula",
            "language": "la"
        })
        self.assertEqual(r.status_code, 201)
        data = json.loads(r.data)
        self.assertIn("id", data)

    def test_api_create_work_missing_title(self):
        r = self.client.post("/api/works", json={"work_type": "formula"})
        self.assertEqual(r.status_code, 400)

    def test_api_update_work(self):
        # Creo un work e poi lo aggiorno via API
        new_id = models.create_work(self.conn, title="Original")
        r = self.client.patch(f"/api/works/{new_id}", json={
            "title": "Patched via API",
            "author": "Test Author"
        })
        self.assertEqual(r.status_code, 200)
        w = models.get_work(self.conn, new_id)
        self.assertEqual(w["title"], "Patched via API")

    def test_api_link_document(self):
        # Trovo un doc libero e un work
        doc = self.conn.execute(
            "SELECT id FROM text_document WHERE work_id IS NULL LIMIT 1"
        ).fetchone()
        w = self.conn.execute("SELECT id FROM work LIMIT 1").fetchone()
        r = self.client.post(f"/api/documents/{doc[0]}/link-work", json={
            "work_id": w[0], "witness_siglum": "ApiTest"
        })
        self.assertEqual(r.status_code, 200)
        row = self.conn.execute(
            "SELECT work_id, witness_siglum FROM text_document WHERE id=?", (doc[0],)
        ).fetchone()
        self.assertEqual(row["work_id"], w[0])
        self.assertEqual(row["witness_siglum"], "ApiTest")

    def test_api_documents_without_work(self):
        r = self.client.get("/api/documents/without-work")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIsInstance(data, list)

    # ── Web pages ──────────────────────────────────────────────────

    def test_web_works_page(self):
        r = self.client.get("/works")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Works", r.data)
        self.assertIn(b"witnesses", r.data)

    def test_web_work_detail_page(self):
        w_id = self.conn.execute("SELECT id FROM work LIMIT 1").fetchone()[0]
        r = self.client.get(f"/works/{w_id}")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Witnesses", r.data)

    def test_web_work_detail_404(self):
        r = self.client.get("/works/99999")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    res = unittest.main(exit=False, verbosity=0)
    total = res.result.testsRun
    fail = len(res.result.failures) + len(res.result.errors)
    print(f"\n{total - fail} pass, {fail} fail")
