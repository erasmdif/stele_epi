"""Test: confronto testimoni della stessa opera."""
import json, os, sys, sqlite3, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from stele_app.db import project
from stele_app import create_app, models

DB = "/tmp/test_wit.gpkg"


class WorkWitnessesTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        project.create_project(DB, with_demo=True, overwrite=True)
        cls.app = create_app(DB)
        cls.client = cls.app.test_client()
        cls.conn = sqlite3.connect(DB)
        cls.conn.row_factory = sqlite3.Row
        # Prendo un work con >=2 testimoni
        cls.work_id = cls.conn.execute("""
            SELECT w.id FROM work w
              JOIN text_document td ON td.work_id = w.id
             WHERE td.is_active = 1
             GROUP BY w.id HAVING COUNT(td.id) >= 2
             ORDER BY COUNT(td.id) DESC LIMIT 1
        """).fetchone()[0]

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    # ── Model: matrix + apparatus ─────────────────────────────────

    def test_witnesses_diff_returns_all_fields(self):
        data = models.analytics_work_witnesses_diff(
            self.conn, self.work_id, version_type="normalized")
        for k in ("witnesses", "matrix", "variants", "stats"):
            self.assertIn(k, data)

    def test_matrix_is_square_and_symmetric(self):
        data = models.analytics_work_witnesses_diff(
            self.conn, self.work_id, version_type="normalized")
        m = data["matrix"]
        n = len(m)
        self.assertGreater(n, 1)
        # square
        for row in m:
            self.assertEqual(len(row), n)
        # diagonal = 1.0
        for i in range(n):
            self.assertEqual(m[i][i], 1.0)
        # symmetric
        for i in range(n):
            for j in range(i+1, n):
                self.assertEqual(m[i][j], m[j][i])

    def test_similarity_in_range(self):
        data = models.analytics_work_witnesses_diff(
            self.conn, self.work_id, version_type="normalized")
        for row in data["matrix"]:
            for v in row:
                self.assertGreaterEqual(v, 0.0)
                self.assertLessEqual(v, 1.0)

    def test_apparatus_lists_variants(self):
        data = models.analytics_work_witnesses_diff(
            self.conn, self.work_id, version_type="normalized")
        # Deve trovare varianti (i testimoni sono raggruppati per formula
        # ma i frammenti hanno testo parziale, quindi ci saranno differenze)
        self.assertGreater(len(data["variants"]), 0)
        for v in data["variants"]:
            self.assertIn("line", v)
            self.assertIn("readings", v)
            self.assertGreater(len(v["readings"]), 1)  # varianza reale
            for r in v["readings"]:
                self.assertIn("reading", r)
                self.assertIn("witnesses", r)
                self.assertIn("count", r)

    def test_stats_are_valid(self):
        data = models.analytics_work_witnesses_diff(
            self.conn, self.work_id, version_type="normalized")
        s = data["stats"]
        self.assertGreaterEqual(s["n_witnesses"], 2)
        self.assertIsNotNone(s["avg_similarity"])
        self.assertLessEqual(s["min_similarity"], s["avg_similarity"])
        self.assertLessEqual(s["avg_similarity"], s["max_similarity"])

    def test_witnesses_diff_lt_2_witnesses_returns_message(self):
        # Creo un work senza testimoni
        new_id = models.create_work(self.conn, title="Empty Work")
        data = models.analytics_work_witnesses_diff(self.conn, new_id)
        self.assertIn("message", data)
        self.assertEqual(data["matrix"], [])

    # ── Model: pair diff ───────────────────────────────────────────

    def test_pair_diff_returns_aligned_lines(self):
        data = models.analytics_work_witnesses_diff(
            self.conn, self.work_id, version_type="normalized")
        w = data["witnesses"]
        a_id = w[0]["doc_id"]
        b_id = w[1]["doc_id"]
        p = models.analytics_work_witness_pair_diff(
            self.conn, self.work_id, a_id, b_id, version_type="normalized")
        self.assertIsNotNone(p)
        self.assertIn("lines", p)
        self.assertIn("summary", p)
        self.assertIn("global_similarity", p)

    def test_pair_diff_line_statuses_are_valid(self):
        data = models.analytics_work_witnesses_diff(
            self.conn, self.work_id, version_type="normalized")
        w = data["witnesses"]
        p = models.analytics_work_witness_pair_diff(
            self.conn, self.work_id, w[0]["doc_id"], w[1]["doc_id"])
        valid = {"equal", "variant", "conflict", "only_a", "only_b"}
        for ln in p["lines"]:
            self.assertIn(ln["status"], valid)
            self.assertIn("a", ln)
            self.assertIn("b", ln)
            self.assertIn("similarity", ln)

    def test_pair_diff_summary_matches_lines(self):
        data = models.analytics_work_witnesses_diff(
            self.conn, self.work_id, version_type="normalized")
        w = data["witnesses"]
        p = models.analytics_work_witness_pair_diff(
            self.conn, self.work_id, w[0]["doc_id"], w[1]["doc_id"])
        s = p["summary"]
        total = s["equal"] + s["variant"] + s["conflict"] + s["only_a"] + s["only_b"]
        self.assertEqual(total, s["total"])
        self.assertEqual(len(p["lines"]), s["total"])

    def test_pair_diff_same_witness_is_100pct(self):
        data = models.analytics_work_witnesses_diff(
            self.conn, self.work_id, version_type="normalized")
        w = data["witnesses"][0]
        p = models.analytics_work_witness_pair_diff(
            self.conn, self.work_id, w["doc_id"], w["doc_id"])
        self.assertEqual(p["global_similarity"], 1.0)
        for ln in p["lines"]:
            self.assertEqual(ln["status"], "equal")

    def test_pair_diff_nonexistent_doc(self):
        p = models.analytics_work_witness_pair_diff(
            self.conn, self.work_id, 99999, 99998)
        self.assertIsNone(p)

    # ── API endpoints ──────────────────────────────────────────────

    def test_api_works_with_witnesses(self):
        r = self.client.get("/api/analytics/works-with-witnesses")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertGreater(len(data), 0)
        for w in data:
            self.assertGreaterEqual(w["n_witnesses"], 2)

    def test_api_witnesses_diff(self):
        r = self.client.get(f"/api/analytics/works/{self.work_id}/witnesses-diff")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn("matrix", data)
        self.assertIn("variants", data)

    def test_api_witnesses_diff_with_version_type(self):
        r = self.client.get(
            f"/api/analytics/works/{self.work_id}/witnesses-diff"
            "?version_type=diplomatic_transcription")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data["version_type"], "diplomatic_transcription")

    def test_api_pair_diff(self):
        data = models.analytics_work_witnesses_diff(
            self.conn, self.work_id, version_type="normalized")
        w = data["witnesses"]
        r = self.client.get(
            f"/api/analytics/works/{self.work_id}/pair-diff"
            f"?a={w[0]['doc_id']}&b={w[1]['doc_id']}")
        self.assertEqual(r.status_code, 200)
        d = json.loads(r.data)
        self.assertIn("lines", d)

    def test_api_pair_diff_missing_params(self):
        r = self.client.get(
            f"/api/analytics/works/{self.work_id}/pair-diff")
        self.assertEqual(r.status_code, 400)

    def test_api_pair_diff_wrong_ids(self):
        r = self.client.get(
            f"/api/analytics/works/{self.work_id}/pair-diff?a=99999&b=99998")
        self.assertEqual(r.status_code, 404)

    # ── UI page ────────────────────────────────────────────────────

    def test_web_analytics_has_witnesses_tab(self):
        r = self.client.get("/analytics")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Work Witnesses", r.data)
        self.assertIn(b"witnesses", r.data)


if __name__ == "__main__":
    res = unittest.main(exit=False, verbosity=0)
    total = res.result.testsRun
    fail = len(res.result.failures) + len(res.result.errors)
    print(f"\n{total - fail} pass, {fail} fail")
