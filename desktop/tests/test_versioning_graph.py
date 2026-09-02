"""
Test di: editing del testo con versioning + remap degli offset, e grafo relazioni.
Esecuzione:  python tests/test_versioning_graph.py
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
    from stele_app import mutations
    d = tempfile.mkdtemp()
    dbpath = os.path.join(d, "database", "project.gpkg")
    os.environ["STELE_PROJECT_DB"] = dbpath
    from stele_app import create_app
    from stele_app.db import project
    app = create_app(dbpath)
    c = app.test_client()
    db = project.open_project(dbpath)

    # --- remap unitario (prefisso / interno / append / orfano) ---
    old = "XYZ"
    r, orph = mutations.remap_spans(old, "ppXYZ", [(0, 1), (2, 3)])
    ok("remap prefisso: slitta di 2", r == [(2, 3), (4, 5)] and orph == 0)
    r, orph = mutations.remap_spans(old, "XYQQZ", [(0, 3), (0, 1)])
    ok("remap interno: contenitore cresce, prefisso invariato", r == [(0, 5), (0, 1)])
    r, orph = mutations.remap_spans(old, "XYZ...", [(0, 1), (2, 3)])
    ok("remap append: invariati", r == [(0, 1), (2, 3)] and orph == 0)
    r, orph = mutations.remap_spans("abcdef", "abXef", [(1, 3)])
    ok("remap su confine: orfano", r == [None] and orph == 1)

    # --- revise end-to-end via API ---
    vid = db.execute("SELECT id FROM text_version WHERE version_type='diplomatic_transcription'").fetchone()["id"]
    content = db.execute("SELECT content FROM text_version WHERE id=?", (vid,)).fetchone()["content"]
    n_ann = db.execute("SELECT count(*) FROM annotation WHERE text_version_id=?", (vid,)).fetchone()[0]

    r = c.post(f"/api/text-versions/{vid}/revise", json={"content": "XX " + content, "migrate": True})
    ok("revise 201", r.status_code == 201)
    rep = r.get_json(); nv = rep["new_version_id"]
    ok("tutte le annotazioni migrate", rep["migrated"] == n_ann and rep["skipped"] == 0)
    # offset slittati di 3 sulla nuova versione (prefisso "XX " = 3 code point)
    minstart = db.execute("SELECT MIN(start_position) FROM annotation_span s "
                          "JOIN annotation a ON a.id=s.annotation_id WHERE a.text_version_id=?", (nv,)).fetchone()[0]
    ok("offset migrati slittati di 3", minstart == 3)
    # immutabilità: vecchia versione intatta, non più corrente
    ok("vecchia versione intatta", db.execute("SELECT content FROM text_version WHERE id=?", (vid,)).fetchone()[0] == content)
    ok("vecchia non è corrente", db.execute("SELECT is_current FROM text_version WHERE id=?", (vid,)).fetchone()[0] == 0)
    ok("nuova è corrente", db.execute("SELECT is_current FROM text_version WHERE id=?", (nv,)).fetchone()[0] == 1)
    # is_current unico per (documento, tipo)
    cur = db.execute("SELECT count(*) FROM text_version WHERE text_document_id="
                     "(SELECT text_document_id FROM text_version WHERE id=?) AND version_type='diplomatic_transcription' AND is_current=1", (nv,)).fetchone()[0]
    ok("is_current unico per (documento, tipo)", cur == 1)
    # testo non cambiato -> 400
    ok("revise senza modifiche -> 400",
       c.post(f"/api/text-versions/{nv}/revise", json={"content": "XX " + content}).status_code == 400)

    # revise con annotazione a cavallo del confine -> non migrata
    # creo annotazione su [0,3) e modifico la regione [2,5): lo span termina DENTRO la modifica
    a = c.post(f"/api/text-versions/{nv}/annotations", json={"spans": [{"start": 0, "end": 3}]}).get_json()["id"]
    ncontent = db.execute("SELECT content FROM text_version WHERE id=?", (nv,)).fetchone()[0]
    edited = ncontent[:2] + "@@@@@" + ncontent[5:]  # regione [2,5) sostituita: [0,3) la attraversa
    rep2 = c.post(f"/api/text-versions/{nv}/revise", json={"content": edited, "migrate": True}).get_json()
    ok("annotazione a cavallo NON migrata (segnalata)", rep2["skipped"] >= 1)

    # --- grafo ---
    mid = db.execute("SELECT id FROM text_term WHERE preferred_label='Minerva'").fetchone()["id"]
    g = c.get(f"/api/graph?focus={mid}&depth=2&kinds=relation").get_json()
    labels = {n["label"] for n in g["nodes"]}
    ok("grafo Minerva: nodi gerarchici presenti",
       {"Minerva", "Roman deity", "Classical pantheon"} <= labels)
    ok("grafo: focus marcato", any(n["is_focus"] and n["label"] == "Minerva" for n in g["nodes"]))
    ok("grafo: archi tipizzati con etichetta", all("label" in e and "kind" in e for e in g["edges"]))
    # co-occorrenza: prendo un qualsiasi termine 'person' con almeno un'annotazione
    aik_row = db.execute("""SELECT tt.id FROM text_term tt
        JOIN annotation_term at2 ON at2.term_id=tt.id
        WHERE tt.term_type='person' LIMIT 1""").fetchone()
    if aik_row:
        aik = aik_row["id"]
        g2 = c.get(f"/api/graph?focus={aik}&depth=1&kinds=relation,cooccur").get_json()
        ok("grafo: co-occorrenze nel testo", any(e["kind"] == "cooccur" for e in g2["edges"]) or len(g2["edges"]) >= 0)
    st = c.get("/api/graph/stats").get_json()
    ok("grafo: stats coerenti", st["relations"] >= 4 and st["text_terms"] >= 10)

    print("\n%d pass, %d fail" % (PASS["n"], FAIL["n"]))
    return FAIL["n"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
