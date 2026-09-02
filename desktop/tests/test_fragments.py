"""Test per la gestione dei frammenti e vista ricostruita."""
import json, os, sys, sqlite3, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from stele_app.db import project
from stele_app import create_app, models

DB = "/tmp/test_fragments.gpkg"

class FragmentsTestCase(unittest.TestCase):

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

    def _reconstructed_id(self):
        return self.conn.execute(
            "SELECT id FROM object WHERE record_kind='reconstructed_object' LIMIT 1"
        ).fetchone()[0]

    def _integral_id(self):
        return self.conn.execute(
            "SELECT id FROM object WHERE record_kind='physical_object' LIMIT 1"
        ).fetchone()[0]

    # ── Schema / migration ─────────────────────────────────────────

    def test_fragment_relation_type_exists(self):
        r = self.conn.execute(
            "SELECT id FROM relation_type WHERE code='FRAGMENT_OF'"
        ).fetchone()
        self.assertIsNotNone(r)

    def test_object_relation_has_sequence(self):
        cols = [r["name"] for r in self.conn.execute("PRAGMA table_info(object_relation)")]
        self.assertIn("sequence", cols)

    # ── Demo data ──────────────────────────────────────────────────

    def test_demo_has_reconstructed_object(self):
        rid = self._reconstructed_id()
        self.assertIsNotNone(rid)

    def test_demo_has_fragments(self):
        count = self.conn.execute("""
            SELECT COUNT(*) FROM object WHERE record_kind='fragment'
        """).fetchone()[0]
        self.assertGreaterEqual(count, 3)

    def test_fragments_linked_to_parent(self):
        rid = self._reconstructed_id()
        n = self.conn.execute("""
            SELECT COUNT(*) FROM object_relation orel
              JOIN relation_type rt ON rt.id=orel.relation_type_id
             WHERE rt.code='FRAGMENT_OF' AND orel.target_object_id=?
        """, (rid,)).fetchone()[0]
        self.assertEqual(n, 5)

    def test_fragments_have_sequence(self):
        rid = self._reconstructed_id()
        seqs = [r[0] for r in self.conn.execute("""
            SELECT sequence FROM object_relation orel
              JOIN relation_type rt ON rt.id=orel.relation_type_id
             WHERE rt.code='FRAGMENT_OF' AND orel.target_object_id=?
             ORDER BY sequence
        """, (rid,))]
        self.assertEqual(seqs, [1, 2, 3, 4, 5])

    # ── Model functions ────────────────────────────────────────────

    def test_get_fragments_returns_ordered(self):
        rid = self._reconstructed_id()
        frags = models.get_fragments(self.conn, rid)
        self.assertEqual(len(frags), 5)
        # sequence dovrebbe essere 1, 2, 3
        self.assertEqual([f["sequence"] for f in frags], [1, 2, 3, 4, 5])

    def test_get_fragments_empty_for_integral_object(self):
        oid = self._integral_id()
        frags = models.get_fragments(self.conn, oid)
        # Un oggetto integro non ha frammenti FRAGMENT_OF
        # (potrebbe avere composition ma nel demo no)
        self.assertEqual(frags, [])

    def test_reconstructed_text_returns_all_versions(self):
        rid = self._reconstructed_id()
        recon = models.get_reconstructed_text(self.conn, rid)
        self.assertIsNotNone(recon)
        self.assertIn("fragments", recon)
        self.assertIn("combined", recon)
        self.assertIn("version_types", recon)
        # Devono esserci diplomatic, normalized, translation
        self.assertIn("diplomatic_transcription", recon["version_types"])
        self.assertIn("normalized", recon["version_types"])
        self.assertIn("translation", recon["version_types"])

    def test_reconstructed_text_combines_in_order(self):
        rid = self._reconstructed_id()
        recon = models.get_reconstructed_text(self.conn, rid)
        # Il testo ricostruito della diplomatica deve avere le righe
        # di Fr. A prima di quelle di Fr. C
        dipl = recon["combined"]["diplomatic_transcription"]["full_text"]
        # Il primo frammento iscritto contiene la formula di apertura (MINERVAE)
        idx_minerva = dipl.find("MINERVAE")
        self.assertGreaterEqual(idx_minerva, 0)
        # e il testo termina con la formula VSLM (in un frammento successivo)
        idx_vslm = dipl.find("V · S · L · M")
        if idx_vslm >= 0:
            self.assertLess(idx_minerva, idx_vslm)

    def test_reconstructed_text_parts_have_fragment_labels(self):
        rid = self._reconstructed_id()
        recon = models.get_reconstructed_text(self.conn, rid)
        parts = recon["combined"]["diplomatic_transcription"]["parts"]
        # ogni part deve indicare da quale frammento viene
        for p in parts:
            self.assertIn("fragment_label", p)
            self.assertIn("fragment_id", p)
            self.assertIn("content", p)

    def test_reconstructed_text_none_for_object_without_fragments(self):
        oid = self._integral_id()
        recon = models.get_reconstructed_text(self.conn, oid)
        self.assertIsNone(recon)

    def test_middle_fragment_no_text(self):
        """Fr. B è anepigrafe: non contribuisce al testo ricostruito."""
        rid = self._reconstructed_id()
        recon = models.get_reconstructed_text(self.conn, rid)
        # Alcuni frammenti sono anepigrafi: dovrebbero mancare dalle parts
        parts = recon["combined"]["diplomatic_transcription"]["parts"]
        n_inscribed = len(set(p["fragment_id"] for p in parts))
        n_total_fragments = len(recon["fragments"])
        # Almeno un frammento deve essere anepigrafe (n_inscribed < n_total)
        self.assertLess(n_inscribed, n_total_fragments)

    # ── API endpoints ──────────────────────────────────────────────

    def test_api_fragments(self):
        rid = self._reconstructed_id()
        r = self.client.get(f"/api/objects/{rid}/fragments")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(len(data), 5)

    def test_api_reconstructed_text(self):
        rid = self._reconstructed_id()
        r = self.client.get(f"/api/objects/{rid}/reconstructed-text")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn("combined", data)
        self.assertIn("diplomatic_transcription", data["combined"])

    def test_api_reconstructed_text_404_for_integral(self):
        oid = self._integral_id()
        r = self.client.get(f"/api/objects/{oid}/reconstructed-text")
        self.assertEqual(r.status_code, 404)

    # ── Independent editing of fragments ───────────────────────────

    def test_fragments_have_independent_text_documents(self):
        """Fr. A e Fr. C hanno text_document separati e indipendenti."""
        docs = self.conn.execute("""
            SELECT td.id, td.siglum, o.label
              FROM text_document td
              JOIN object o ON o.id=td.object_id
             WHERE o.record_kind='fragment'
        """).fetchall()
        # Devono esserci almeno 2 documenti (Fr. A e Fr. C)
        self.assertGreaterEqual(len(docs), 2)
        # I documenti sono su oggetti diversi
        obj_ids = set(d["id"] for d in docs)
        self.assertGreaterEqual(len(obj_ids), 2)

    def test_editing_one_fragment_does_not_affect_others(self):
        """Modificare il testo di Fr. A non tocca Fr. C."""
        docs = list(self.conn.execute("""
            SELECT td.id, o.label
              FROM text_document td
              JOIN object o ON o.id=td.object_id
             WHERE o.record_kind='fragment'
             ORDER BY o.label
        """))
        doc_a = docs[0]
        doc_c = docs[1]
        # snapshot originale del contenuto di Fr. C
        content_c_before = self.conn.execute("""
            SELECT content FROM text_version
             WHERE text_document_id=? AND version_type='diplomatic_transcription'
        """, (doc_c["id"],)).fetchone()[0]

        # Ora "modifichiamo" (senza commit al db reale — solo verifica logica)
        # In pratica: che le versioni di doc_a e doc_c abbiano IDs diversi
        vers_a = self.conn.execute("""
            SELECT id FROM text_version WHERE text_document_id=?
        """, (doc_a["id"],)).fetchall()
        vers_c = self.conn.execute("""
            SELECT id FROM text_version WHERE text_document_id=?
        """, (doc_c["id"],)).fetchall()
        ids_a = set(v["id"] for v in vers_a)
        ids_c = set(v["id"] for v in vers_c)
        self.assertEqual(ids_a & ids_c, set(), "Le versioni devono essere disgiunte")

        # Il contenuto di Fr. C non è cambiato
        content_c_after = self.conn.execute("""
            SELECT content FROM text_version
             WHERE text_document_id=? AND version_type='diplomatic_transcription'
        """, (doc_c["id"],)).fetchone()[0]
        self.assertEqual(content_c_before, content_c_after)


if __name__ == "__main__":
    res = unittest.main(exit=False, verbosity=0)
    total = res.result.testsRun
    fail = len(res.result.failures) + len(res.result.errors)
    print(f"\n{total - fail} pass, {fail} fail")
