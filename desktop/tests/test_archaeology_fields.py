"""
Test dell'iterazione 2:
- nuovi campi archeologici su context / object;
- CHECK di enumerazione (deposit_type, excavation_technique) rispettati;
- migrazione non-distruttiva che aggiunge le colonne su progetti "vecchi";
- datazioni multiple con termine o intervallo libero;
- validazione anni/metodi/from-to;
- assegnazione termini in-place con rimozione;
- scheda contesto (nuova) e scheda oggetto risponde ai nuovi campi;
- API enums.
"""
import os
import sys
import tempfile
import sqlite3
import shutil

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

    # --- schema nuovo: colonne presenti ---
    ctx_cols = {r[1] for r in db.execute("PRAGMA table_info(context)")}
    obj_cols = {r[1] for r in db.execute("PRAGMA table_info(object)")}
    ok("context: nuove colonne presenti",
       {"deposit_type", "excavation_technique", "excavation_method_note", "preservation_note"} <= ctx_cols)
    ok("object: nuove colonne presenti",
       {"decoration_present", "decoration_note", "restored", "restoration_date", "restoration_note"} <= obj_cols)

    # --- PATCH context con nuovi campi ---
    ctx_id = db.execute("SELECT id FROM context LIMIT 1").fetchone()[0]
    r = c.patch(f"/api/context/{ctx_id}", json={
        "deposit_type": "floor",
        "excavation_technique": "stratigraphic",
        "excavation_method_note": "setaccio 2mm",
        "preservation_note": "ottimo"})
    ok("patch context: campi archeologici 200", r.status_code == 200)
    row = db.execute("SELECT deposit_type, excavation_technique, excavation_method_note, preservation_note "
                     "FROM context WHERE id=?", (ctx_id,)).fetchone()
    ok("patch riflessa (deposit_type)", row["deposit_type"] == "floor")
    ok("patch riflessa (excavation_technique)", row["excavation_technique"] == "stratigraphic")

    # --- validazione: enum sbagliato ---
    r = c.patch(f"/api/context/{ctx_id}", json={"deposit_type": "invalid_x"})
    ok("deposit_type invalido -> 400", r.status_code == 400)
    r = c.patch(f"/api/context/{ctx_id}", json={"excavation_technique": "chirurgia"})
    ok("excavation_technique invalida -> 400", r.status_code == 400)

    # --- PATCH object ---
    obj_id = db.execute("SELECT id FROM object LIMIT 1").fetchone()[0]
    r = c.patch(f"/api/object/{obj_id}", json={
        "decoration_present": True, "decoration_note": "Incisione",
        "restored": True, "restoration_date": "anni '80",
        "restoration_note": "Ricomposizione."})
    ok("patch object: campi archeologici 200", r.status_code == 200)
    row = db.execute("SELECT decoration_present, restored, restoration_date FROM object WHERE id=?",
                     (obj_id,)).fetchone()
    ok("bool coercion (decoration_present=1)", row["decoration_present"] == 1)
    ok("bool coercion (restored=1)", row["restored"] == 1)
    ok("restoration_date libero", row["restoration_date"] == "anni '80")

    # completeness fuori range -> 400
    r = c.patch(f"/api/object/{obj_id}", json={"completeness_percentage": 150})
    ok("completeness > 100 -> 400", r.status_code == 400)

    # --- datazioni multiple ---
    ch = c.post("/api/vocab/chronology_term", json={
        "preferred_label": "Late Mycenaean IIIB",
        "year_from": -1300, "year_to": -1200}).get_json()["id"]

    # (a) datazione via termine
    r = c.post(f"/api/context/{ctx_id}/datings", json={
        "chronology_term_id": ch, "dating_method": "stratigraphic_context",
        "certainty_code": "probable"})
    ok("dating via term 201", r.status_code == 201)
    row = db.execute("SELECT absolute_from, absolute_to FROM context_chronology WHERE id=?",
                     (r.get_json()["id"],)).fetchone()
    ok("anni presi dal termine", row["absolute_from"] == -1300 and row["absolute_to"] == -1200)

    # (b) datazione libera
    r = c.post(f"/api/context/{ctx_id}/datings", json={
        "absolute_from": -1250, "absolute_to": -1150,
        "dating_method": "palaeography", "certainty_code": "possible",
        "note": "indipendente"})
    ok("dating libera 201", r.status_code == 201)

    # (c) sia termine che anni: gli anni sovrascrivono
    r = c.post(f"/api/context/{ctx_id}/datings", json={
        "chronology_term_id": ch, "absolute_from": -1290, "absolute_to": -1220,
        "dating_method": "radiocarbon"})
    ok("dating con override 201", r.status_code == 201)
    row = db.execute("SELECT absolute_from, absolute_to FROM context_chronology WHERE id=?",
                     (r.get_json()["id"],)).fetchone()
    ok("override anni ha effetto", row["absolute_from"] == -1290 and row["absolute_to"] == -1220)

    # (d) validazione: metodo non valido
    r = c.post(f"/api/context/{ctx_id}/datings", json={
        "absolute_from": -1000, "absolute_to": -800, "dating_method": "astrologia"})
    ok("dating_method invalido -> 400", r.status_code == 400)

    # (e) validazione: from > to
    r = c.post(f"/api/context/{ctx_id}/datings", json={
        "absolute_from": -800, "absolute_to": -1000, "dating_method": "other"})
    ok("from > to -> 400", r.status_code == 400)
    ok("errore chiaro from>to",
       "≤" in r.get_json().get("error", "") or "<=" in r.get_json().get("error", ""))

    # (f) senza né termine né anni -> 400
    r = c.post(f"/api/context/{ctx_id}/datings", json={"dating_method": "other"})
    ok("dating vuota -> 400", r.status_code == 400)

    # (g) update di una datazione
    dating_id = c.post(f"/api/context/{ctx_id}/datings", json={
        "absolute_from": -1000, "absolute_to": -900,
        "dating_method": "typological"}).get_json()["id"]
    r = c.patch(f"/api/context-datings/{dating_id}", json={
        "absolute_to": -850, "certainty_code": "uncertain"})
    ok("patch dating 200", r.status_code == 200)
    row = db.execute("SELECT absolute_to FROM context_chronology WHERE id=?", (dating_id,)).fetchone()
    ok("patch riflessa", row["absolute_to"] == -850)

    # (h) delete datazione
    r = c.delete(f"/api/context-datings/{dating_id}")
    ok("delete dating 200", r.status_code == 200)
    ok("dating sparita",
       db.execute("SELECT count(*) FROM context_chronology WHERE id=?", (dating_id,)).fetchone()[0] == 0)

    # --- assegnazione termini in-place ---
    mid = c.post("/api/vocab/context_term",
                 json={"preferred_label": "midden", "term_type": "deposit_type"}).get_json()["id"]
    r = c.post(f"/api/context/{ctx_id}/terms", json={"term_id": mid, "certainty_code": "probable"})
    ok("assegna term a context 201", r.status_code == 201)
    aid = r.get_json()["id"]
    ok("assegnazione visibile",
       db.execute("SELECT count(*) FROM context_term_assignment WHERE id=?", (aid,)).fetchone()[0] == 1)
    # duplicato -> 400
    r = c.post(f"/api/context/{ctx_id}/terms", json={"term_id": mid})
    ok("assegnazione duplicata -> 400", r.status_code == 400)
    # remove
    r = c.delete(f"/api/context-term-assignments/{aid}")
    ok("rimuovi assegnazione 200", r.status_code == 200)

    # analogo per object
    mat = c.post("/api/vocab/object_term",
                 json={"preferred_label": "terracotta", "term_type": "material"}).get_json()["id"]
    r = c.post(f"/api/object/{obj_id}/terms", json={"term_id": mat})
    ok("assegna term a object 201", r.status_code == 201)

    # --- pagine web ---
    r = c.get(f"/contexts/{ctx_id}")
    ok("pagina /contexts/<id> 200", r.status_code == 200)
    ok("scheda contesto ha campi archeologici",
       b"fDepositType" in r.data and b"fExcavationTechnique" in r.data)
    ok("scheda contesto ha barra cronologica", b"chronoBar" in r.data)

    r = c.get(f"/objects/{obj_id}")
    ok("scheda oggetto ha nuovi campi",
       b"fDecorationPresent" in r.data and b"fRestored" in r.data)

    # /contexts (lista) mostra le nuove colonne
    r = c.get("/contexts")
    ok("lista contesti mostra deposit_type",
       b"Tipo deposito" in r.data or b"deposit_type" in r.data)

    # --- API enums ---
    r = c.get("/api/enums/archaeology").get_json()
    ok("enums: deposit_types", "midden" in r["deposit_types"])
    ok("enums: excavation_techniques", "stratigraphic" in r["excavation_techniques"])
    ok("enums: dating_methods", "palaeography" in r["dating_methods"] and "radiocarbon" in r["dating_methods"])

    # --- migrazione non-distruttiva ---
    old = os.path.join(d, "old.gpkg")
    shutil.copy(dbpath, old)
    c2 = sqlite3.connect(old)
    # rimuovo le colonne nuove simulando un DB vecchio
    c2.executescript("""
      BEGIN;
      CREATE TABLE ctx_old AS SELECT id,uid,code,name,description,geometry,geometry_precision,
        geometry_note,reliability_id,source_reference,notes,is_active,created_at,updated_at,created_by,updated_by
        FROM context;
      DROP TABLE context;
      ALTER TABLE ctx_old RENAME TO context;
      COMMIT;
    """)
    c2.close()
    # riapertura → migrazione
    reopened = project.open_project(old)
    cols_after = {r[1] for r in reopened.execute("PRAGMA table_info(context)")}
    ok("migrazione: colonne reintrodotte",
       {"deposit_type", "excavation_technique", "preservation_note"} <= cols_after)
    # dati precedenti intatti
    ok("migrazione: dati preservati",
       reopened.execute("SELECT count(*) FROM context").fetchone()[0] > 0)

    print("\n%d pass, %d fail" % (PASS["n"], FAIL["n"]))
    return FAIL["n"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
