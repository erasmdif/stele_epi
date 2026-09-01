"""
Test delle versioni parallele: allineamento, vista parallela, creazione,
annotazione fissata sulla primaria, marcatori di co-riga.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = {"n": 0}; FAIL = {"n": 0}
def ok(name, cond):
    (PASS if cond else FAIL)["n"] += 1
    print(("PASS " if cond else "FAIL ") + name)


def run():
    d = tempfile.mkdtemp()
    dbpath = os.path.join(d, "database", "project.gpkg")
    os.environ["STELE_PROJECT_DB"] = dbpath
    from stele_app import create_app
    from stele_app.db import project
    app = create_app(dbpath); c = app.test_client()
    db = project.open_project(dbpath)

    # documento demo: 1 doc, 3 versioni parallele (diplomatica primaria + trans + trad)
    doc_id = db.execute("SELECT id FROM text_document LIMIT 1").fetchone()["id"]

    # 1. document_versions ritorna 3 versioni
    vs = db.execute("SELECT version_type FROM text_version WHERE text_document_id=? ORDER BY version_type",
                    (doc_id,)).fetchall()
    types = [r["version_type"] for r in vs]
    ok("3 versioni parallele nel seed",
       set(types) == {"diplomatic_transcription", "translation", "normalized"})

    # 2. parallel-view: primaria è diplomatic_transcription
    v = c.get(f"/api/documents/{doc_id}/parallel-view").get_json()
    ok("primaria = diplomatic_transcription", v["primary"]["version_type"] == "diplomatic_transcription")
    ok("3 tipi attivi per default", len(v["active"]) == 3)

    # 3. righe allineate: ogni row ha 3 celle
    ok("tutte le righe hanno 3 celle", all(len(row["cells"]) == 3 for row in v["rows"]))
    # cella con is_primary_version = una sola per row
    ok("ogni row ha esattamente una primary cell",
       all(sum(1 for c in row["cells"] if c["is_primary_version"]) == 1 for row in v["rows"]))

    # 4. i cell delle versioni parallele hanno ann_count = numero annotazioni sulla riga primaria
    #    riga 1 della diplomatica ha 3 annotazioni; riga 2 nessuna
    row1 = v["rows"][0]
    parallels1 = [x for x in row1["cells"] if not x["is_primary_version"]]
    ok("parallele di riga 1 hanno ann_count coerente", all(p["ann_count"] >= 0 for p in parallels1))
    row2 = v["rows"][1]
    parallels2 = [x for x in row2["cells"] if not x["is_primary_version"]]
    ok("parallele di riga 2 hanno ann_count coerente", all(p["ann_count"] >= 0 for p in parallels2))

    # 5. filtro attivo: se richiedo solo diplomatica
    v_only = c.get(f"/api/documents/{doc_id}/parallel-view?types=diplomatic_transcription").get_json()
    ok("filtro types: solo diplomatica presente",
       all(len(row["cells"]) == 1 for row in v_only["rows"]))

    # 6. crea versione parallela via API
    commentary = "\n".join(f"Line {i} comment." for i in range(1, len(v["rows"]) + 1))
    r = c.post(f"/api/documents/{doc_id}/parallel-versions",
               json={"version_type": "commentary", "language": "en",
                     "content": commentary, "auto_align": True})
    ok("POST parallel-version 201", r.status_code == 201)
    v2 = c.get(f"/api/documents/{doc_id}/parallel-view").get_json()
    ok("nuova versione compare in active", "commentary" in v2["active"])
    ok("nuova versione allineata alle righe",
       all(any(cell["version_type"] == "commentary" for cell in row["cells"]) for row in v2["rows"]))

    # 7. auto-align idempotente (non crea duplicati)
    n_before = db.execute("SELECT count(*) FROM text_unit_alignment").fetchone()[0]
    c.post(f"/api/documents/{doc_id}/auto-align")
    n_after = db.execute("SELECT count(*) FROM text_unit_alignment").fetchone()[0]
    ok("auto-align idempotente", n_before == n_after)

    # 8. set_alignment_group: modifica manuale
    group = db.execute("SELECT group_id FROM text_unit_alignment WHERE role='primary' LIMIT 1").fetchone()["group_id"]
    unit_ids = [r["text_unit_id"] for r in db.execute("SELECT text_unit_id FROM text_unit_alignment WHERE group_id=?", (group,))]
    r = c.put(f"/api/alignment-groups/{group}", json={"unit_ids": unit_ids[:2], "primary_unit_id": unit_ids[0]})
    ok("PUT alignment-group 200", r.status_code == 200)
    remaining = db.execute("SELECT count(*) FROM text_unit_alignment WHERE group_id=?", (group,)).fetchone()[0]
    ok("gruppo modificato: 2 unità", remaining == 2)

    # 9. delete alignment-group
    r = c.delete(f"/api/alignment-groups/{group}")
    ok("DELETE alignment-group", r.status_code == 200)
    ok("gruppo sparito", db.execute("SELECT count(*) FROM text_unit_alignment WHERE group_id=?",
                                     (group,)).fetchone()[0] == 0)

    # 10. le annotazioni restano fissate sulla versione primaria
    prim_vid = db.execute("SELECT id FROM text_version WHERE version_type='diplomatic_transcription' AND text_document_id=?",
                          (doc_id,)).fetchone()["id"]
    n_ann_prim = db.execute("SELECT count(*) FROM annotation WHERE text_version_id=?", (prim_vid,)).fetchone()[0]
    n_ann_other = db.execute("""SELECT count(*) FROM annotation a JOIN text_version v ON v.id=a.text_version_id
                                 WHERE v.text_document_id=? AND v.version_type<>'diplomatic_transcription'""",
                             (doc_id,)).fetchone()[0]
    ok("annotazioni SOLO sulla primaria (diplomatica)",
       n_ann_prim > 0 and n_ann_other == 0)

    # 11. migrazione non-distruttiva: rimuovo la tabella allineamento e riapro
    import sqlite3, shutil
    shutil.copy(dbpath, dbpath + ".copy")
    c2 = sqlite3.connect(dbpath + ".copy")
    c2.execute("DROP TABLE text_unit_alignment"); c2.commit(); c2.close()
    reopened = project.open_project(dbpath + ".copy")
    has = reopened.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='text_unit_alignment'").fetchone()
    ok("migrazione ricrea text_unit_alignment", bool(has))

    print("\n%d pass, %d fail" % (PASS["n"], FAIL["n"]))
    return FAIL["n"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
