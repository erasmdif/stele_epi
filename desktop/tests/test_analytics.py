"""Test suite per la dashboard analitica."""
import json, os, sys, sqlite3, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from stele_app.db import project
from stele_app import create_app, models

DB = "/tmp/test_analytics.gpkg"

class AnalyticsTestCase(unittest.TestCase):

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

    # ── Model-level tests ──────────────────────────────────────────

    def test_semantic_search_returns_results(self):
        """Ricerca semantica su un termine con annotazioni."""
        # Prendi il primo termine annotato
        row = self.conn.execute("""
            SELECT at2.term_id FROM annotation_term at2 LIMIT 1
        """).fetchone()
        if row:
            results = models.analytics_semantic_search(self.conn, row[0])
            self.assertIsInstance(results, list)
            self.assertGreater(len(results), 0)
            self.assertIn("doc_id", results[0])
            self.assertIn("matched_term", results[0])

    def test_semantic_search_no_results(self):
        """Ricerca su termine non annotato → lista vuota."""
        results = models.analytics_semantic_search(self.conn, 999999)
        self.assertEqual(results, [])

    def test_semantic_search_with_hierarchy(self):
        """Ricerca su un termine genitore recupera annotazioni dei figli."""
        # Minerva IS_A Roman deity → cercare "Roman deity" deve trovare Minerva
        roman = self.conn.execute(
            "SELECT id FROM text_term WHERE preferred_label='Roman deity'"
        ).fetchone()
        minerva = self.conn.execute(
            "SELECT id FROM text_term WHERE preferred_label='Minerva'"
        ).fetchone()
        if roman and minerva:
            desc = models.descendants(self.conn, "text_term", roman[0])
            desc_ids = [d["id"] for d in desc]
            self.assertIn(minerva[0], desc_ids)

    def test_cooccurrence_version_scope(self):
        """Grafo co-occorrenze con scope version."""
        data = models.analytics_cooccurrence(self.conn, scope="version")
        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        self.assertIsInstance(data["nodes"], list)
        self.assertIsInstance(data["edges"], list)

    def test_cooccurrence_unit_scope(self):
        """Grafo co-occorrenze con scope unit."""
        data = models.analytics_cooccurrence(self.conn, scope="unit")
        self.assertIn("nodes", data)
        self.assertIn("edges", data)

    def test_cooccurrence_structure(self):
        """Verifica struttura nodi e archi."""
        data = models.analytics_cooccurrence(self.conn, scope="version")
        if data["nodes"]:
            n = data["nodes"][0]
            self.assertIn("id", n)
            self.assertIn("label", n)
            self.assertIn("total_annotations", n)
        if data["edges"]:
            e = data["edges"][0]
            self.assertIn("source", e)
            self.assertIn("target", e)
            self.assertIn("weight", e)

    def test_text_concept_matrix(self):
        """Matrice testi × concetti ha struttura corretta."""
        data = models.analytics_text_concept_matrix(self.conn)
        self.assertIn("columns", data)
        self.assertIn("rows", data)
        self.assertIsInstance(data["columns"], list)
        self.assertIsInstance(data["rows"], list)
        if data["rows"]:
            r = data["rows"][0]
            self.assertIn("doc_id", r)
            self.assertIn("siglum", r)
            self.assertIn("counts", r)

    def test_text_archaeology_cross(self):
        """Incrocio testo × archeologia ha struttura corretta."""
        data = models.analytics_text_archaeology_cross(self.conn)
        self.assertIn("columns", data)
        self.assertIn("rows", data)
        if data["rows"]:
            r = data["rows"][0]
            self.assertIn("category", r)
            self.assertIn("counts", r)

    # ── API endpoint tests ────────────────────────────────────────

    def test_api_terms_for_search(self):
        r = self.client.get("/api/analytics/terms-for-search")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn("preferred_label", data[0])

    def test_api_semantic_search_missing_param(self):
        r = self.client.get("/api/analytics/semantic-search")
        self.assertEqual(r.status_code, 400)

    def test_api_semantic_search_ok(self):
        row = self.conn.execute(
            "SELECT at2.term_id FROM annotation_term at2 LIMIT 1"
        ).fetchone()
        if row:
            r = self.client.get(f"/api/analytics/semantic-search?term_id={row[0]}")
            self.assertEqual(r.status_code, 200)
            data = json.loads(r.data)
            self.assertIsInstance(data, list)

    def test_api_cooccurrence(self):
        r = self.client.get("/api/analytics/cooccurrence?scope=version")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn("nodes", data)
        self.assertIn("edges", data)

    def test_api_text_concept_matrix(self):
        r = self.client.get("/api/analytics/text-concept-matrix")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn("columns", data)
        self.assertIn("rows", data)

    def test_api_text_archaeology_cross(self):
        r = self.client.get("/api/analytics/text-archaeology-cross")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn("columns", data)

    def test_web_analytics_page(self):
        """La pagina /analytics carica correttamente."""
        r = self.client.get("/analytics")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Analytics", r.data)
        self.assertIn(b"Semantic Search", r.data)
        self.assertIn(b"Co-occurrence", r.data)
        self.assertIn(b"Concept Timeline", r.data)

    def test_api_enums_archaeology(self):
        """L'endpoint enums serve i deposit_types per il filtro."""
        r = self.client.get("/api/enums/archaeology")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn("deposit_types", data)

if __name__ == "__main__":
    res = unittest.main(exit=False, verbosity=0)
    total = res.result.testsRun
    fail = len(res.result.failures) + len(res.result.errors)
    print(f"\n{total - fail} pass, {fail} fail")
