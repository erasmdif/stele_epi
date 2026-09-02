"""
Test delle schede-record generiche per context_term / object_term / chronology_term:
mirror del flusso già testato per text_term, adattato ai tre nuovi vocabolari.
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

    # --- context_term -------------------------------------------------------
    mid = c.post("/api/vocab/context_term",
                 json={"preferred_label": "midden", "term_type": "deposit_type"}).get_json()["id"]
    ok("context_term crea", mid > 0)
    wd = c.post("/api/vocab/context_term",
                json={"preferred_label": "waste deposit", "term_type": "deposit_type"}).get_json()["id"]
    r = c.post("/api/vocab/context_term/relations",
               json={"source_id": mid, "target_id": wd, "relation_code": "IS_A"})
    ok("context_term relazione IS_A 200", r.status_code == 200)
    d1 = c.get(f"/api/vocab/context_term/{mid}").get_json()
    ok("context_term lineage risalito", any(a["preferred_label"] == "waste deposit" for a in d1["ancestors"]))
    r = c.post("/api/vocab/context_term/relations",
               json={"source_id": wd, "target_id": mid, "relation_code": "IS_A"})
    ok("context_term ciclo rifiutato", r.status_code == 400)

    # label alternative
    r = c.post(f"/api/vocab/context_term/{mid}/labels",
               json={"label": "discarica", "language": "it"})
    ok("context_term label 201", r.status_code == 201)
    d1 = c.get(f"/api/vocab/context_term/{mid}").get_json()
    ok("context_term label appare", any(l["label"] == "discarica" for l in d1["labels"]))

    # occorrenza + delete rifiutato
    ctx = db.execute("SELECT id FROM context LIMIT 1").fetchone()[0]
    db.execute("INSERT INTO context_term_assignment (context_id,term_id,created_at) VALUES (?,?,?)",
               (ctx, mid, "2025")); db.commit()
    d1 = c.get(f"/api/vocab/context_term/{mid}").get_json()
    ok("context_term occorrenze rilevate", len(d1["occurrences"]) == 1)
    r = c.delete(f"/api/vocab/context_term/{mid}")
    ok("context_term delete in uso rifiutato", r.status_code == 400)

    # --- object_term --------------------------------------------------------
    mat = c.post("/api/vocab/object_term",
                 json={"preferred_label": "terracotta", "term_type": "material"}).get_json()["id"]
    cer = c.post("/api/vocab/object_term",
                 json={"preferred_label": "ceramic", "term_type": "material"}).get_json()["id"]
    c.post("/api/vocab/object_term/relations",
           json={"source_id": mat, "target_id": cer, "relation_code": "IS_A"})
    d1 = c.get(f"/api/vocab/object_term/{mat}").get_json()
    ok("object_term lineage risalito",
       any(a["preferred_label"] == "ceramic" for a in d1["ancestors"]))
    # occorrenze
    obj = db.execute("SELECT id FROM object LIMIT 1").fetchone()[0]
    db.execute("INSERT INTO object_term_assignment (object_id,term_id,created_at) VALUES (?,?,?)",
               (obj, mat, "2025")); db.commit()
    d1 = c.get(f"/api/vocab/object_term/{mat}").get_json()
    ok("object_term occorrenze rilevate", len(d1["occurrences"]) == 1)

    # --- chronology_term ----------------------------------------------------
    ch = c.post("/api/vocab/chronology_term",
                json={"preferred_label": "Late Mycenaean",
                      "year_from": -1400, "year_to": -1050, "precision": "century"}).get_json()["id"]
    d1 = c.get(f"/api/vocab/chronology_term/{ch}").get_json()
    ok("chronology_term year_from/to salvati", d1["year_from"] == -1400 and d1["year_to"] == -1050)
    # patch
    r = c.patch(f"/api/vocab/chronology_term/{ch}",
                json={"year_to": -1100, "precision": "decade"})
    ok("chronology_term patch 200", r.status_code == 200)
    d1 = c.get(f"/api/vocab/chronology_term/{ch}").get_json()
    ok("chronology_term patch applicata",
       d1["year_to"] == -1100 and d1["precision"] == "decade")
    # relazione gerarchica fra due termini di cronologia
    ch2 = c.post("/api/vocab/chronology_term",
                 json={"preferred_label": "Bronze Age",
                       "year_from": -3300, "year_to": -1200}).get_json()["id"]
    c.post("/api/vocab/chronology_term/relations",
           json={"source_id": ch, "target_id": ch2, "relation_code": "PART_OF"})
    d1 = c.get(f"/api/vocab/chronology_term/{ch}").get_json()
    ok("chronology_term relazione PART_OF",
       any(a["preferred_label"] == "Bronze Age" for a in d1["ancestors"]))

    # occorrenze via assegnazione a un object
    db.execute("INSERT INTO object_chronology (object_id,chronology_term_id,dating_method,created_at) "
               "VALUES (?,?,?,?)", (obj, ch, "stylistic", "2025")); db.commit()
    d1 = c.get(f"/api/vocab/chronology_term/{ch}").get_json()
    ok("chronology_term occorrenza da object",
       any(o.get("owner_kind") == "object" for o in d1["occurrences"]))
    r = c.delete(f"/api/vocab/chronology_term/{ch}")
    ok("chronology_term delete in uso rifiutato", r.status_code == 400)

    # --- pagine web ---------------------------------------------------------
    for path in [f"/vocab/context_term/{mid}",
                 f"/vocab/object_term/{mat}",
                 f"/vocab/chronology_term/{ch}"]:
        r = c.get(path)
        ok(f"pagina {path} → 200", r.status_code == 200)
        ok(f"pagina {path} contains 'Semantic network'", b"Semantic network" in r.data)

    # search
    r = c.get("/api/vocab/context_term?q=mid").get_json()
    ok("search context_term", any(x["preferred_label"] == "midden" for x in r))

    # tabella non consentita
    r = c.get("/api/vocab/text_term")
    ok("tabella non consentita → 404", r.status_code == 404)

    print("\n%d pass, %d fail" % (PASS["n"], FAIL["n"]))
    return FAIL["n"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
