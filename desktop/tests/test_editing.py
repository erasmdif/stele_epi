"""
Test del flusso di EDITING dell'annotazione via API (ciò che fa il frontend):
creazione da selezione, validazioni, assegnazione/creazione termini, span
discontinui, geocoding, rete semantica con anti-ciclo, patch, delete.
Esecuzione:  python tests/test_editing.py
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
    app = create_app(dbpath)
    c = app.test_client()
    db = project.open_project(dbpath)
    vid = db.execute("SELECT id FROM text_version WHERE version_type='transliteration'").fetchone()["id"]
    content = db.execute("SELECT content FROM text_version WHERE id=?", (vid,)).fetchone()["content"]
    clen = len(list(content))

    # crea annotazione da "selezione" [0,4)
    r = c.post(f"/api/text-versions/{vid}/annotations",
               json={"annotation_type": "editorial", "note": "n1", "spans": [{"start": 0, "end": 4}]})
    ok("create 201", r.status_code == 201)
    aid = r.get_json()["id"]

    # validazioni
    ok("span oltre lunghezza -> 400",
       c.post(f"/api/text-versions/{vid}/annotations", json={"spans": [{"start": 0, "end": clen + 1}]}).status_code == 400)
    ok("span zero -> 400",
       c.post(f"/api/text-versions/{vid}/annotations", json={"spans": [{"start": 2, "end": 2}]}).status_code == 400)
    ok("nessuno span -> 400",
       c.post(f"/api/text-versions/{vid}/annotations", json={"spans": []}).status_code == 400)

    # crea termine place e collega
    tid = c.post("/api/text-terms", json={"term_type": "place", "preferred_label": "Tebe"}).get_json()["id"]
    ok("add term 200", c.post(f"/api/annotations/{aid}/terms", json={"term_id": tid}).status_code == 200)
    # duplicato stesso ruolo -> 400
    ok("term duplicato -> 400", c.post(f"/api/annotations/{aid}/terms", json={"term_id": tid}).status_code == 400)

    # annotations JSON riflette termine
    anns = c.get(f"/api/text-versions/{vid}/annotations").get_json()["annotations"]
    a = [x for x in anns if x["id"] == aid][0]
    ok("annotazione ha 1 termine", len(a["terms"]) == 1 and a["terms"][0]["preferred_label"] == "Tebe")

    # geocoding: place ok, non-place -> 400
    ok("set place su place 200", c.post(f"/api/text-terms/{tid}/place", json={"lat": 38.32, "lon": 23.31}).status_code == 200)
    non_place = db.execute("SELECT id FROM text_term WHERE term_type<>'place' LIMIT 1").fetchone()["id"]
    ok("set place su non-place -> 400", c.post(f"/api/text-terms/{non_place}/place", json={"lat": 1, "lon": 2}).status_code == 400)
    # ora la versione ha un luogo
    places = c.get(f"/api/text-versions/{vid}/annotations").get_json()["places"]
    ok("place compare nella mappa", any(p["label"] == "Tebe" for p in places))

    # span discontinuo: aggiungo [5,8)
    ok("set spans discontinui 200",
       c.put(f"/api/annotations/{aid}/spans", json={"spans": [{"start": 0, "end": 4}, {"start": 5, "end": 8}]}).status_code == 200)
    a = [x for x in c.get(f"/api/text-versions/{vid}/annotations").get_json()["annotations"] if x["id"] == aid][0]
    ok("annotazione ora ha 2 span", len(a["spans"]) == 2)

    # rete semantica + anti-ciclo
    cid = c.post("/api/text-terms", json={"term_type": "concept", "preferred_label": "Città beotica"}).get_json()["id"]
    ok("relazione IS_A 200", c.post("/api/text-term-relations", json={"source_id": tid, "target_id": cid, "relation_code": "IS_A"}).status_code == 200)
    ok("relazione ciclica -> 400", c.post("/api/text-term-relations", json={"source_id": cid, "target_id": tid, "relation_code": "IS_A"}).status_code == 400)
    lin = c.get(f"/api/vocab/text_term/{tid}/lineage").get_json()
    ok("lineage riflette la nuova relazione", any(x["preferred_label"] == "Città beotica" for x in lin["ancestors"]))

    # patch
    ok("patch 200", c.patch(f"/api/annotations/{aid}", json={"status": "proposed", "note": "n2"}).status_code == 200)
    a = [x for x in c.get(f"/api/text-versions/{vid}/annotations").get_json()["annotations"] if x["id"] == aid][0]
    ok("patch applicata", a["status"] == "proposed" and a["note"] == "n2")

    # TEI aggiornato e ben formato
    tei = c.get(f"/api/text-versions/{vid}/tei").get_data(as_text=True)
    import xml.dom.minidom as m
    wf = True
    try: m.parseString(tei)
    except Exception: wf = False
    ok("TEI ben formato dopo editing", wf and "#char=0,4" in tei and "#char=5,8" in tei)

    # change_log popolato
    ok("audit change_log popolato", db.execute("SELECT count(*) FROM change_log").fetchone()[0] >= 2)

    # rimuovi termine e elimina annotazione
    ok("remove term 200", c.delete(f"/api/annotations/{aid}/terms/{tid}").status_code == 200)
    ok("delete annotazione 200", c.delete(f"/api/annotations/{aid}").status_code == 200)
    gone = db.execute("SELECT count(*) FROM annotation WHERE id=?", (aid,)).fetchone()[0] == 0
    spans_gone = db.execute("SELECT count(*) FROM annotation_span WHERE annotation_id=?", (aid,)).fetchone()[0] == 0
    ok("delete a cascata (annotazione+span)", gone and spans_gone)

    print("\n%d pass, %d fail" % (PASS["n"], FAIL["n"]))
    return FAIL["n"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
