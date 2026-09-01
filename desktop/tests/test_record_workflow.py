"""
Test del flusso record-based richiesto dall'utente:
1. sottolineo, creo annotazione;
2. lego a un record NUOVO ("Ares") creato inline;
3. dalla scheda-record aggiungo relazione con "dio greco" (anch'esso NUOVO, creato inline);
4. verifico che la profondità si eredita in tutte le annotazioni che puntano al record;
5. testo scheda-record: label alternative, ID esterni, occorrenze, rimozione relazione.
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
    vid = db.execute("SELECT id FROM text_version WHERE version_type='normalized'").fetchone()["id"]

    # 1. creo annotazione
    a1 = c.post(f"/api/text-versions/{vid}/annotations",
                json={"annotation_type": "named_entity", "spans": [{"start": 0, "end": 4}]}).get_json()["id"]

    # 2. creo record NUOVO "Ares" e lo lego
    ares = c.post("/api/text-terms", json={"term_type": "deity", "preferred_label": "Ares"}).get_json()
    ok("Ares creato ex novo", ares["preferred_label"] == "Ares" and ares["term_type"] == "deity")
    c.post(f"/api/annotations/{a1}/terms", json={"term_id": ares["id"], "role": "primary"})

    # 3. dalla scheda-record: aggiungo relazione con record NUOVO "dio greco" creato inline
    dio = c.post("/api/text-terms", json={"term_type": "concept", "preferred_label": "dio greco"}).get_json()
    ok("'dio greco' creato ex novo dal picker", dio["preferred_label"] == "dio greco")
    r = c.post("/api/text-term-relations",
               json={"source_id": ares["id"], "target_id": dio["id"], "relation_code": "IS_A"})
    ok("relazione IS_A creata", r.status_code == 200)

    # divinità (altro livello)
    div = c.post("/api/text-terms", json={"term_type": "concept", "preferred_label": "divinità"}).get_json()
    c.post("/api/text-term-relations",
           json={"source_id": dio["id"], "target_id": div["id"], "relation_code": "IS_A"})

    # 4. profondità ereditata a runtime
    lin = c.get(f"/api/vocab/text_term/{ares['id']}/lineage").get_json()
    labels = [x["preferred_label"] for x in lin["ancestors"]]
    ok("gerarchia risalita: dio greco", "dio greco" in labels)
    ok("gerarchia risalita: divinità (transitiva)", "divinità" in labels)

    # 5. CREO UNA SECONDA annotazione legata allo STESSO Ares
    #    -> deve vedere identica gerarchia SENZA doverla ri-esplicitare
    a2 = c.post(f"/api/text-versions/{vid}/annotations",
                json={"annotation_type": "named_entity", "spans": [{"start": 5, "end": 10}]}).get_json()["id"]
    c.post(f"/api/annotations/{a2}/terms", json={"term_id": ares["id"], "role": "primary"})

    detail = c.get(f"/api/text-terms/{ares['id']}").get_json()
    ok("scheda-record: 2 occorrenze rilevate", len(detail["occurrences"]) == 2)
    ok("scheda-record: ereditarietà ancestors uguale per entrambe",
       [x["preferred_label"] for x in detail["ancestors"]] == labels)

    # 6. AGGIUNGO relazione DOPO che le annotazioni esistono: entrambe la ereditano
    war = c.post("/api/text-terms", json={"term_type": "concept", "preferred_label": "guerra"}).get_json()
    c.post("/api/text-term-relations",
           json={"source_id": ares["id"], "target_id": war["id"], "relation_code": "ASSOCIATED_WITH"})
    detail2 = c.get(f"/api/text-terms/{ares['id']}").get_json()
    rels = {(n["rel"], n["other_label"]) for n in detail2["neighbours"]}
    ok("relazione retroattiva visibile a tutte le occorrenze",
       ("ASSOCIATED_WITH", "guerra") in rels)

    # 7. label alternative + ID esterni
    lid = c.post(f"/api/text-terms/{ares['id']}/labels",
                 json={"label": "Ἄρης", "language": "grc", "label_type": "alternative"}).get_json()["id"]
    ok("label alternativa aggiunta", lid > 0)
    ok("label ricompare nella scheda",
       any(l["label"] == "Ἄρης" for l in c.get(f"/api/text-terms/{ares['id']}").get_json()["labels"]))

    xid = c.post(f"/api/text-terms/{ares['id']}/external-ids",
                 json={"authority": "Wikidata", "identifier": "Q41127",
                       "uri": "https://www.wikidata.org/wiki/Q41127"}).get_json()["id"]
    ok("ID esterno Wikidata aggiunto", xid > 0)
    # duplicato -> 400
    r = c.post(f"/api/text-terms/{ares['id']}/external-ids",
               json={"authority": "Wikidata", "identifier": "Q41127"})
    ok("ID esterno duplicato rifiutato", r.status_code == 400)

    # 8. rimozione di una relazione
    r = c.delete("/api/text-term-relations",
                 json={"source_id": ares["id"], "target_id": war["id"], "relation_code": "ASSOCIATED_WITH"})
    ok("relazione rimossa", r.status_code == 200)
    detail3 = c.get(f"/api/text-terms/{ares['id']}").get_json()
    ok("relazione sparita dalla scheda",
       not any(n["rel"] == "ASSOCIATED_WITH" and n["other_label"] == "guerra" for n in detail3["neighbours"]))

    # 9. delete termine usato -> 400 (RESTRICT), delete termine libero -> ok
    r = c.delete(f"/api/text-terms/{ares['id']}")
    ok("delete di termine usato: rifiutato", r.status_code == 400)
    orphan = c.post("/api/text-terms", json={"term_type": "concept", "preferred_label": "temp"}).get_json()
    r = c.delete(f"/api/text-terms/{orphan['id']}")
    ok("delete di termine libero: ok", r.status_code == 200)

    # 10. patch termine
    r = c.patch(f"/api/text-terms/{ares['id']}", json={"description": "dio della guerra"})
    ok("patch descrizione", r.status_code == 200)
    ok("patch riflessa",
       c.get(f"/api/text-terms/{ares['id']}").get_json()["description"] == "dio della guerra")

    # 11. pagina web della scheda risponde
    r = c.get(f"/vocabularies/{ares['id']}")
    ok("pagina /vocabularies/<id> 200", r.status_code == 200)
    ok("pagina contiene la scheda", b"Semantic network" in r.data and b"Text occurrences" in r.data)

    print("\n%d pass, %d fail" % (PASS["n"], FAIL["n"]))
    return FAIL["n"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
