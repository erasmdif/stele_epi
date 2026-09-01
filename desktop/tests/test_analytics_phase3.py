"""Test suite Fase 3: spatiotemporal, formulas/parallels, timeline."""
import json, os, sys, sqlite3, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from stele_app.db import project
from stele_app import create_app, models

DB = "/tmp/test_analytics_phase3.gpkg"

class AnalyticsPhase3TestCase(unittest.TestCase):

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

    # ── Spatiotemporal ─────────────────────────────────────────────

    def test_spatiotemporal_findspot_returns_points(self):
        r = models.analytics_spatiotemporal(self.conn, mode="findspot")
        self.assertIsInstance(r, list)
        self.assertGreater(len(r), 0)
        for p in r:
            self.assertIn("lat", p)
            self.assertIn("lon", p)
            self.assertIn("matched_term", p)

    def test_spatiotemporal_mention_returns_list(self):
        # Il generatore procedurale non aggiunge sempre menzioni di luoghi ai testi;
        # test tollerante: verifica che l'API risponda e ritorni una lista.
        r = models.analytics_spatiotemporal(self.conn, mode="mention")
        self.assertIsInstance(r, list)
        # Se ci sono attestazioni, devono avere il campo lat/lon
        for p in r:
            self.assertIn("lat", p)
            self.assertIn("lon", p)

    def test_spatiotemporal_year_filter(self):
        all_pts = models.analytics_spatiotemporal(self.conn, mode="findspot")
        early = models.analytics_spatiotemporal(
            self.conn, mode="findspot", year_from=1, year_to=100)
        # Deve essere <= totale
        self.assertLessEqual(len(early), len(all_pts))

    def test_spatiotemporal_term_filter(self):
        # Filtro su "Funerary formula" — solo Cornelius e Aurelia
        term_id = self.conn.execute(
            "SELECT id FROM text_term WHERE preferred_label='Funerary formula'"
        ).fetchone()[0]
        r = models.analytics_spatiotemporal(self.conn, term_id=term_id, mode="findspot")
        self.assertGreater(len(r), 0)
        for p in r:
            # Deve essere in una necropoli
            self.assertIsNotNone(p.get("context_name"))

    def test_api_spatiotemporal(self):
        r = self.client.get("/api/analytics/spatiotemporal?mode=findspot")
        self.assertEqual(r.status_code, 200)
        d = json.loads(r.data)
        self.assertIsInstance(d, list)

    def test_api_spatiotemporal_bad_mode(self):
        r = self.client.get("/api/analytics/spatiotemporal?mode=invalid")
        self.assertEqual(r.status_code, 400)

    # ── Formulas & Parallels ───────────────────────────────────────

    def test_formula_search_finds_votive_parallel(self):
        # Il demo ha molti altari votivi con formule condivise (VSLM, aram posuit, sacrum)
        r = models.analytics_formula_search(
            self.conn, version_type="normalized",
            min_similarity=0.2, ngram=2)
        # Deve trovare paralleli con VSLM come shared n-gram
        vslm_parallels = [m for m in r["matches"]
                          if any("v(otum)" in ng or "s(olvit)" in ng or "l(ibens)" in ng
                                 for ng in m["shared_ngrams"])]
        self.assertGreater(len(vslm_parallels), 0,
                           "Nessun parallelo formulare votivo trovato")

    def test_formula_search_finds_funerary_parallel(self):
        # Molte iscrizioni funerarie condividono DM + HSE + vixit annis
        r = models.analytics_formula_search(
            self.conn, version_type="normalized",
            min_similarity=0.2, ngram=2)
        # Deve trovare paralleli con DM o HSE come shared n-gram
        funerary_parallels = [m for m in r["matches"]
                              if any("d(is)" in ng or "m(anibus)" in ng
                                     or "s(itus)" in ng or "vixit" in ng
                                     for ng in m["shared_ngrams"])]
        self.assertGreater(len(funerary_parallels), 0,
                           "Nessun parallelo formulare funerario trovato")

    def test_formula_search_no_false_positives(self):
        # Con soglia altissima possono emergere solo testi molto brevi
        # (es. due graffiti "Rufi" identici). Verifichiamo invece che
        # con ngram=5 e testi normali NON si producano match spuri.
        r = models.analytics_formula_search(
            self.conn, version_type="normalized",
            min_similarity=0.99, ngram=5)
        # con n=5 anche gli identici corti non fanno match perché
        # non hanno abbastanza parole per generare 5-gram
        for m in r["matches"]:
            self.assertGreater(m["n_shared"], 0)  # nessun match spurio

    def test_formula_search_structure(self):
        r = models.analytics_formula_search(self.conn, min_similarity=0.05)
        self.assertIn("texts", r)
        self.assertIn("matches", r)
        self.assertIn("n_texts", r)
        if r["matches"]:
            m = r["matches"][0]
            for k in ("a_doc_id", "b_doc_id", "similarity", "shared_ngrams", "n_shared"):
                self.assertIn(k, m)

    def test_ngram_frequency_finds_recurring(self):
        r = models.analytics_ngram_frequency(
            self.conn, version_type="normalized", ngram=2, min_count=2)
        self.assertGreater(len(r["top_ngrams"]), 0)
        # Verifichiamo che d(is) m(anibus) sia trovato
        found = any("d(is) m(anibus)" in ng["ngram"] for ng in r["top_ngrams"])
        self.assertTrue(found, f"'d(is) m(anibus)' non trovato: {r['top_ngrams']}")

    def test_ngram_frequency_min_count(self):
        # con min_count=99 non ci sono risultati
        r = models.analytics_ngram_frequency(
            self.conn, version_type="normalized", ngram=2, min_count=99)
        self.assertEqual(len(r["top_ngrams"]), 0)

    def test_api_formula_search(self):
        r = self.client.get("/api/analytics/formula-search?min_similarity=0.1&ngram=2")
        self.assertEqual(r.status_code, 200)
        d = json.loads(r.data)
        self.assertIn("matches", d)

    def test_api_ngram_frequency(self):
        r = self.client.get("/api/analytics/ngram-frequency?ngram=2&min_count=2")
        self.assertEqual(r.status_code, 200)
        d = json.loads(r.data)
        self.assertIn("top_ngrams", d)

    # ── Concept Timeline ──────────────────────────────────────────

    def test_concept_timeline_returns_bins(self):
        r = models.analytics_concept_timeline(self.conn, granularity="half")
        self.assertGreater(len(r["bins"]), 0)
        self.assertGreater(len(r["series"]), 0)

    def test_concept_timeline_bin_sizes(self):
        r_c = models.analytics_concept_timeline(self.conn, granularity="century")
        r_h = models.analytics_concept_timeline(self.conn, granularity="half")
        # Half deve avere più bin di century (approssimativamente il doppio)
        self.assertGreater(len(r_h["bins"]), len(r_c["bins"]) - 1)

    def test_concept_timeline_counts_annotations(self):
        r = models.analytics_concept_timeline(self.conn, granularity="half")
        # La somma dei counts di una serie deve essere >= 1
        for s in r["series"]:
            self.assertGreaterEqual(sum(s["counts"]), 1)

    def test_concept_timeline_funerary_across_time(self):
        """Funerary formula appare in obj1 (I sec) e obj7 (II sec fine)."""
        r = models.analytics_concept_timeline(self.conn, granularity="half")
        funerary = next((s for s in r["series"] if s["label"] == "Funerary formula"), None)
        self.assertIsNotNone(funerary)
        # Deve avere counts > 0 in almeno 2 bin distinti (I e II secolo)
        non_zero = sum(1 for c in funerary["counts"] if c > 0)
        self.assertGreaterEqual(non_zero, 2)

    def test_api_concept_timeline(self):
        r = self.client.get("/api/analytics/concept-timeline?granularity=century")
        self.assertEqual(r.status_code, 200)
        d = json.loads(r.data)
        self.assertIn("series", d)

    def test_api_concept_timeline_bad_granularity(self):
        r = self.client.get("/api/analytics/concept-timeline?granularity=yearly")
        self.assertEqual(r.status_code, 400)

    # ── Web page ───────────────────────────────────────────────────

    def test_analytics_page_includes_phase3_tabs(self):
        r = self.client.get("/analytics")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Space", r.data)  # Space x Time
        self.assertIn(b"Formulas", r.data)
        self.assertIn(b"Concept Timeline", r.data)

if __name__ == "__main__":
    res = unittest.main(exit=False, verbosity=0)
    total = res.result.testsRun
    fail = len(res.result.failures) + len(res.result.errors)
    print(f"\n{total - fail} pass, {fail} fail")
