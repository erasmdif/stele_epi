"""API JSON del DBMS."""
from flask import Blueprint, jsonify, request, Response, current_app
from .. import models, tei, mutations
from .. import get_db
from ..db import project as project_lib

bp = Blueprint("api", __name__)


def _err(msg, code=400):
    return jsonify({"error": str(msg)}), code


@bp.get("/objects")
def objects():
    return jsonify(models.list_objects(get_db()))


@bp.get("/objects/<int:obj_id>")
def object_detail(obj_id):
    o = models.get_object(get_db(), obj_id)
    return (jsonify(o), 200) if o else (jsonify({"error": "not found"}), 404)


@bp.get("/text-versions/<int:version_id>/annotations")
def version_annotations(version_id):
    db = get_db()
    return jsonify({
        "version": models.get_text_version(db, version_id),
        "annotations": models.annotations_for_version(db, version_id),
        "places": models.places_for_version(db, version_id),
    })


@bp.get("/text-versions/<int:version_id>/tei")
def version_tei(version_id):
    xml = tei.export_text_version(get_db(), version_id)
    return Response(xml, mimetype="application/xml")


@bp.get("/vocab/<term_table>/<int:term_id>/lineage")
def vocab_lineage(term_table, term_id):
    if term_table not in models.RELATION_TABLE:
        return jsonify({"error": "unknown vocabulary"}), 400
    db = get_db()
    return jsonify({
        "ancestors": models.ancestors(db, term_table, term_id),
        "descendants": models.descendants(db, term_table, term_id),
        "neighbours": models.term_neighbours(db, term_table, term_id),
    })


@bp.get("/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    return jsonify(models.fulltext_search(get_db(), q))


# ---------------------------------------------------------------------------
# Scrittura: annotazioni
# ---------------------------------------------------------------------------
def _current_user(db):
    r = db.execute("SELECT id FROM app_user WHERE is_active=1 ORDER BY id LIMIT 1").fetchone()
    return r["id"] if r else None


@bp.post("/project/remove-sample-data")
def remove_sample_data():
    """Replace the bundled sample corpus with a clean, empty project."""
    payload = request.get_json(force=True, silent=True) or {}
    if payload.get("confirmation") != "REMOVE SAMPLE DATA":
        return _err("Type REMOVE SAMPLE DATA to confirm this operation.")
    db = get_db()
    try:
        backup_path = project_lib.replace_sample_with_blank(
            db, current_app.config["PROJECT_DB"]
        )
    except ValueError as exc:
        return _err(exc)
    current_app.config["SAMPLE_DATA_ACTIVE"] = False
    return jsonify({"ok": True, "backup_path": backup_path})


@bp.post("/text-versions/<int:version_id>/annotations")
def create_annotation(version_id):
    db = get_db()
    d = request.get_json(force=True, silent=True) or {}
    try:
        aid = mutations.create_annotation(
            db, version_id,
            annotation_type=d.get("annotation_type", "semantic"),
            note=d.get("note", ""), status=d.get("status", "accepted"),
            certainty_code=d.get("certainty_code"),
            spans=d.get("spans"), terms=d.get("terms"),
            user_id=_current_user(db))
    except ValueError as e:
        return _err(e)
    anns = models.annotations_for_version(db, version_id)
    created = [a for a in anns if a["id"] == aid]
    return jsonify(created[0] if created else {"id": aid}), 201


@bp.patch("/annotations/<int:aid>")
def patch_annotation(aid):
    db = get_db()
    d = request.get_json(force=True, silent=True) or {}
    try:
        mutations.update_annotation(db, aid, d, user_id=_current_user(db))
    except ValueError as e:
        return _err(e)
    return jsonify({"ok": True})


@bp.delete("/annotations/<int:aid>")
def delete_annotation(aid):
    db = get_db()
    try:
        mutations.delete_annotation(db, aid, user_id=_current_user(db))
    except ValueError as e:
        return _err(e)
    return jsonify({"ok": True})


@bp.put("/annotations/<int:aid>/spans")
def put_spans(aid):
    db = get_db()
    d = request.get_json(force=True, silent=True) or {}
    try:
        mutations.set_spans(db, aid, d.get("spans", []), user_id=_current_user(db))
    except ValueError as e:
        return _err(e)
    return jsonify({"ok": True})


@bp.post("/annotations/<int:aid>/terms")
def add_term(aid):
    db = get_db()
    d = request.get_json(force=True, silent=True) or {}
    try:
        mutations.add_annotation_term(db, aid, d["term_id"], d.get("role", "primary"),
                                      d.get("certainty_code"))
    except (ValueError, KeyError) as e:
        return _err(e)
    return jsonify({"ok": True})


@bp.delete("/annotations/<int:aid>/terms/<int:term_id>")
def remove_term(aid, term_id):
    db = get_db()
    mutations.remove_annotation_term(db, aid, term_id, request.args.get("role"))
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Scrittura: vocabolario testuale e rete semantica
# ---------------------------------------------------------------------------
@bp.get("/text-terms")
def text_terms():
    return jsonify(mutations.search_text_terms(get_db(), request.args.get("q", "")))


@bp.post("/text-terms")
def new_text_term():
    db = get_db()
    d = request.get_json(force=True, silent=True) or {}
    try:
        term = mutations.create_text_term(db, d.get("term_type", "other"),
                                          d.get("preferred_label", ""), d.get("description"))
    except ValueError as e:
        return _err(e)
    return jsonify(term), 201


@bp.post("/text-terms/<int:term_id>/place")
def set_place(term_id):
    db = get_db()
    d = request.get_json(force=True, silent=True) or {}
    try:
        mutations.set_term_place(db, term_id, d["lat"], d["lon"],
                                 d.get("precision", "approximate"), d.get("source", "manual"))
    except (ValueError, KeyError) as e:
        return _err(e)
    return jsonify({"ok": True})


@bp.post("/text-term-relations")
def add_relation():
    db = get_db()
    d = request.get_json(force=True, silent=True) or {}
    try:
        mutations.add_term_relation(db, d["source_id"], d["target_id"], d["relation_code"],
                                    d.get("certainty_code"), user_id=_current_user(db))
    except (ValueError, KeyError) as e:
        return _err(e)
    return jsonify({"ok": True})


@bp.get("/relation-types")
def relation_types():
    db = get_db()
    rows = db.execute("SELECT code,label,is_hierarchical FROM relation_type "
                      "WHERE is_active=1 AND domain IN ('generic','text_term') ORDER BY is_hierarchical DESC, code")
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Versioning del testo
# ---------------------------------------------------------------------------
@bp.post("/text-versions/<int:version_id>/revise")
def revise_version(version_id):
    db = get_db()
    d = request.get_json(force=True, silent=True) or {}
    if "content" not in d:
        return _err("content is required")
    try:
        report = mutations.revise_text_version(
            db, version_id, d["content"], note=d.get("note"),
            migrate=d.get("migrate", True), user_id=_current_user(db))
    except ValueError as e:
        return _err(e)
    return jsonify(report), 201


@bp.get("/documents/<int:doc_id>/versions")
def document_versions(doc_id):
    db = get_db()
    rows = db.execute(
        "SELECT id,version_type,version_number,is_current,language,script "
        "FROM text_version WHERE text_document_id=? ORDER BY version_type,version_number", (doc_id,))
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Grafo delle relazioni
# ---------------------------------------------------------------------------
@bp.get("/graph")
def graph():
    db = get_db()
    focus = request.args.get("focus", type=int)
    if not focus:
        focus = models.default_focus_term(db)
    depth = min(4, max(1, request.args.get("depth", default=2, type=int)))
    kinds = tuple((request.args.get("kinds", "relation,cooccur") or "").split(","))
    return jsonify(models.ego_graph(db, focus, depth=depth, kinds=kinds))


@bp.get("/graph/stats")
def graph_stats():
    return jsonify(models.graph_stats(get_db()))


# ---------------------------------------------------------------------------
# Scheda-record del text_term (lettura + editing)
# ---------------------------------------------------------------------------
@bp.get("/text-terms/<int:term_id>")
def term_detail(term_id):
    d = models.get_term_detail(get_db(), term_id)
    if not d:
        return _err("term not found", 404)
    # geometria è bytes -> non serializzabile: già trasformata in "place" dict
    d.pop("properties_bytes", None)
    return jsonify(d)


@bp.patch("/text-terms/<int:term_id>")
def patch_term(term_id):
    db = get_db()
    try:
        mutations.update_text_term(db, term_id, request.get_json(force=True, silent=True) or {},
                                    user_id=_current_user(db))
    except ValueError as e:
        return _err(e)
    return jsonify({"ok": True})


@bp.delete("/text-terms/<int:term_id>")
def delete_term(term_id):
    db = get_db()
    try:
        mutations.delete_text_term(db, term_id, user_id=_current_user(db))
    except ValueError as e:
        return _err(e)
    return jsonify({"ok": True})


@bp.post("/text-terms/<int:term_id>/labels")
def add_label(term_id):
    db = get_db()
    d = request.get_json(force=True, silent=True) or {}
    try:
        lid = mutations.add_term_label(db, term_id, d.get("label", ""), d.get("language"),
                                       d.get("label_type", "alternative"), d.get("script"),
                                       d.get("is_preferred", False))
    except ValueError as e:
        return _err(e)
    return jsonify({"id": lid}), 201


@bp.delete("/text-term-labels/<int:label_id>")
def remove_label(label_id):
    mutations.remove_term_label(get_db(), label_id)
    return jsonify({"ok": True})


@bp.post("/text-terms/<int:term_id>/external-ids")
def add_external(term_id):
    db = get_db()
    d = request.get_json(force=True, silent=True) or {}
    try:
        xid = mutations.add_term_external_id(db, term_id, d.get("authority", ""),
                                             d.get("identifier", ""), d.get("uri"), d.get("note"))
    except ValueError as e:
        return _err(e)
    return jsonify({"id": xid}), 201


@bp.delete("/text-term-external-ids/<int:xid>")
def remove_external(xid):
    mutations.remove_term_external_id(get_db(), xid)
    return jsonify({"ok": True})


@bp.delete("/text-term-relations")
def delete_relation():
    db = get_db()
    d = request.get_json(force=True, silent=True) or {}
    try:
        mutations.remove_term_relation(db, d["source_id"], d["target_id"], d["relation_code"])
    except (ValueError, KeyError) as e:
        return _err(e)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Versioni parallele + allineamento
# ---------------------------------------------------------------------------
@bp.get("/documents/<int:doc_id>/parallel-view")
def parallel_view(doc_id):
    db = get_db()
    active = request.args.get("types")
    types = active.split(",") if active else None
    view = models.parallel_view(db, doc_id, active_version_types=types)
    if not view:
        return _err("document is empty", 404)
    return jsonify(view)


@bp.post("/documents/<int:doc_id>/auto-align")
def auto_align(doc_id):
    db = get_db()
    try:
        rep = mutations.auto_align_document(db, doc_id, user_id=_current_user(db))
    except ValueError as e:
        return _err(e)
    return jsonify(rep)


@bp.post("/documents/<int:doc_id>/parallel-versions")
def new_parallel(doc_id):
    db = get_db()
    d = request.get_json(force=True, silent=True) or {}
    try:
        vid = mutations.create_parallel_version(
            db, doc_id,
            version_type=d.get("version_type", "translation"),
            language=d.get("language"),
            content=d.get("content", ""),
            based_on_version_id=d.get("based_on_version_id"),
            note=d.get("note"),
            auto_align=d.get("auto_align", True),
            user_id=_current_user(db))
    except ValueError as e:
        return _err(e)
    return jsonify({"id": vid}), 201


@bp.put("/alignment-groups/<int:group_id>")
def put_alignment_group(group_id):
    db = get_db()
    d = request.get_json(force=True, silent=True) or {}
    try:
        gid = mutations.set_alignment_group(db, group_id, d.get("unit_ids", []),
                                            d.get("primary_unit_id"), user_id=_current_user(db))
    except (ValueError, KeyError) as e:
        return _err(e)
    return jsonify({"group_id": gid})


@bp.post("/alignment-groups")
def create_alignment_group():
    db = get_db()
    d = request.get_json(force=True, silent=True) or {}
    try:
        gid = mutations.set_alignment_group(db, None, d.get("unit_ids", []),
                                            d.get("primary_unit_id"), user_id=_current_user(db))
    except (ValueError, KeyError) as e:
        return _err(e)
    return jsonify({"group_id": gid}), 201


@bp.delete("/alignment-groups/<int:group_id>")
def del_alignment_group(group_id):
    db = get_db()
    mutations.delete_alignment_group(db, group_id, user_id=_current_user(db))
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API generiche per vocabolari (context_term / object_term / chronology_term)
# ---------------------------------------------------------------------------
_ALLOWED_VOCAB_ROUTE = ("context_term", "object_term", "chronology_term")


@bp.get("/vocab/<string:table>")
def generic_vocab_search(table):
    if table not in _ALLOWED_VOCAB_ROUTE:
        return _err("Table not allowed", 404)
    q = request.args.get("q", "")
    return jsonify(models.search_generic_terms(get_db(), table, q))


@bp.get("/vocab/<string:table>/<int:term_id>")
def generic_vocab_detail(table, term_id):
    if table not in _ALLOWED_VOCAB_ROUTE:
        return _err("Table not allowed", 404)
    d = models.get_generic_term_detail(get_db(), table, term_id)
    if not d:
        return _err("term not found", 404)
    d.pop("_meta", None)
    return jsonify(d)


@bp.post("/vocab/<string:table>")
def generic_vocab_create(table):
    if table not in _ALLOWED_VOCAB_ROUTE:
        return _err("Table not allowed", 404)
    d = request.get_json(force=True, silent=True) or {}
    try:
        t = mutations.create_generic_term(
            get_db(), table, d.get("preferred_label", ""),
            term_type=d.get("term_type"),
            description=d.get("description"),
            extra={k: d.get(k) for k in ("year_from", "year_to", "precision") if k in d})
    except ValueError as e:
        return _err(e)
    return jsonify(t), 201


@bp.patch("/vocab/<string:table>/<int:term_id>")
def generic_vocab_patch(table, term_id):
    if table not in _ALLOWED_VOCAB_ROUTE:
        return _err("Table not allowed", 404)
    db = get_db()
    try:
        mutations.update_generic_term(db, table, term_id,
                                       request.get_json(force=True, silent=True) or {},
                                       user_id=_current_user(db))
    except ValueError as e:
        return _err(e)
    return jsonify({"ok": True})


@bp.delete("/vocab/<string:table>/<int:term_id>")
def generic_vocab_delete(table, term_id):
    if table not in _ALLOWED_VOCAB_ROUTE:
        return _err("Table not allowed", 404)
    db = get_db()
    try:
        mutations.delete_generic_term(db, table, term_id, user_id=_current_user(db))
    except ValueError as e:
        return _err(e)
    return jsonify({"ok": True})


@bp.post("/vocab/<string:table>/<int:term_id>/labels")
def generic_vocab_add_label(table, term_id):
    if table not in _ALLOWED_VOCAB_ROUTE:
        return _err("Table not allowed", 404)
    d = request.get_json(force=True, silent=True) or {}
    try:
        lid = mutations.add_generic_term_label(
            get_db(), table, term_id, d.get("label", ""), d.get("language"),
            d.get("label_type", "alternative"), d.get("script"),
            d.get("is_preferred", False))
    except ValueError as e:
        return _err(e)
    return jsonify({"id": lid}), 201


@bp.delete("/vocab/<string:table>/labels/<int:label_id>")
def generic_vocab_remove_label(table, label_id):
    if table not in _ALLOWED_VOCAB_ROUTE:
        return _err("Table not allowed", 404)
    try:
        mutations.remove_generic_term_label(get_db(), table, label_id)
    except ValueError as e:
        return _err(e)
    return jsonify({"ok": True})


@bp.post("/vocab/<string:table>/relations")
def generic_vocab_add_relation(table):
    if table not in _ALLOWED_VOCAB_ROUTE:
        return _err("Table not allowed", 404)
    d = request.get_json(force=True, silent=True) or {}
    db = get_db()
    try:
        mutations.add_generic_term_relation(
            db, table, d["source_id"], d["target_id"], d["relation_code"],
            d.get("certainty_code"), user_id=_current_user(db))
    except (ValueError, KeyError) as e:
        return _err(e)
    return jsonify({"ok": True})


@bp.delete("/vocab/<string:table>/relations")
def generic_vocab_delete_relation(table):
    if table not in _ALLOWED_VOCAB_ROUTE:
        return _err("Table not allowed", 404)
    d = request.get_json(force=True, silent=True) or {}
    try:
        mutations.remove_generic_term_relation(
            get_db(), table, d["source_id"], d["target_id"], d["relation_code"])
    except (ValueError, KeyError) as e:
        return _err(e)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Iterazione 2 · Context / Object — editing + datazioni + assegnazioni
# ---------------------------------------------------------------------------
@bp.patch("/context/<int:ctx_id>")
def patch_context(ctx_id):
    db = get_db()
    try:
        mutations.update_context(db, ctx_id, request.get_json(force=True, silent=True) or {},
                                  user_id=_current_user(db))
    except ValueError as e:
        return _err(e)
    return jsonify({"ok": True})


@bp.patch("/object/<int:obj_id>")
def patch_object(obj_id):
    db = get_db()
    try:
        mutations.update_object(db, obj_id, request.get_json(force=True, silent=True) or {},
                                 user_id=_current_user(db))
    except ValueError as e:
        return _err(e)
    return jsonify({"ok": True})


# --- datazioni multiple (uniforme per context e object) --------------------
@bp.post("/<any(context,object):owner_kind>/<int:owner_id>/datings")
def add_dating(owner_kind, owner_id):
    db = get_db()
    d = request.get_json(force=True, silent=True) or {}
    try:
        did = mutations.add_dating(
            db, owner_kind, owner_id,
            chronology_term_id=d.get("chronology_term_id"),
            absolute_from=d.get("absolute_from"),
            absolute_to=d.get("absolute_to"),
            dating_method=d.get("dating_method"),
            certainty_code=d.get("certainty_code"),
            note=d.get("note"), user_id=_current_user(db))
    except ValueError as e:
        return _err(e)
    return jsonify({"id": did}), 201


@bp.patch("/<any(context,object):owner_kind>-datings/<int:dating_id>")
def patch_dating(owner_kind, dating_id):
    db = get_db()
    try:
        mutations.update_dating(db, owner_kind, dating_id,
                                 request.get_json(force=True, silent=True) or {},
                                 user_id=_current_user(db))
    except ValueError as e:
        return _err(e)
    return jsonify({"ok": True})


@bp.delete("/<any(context,object):owner_kind>-datings/<int:dating_id>")
def del_dating(owner_kind, dating_id):
    db = get_db()
    try:
        mutations.delete_dating(db, owner_kind, dating_id, user_id=_current_user(db))
    except ValueError as e:
        return _err(e)
    return jsonify({"ok": True})


# --- assegnazione termini in-place -----------------------------------------
@bp.post("/<any(context,object):owner_kind>/<int:owner_id>/terms")
def add_term_assign(owner_kind, owner_id):
    db = get_db()
    d = request.get_json(force=True, silent=True) or {}
    try:
        aid = mutations.add_term_assignment(
            db, owner_kind, owner_id, d["term_id"],
            certainty_code=d.get("certainty_code"), note=d.get("note"),
            user_id=_current_user(db))
    except (ValueError, KeyError) as e:
        return _err(e)
    return jsonify({"id": aid}), 201


@bp.delete("/<any(context,object):owner_kind>-term-assignments/<int:assign_id>")
def del_term_assign(owner_kind, assign_id):
    try:
        mutations.remove_term_assignment(get_db(), owner_kind, assign_id)
    except ValueError as e:
        return _err(e)
    return jsonify({"ok": True})


# --- vocabolari ausiliari per l'UI (enumerazioni) --------------------------
@bp.get("/enums/archaeology")
def enums_archaeology():
    return jsonify({
        "deposit_types": list(mutations.DEPOSIT_TYPES),
        "excavation_techniques": list(mutations.EXCAVATION_TECHNIQUES),
        "dating_methods": list(mutations.DATING_METHODS),
    })


# ============================================================================
# ANALYTICS API
# ============================================================================

@bp.get("/analytics/semantic-search")
def analytics_semantic_search_api():
    """Ricerca semantica gerarchica. Params: term_id (required),
    deposit_type, year_from, year_to."""
    term_id = request.args.get("term_id", type=int)
    if not term_id:
        return jsonify({"error": "term_id is required"}), 400
    deposit_type = request.args.get("deposit_type")
    year_from = request.args.get("year_from", type=int)
    year_to = request.args.get("year_to", type=int)
    results = models.analytics_semantic_search(
        get_db(), term_id, deposit_type=deposit_type,
        year_from=year_from, year_to=year_to)
    return jsonify(results)


@bp.get("/analytics/cooccurrence")
def analytics_cooccurrence_api():
    """Grafo co-occorrenze. Params: scope (version|unit), min_count."""
    scope = request.args.get("scope", "version")
    min_count = request.args.get("min_count", 1, type=int)
    data = models.analytics_cooccurrence(
        get_db(), scope=scope, min_count=min_count)
    return jsonify(data)


@bp.get("/analytics/text-concept-matrix")
def analytics_text_concept_matrix_api():
    """Matrice testi × concetti."""
    data = models.analytics_text_concept_matrix(get_db())
    return jsonify(data)


@bp.get("/analytics/text-archaeology-cross")
def analytics_text_archaeology_cross_api():
    """Incrocio contenuto testuale × realtà archeologica."""
    data = models.analytics_text_archaeology_cross(get_db())
    return jsonify(data)


@bp.get("/analytics/terms-for-search")
def analytics_terms_for_search():
    """Lista termini disponibili per la ricerca semantica."""
    terms = [dict(r) for r in get_db().execute("""
        SELECT id, preferred_label, description FROM text_term
         ORDER BY preferred_label
    """)]
    return jsonify(terms)


# --- vista ricostruita frammenti -------------------------------------------
@bp.get("/objects/<int:obj_id>/reconstructed-text")
def object_reconstructed_text(obj_id):
    """Vista ricostruita del testo da frammenti."""
    data = models.get_reconstructed_text(get_db(), obj_id)
    if not data:
        return jsonify({"error": "no fragments found"}), 404
    return jsonify(data)

@bp.get("/objects/<int:obj_id>/fragments")
def object_fragments(obj_id):
    """Lista frammenti di un oggetto ricostruito."""
    frags = models.get_fragments(get_db(), obj_id)
    return jsonify(frags)


# --- Analytics Fase 3 -------------------------------------------------------
@bp.get("/analytics/spatiotemporal")
def analytics_spatiotemporal_api():
    """Distribuzione spazio-temporale su mappa.
    Params: term_id (opz), year_from, year_to, mode (findspot|mention)."""
    term_id = request.args.get("term_id", type=int)
    year_from = request.args.get("year_from", type=int)
    year_to = request.args.get("year_to", type=int)
    mode = request.args.get("mode", "findspot")
    if mode not in ("findspot", "mention"):
        return jsonify({"error": "mode must be findspot or mention"}), 400
    data = models.analytics_spatiotemporal(
        get_db(), term_id=term_id, year_from=year_from,
        year_to=year_to, mode=mode)
    return jsonify(data)


@bp.get("/analytics/formula-search")
def analytics_formula_search_api():
    """Ricerca formule e paralleli testuali."""
    vtype = request.args.get("version_type", "normalized")
    min_sim = request.args.get("min_similarity", 0.3, type=float)
    ngram = request.args.get("ngram", 3, type=int)
    data = models.analytics_formula_search(
        get_db(), version_type=vtype,
        min_similarity=min_sim, ngram=ngram)
    return jsonify(data)


@bp.get("/analytics/ngram-frequency")
def analytics_ngram_frequency_api():
    """N-grammi più frequenti nei testi."""
    vtype = request.args.get("version_type", "normalized")
    ngram = request.args.get("ngram", 2, type=int)
    min_count = request.args.get("min_count", 2, type=int)
    limit = request.args.get("limit", 30, type=int)
    data = models.analytics_ngram_frequency(
        get_db(), version_type=vtype, ngram=ngram,
        min_count=min_count, limit=limit)
    return jsonify(data)


@bp.get("/analytics/concept-timeline")
def analytics_concept_timeline_api():
    """Timeline dei rami semantici. Params: granularity (century|half)."""
    gran = request.args.get("granularity", "century")
    if gran not in ("century", "half"):
        return jsonify({"error": "granularity must be century or half"}), 400
    data = models.analytics_concept_timeline(get_db(), granularity=gran)
    return jsonify(data)


# --- WORK (opere intellettuali astratte) ------------------------------------
@bp.get("/works")
def works_list_api():
    """Elenca tutte le opere con numero di testimoni."""
    return jsonify(models.list_works(get_db()))


@bp.get("/works/<int:work_id>")
def work_detail_api(work_id):
    """Dettaglio opera con lista dei testimoni."""
    w = models.get_work(get_db(), work_id)
    if not w:
        return jsonify({"error": "not found"}), 404
    return jsonify(w)


@bp.post("/works")
def work_create_api():
    """Crea una nuova opera."""
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    work_id = models.create_work(
        get_db(),
        title=title,
        author=data.get("author"),
        work_type=data.get("work_type"),
        canonical_dating=data.get("canonical_dating"),
        composition_from=data.get("composition_from"),
        composition_to=data.get("composition_to"),
        language=data.get("language"),
        description=data.get("description"),
        bibliography=data.get("bibliography"),
        notes=data.get("notes"),
    )
    return jsonify({"id": work_id}), 201


@bp.patch("/works/<int:work_id>")
def work_update_api(work_id):
    """Aggiorna un'opera."""
    data = request.get_json() or {}
    ok = models.update_work(get_db(), work_id, **data)
    if not ok:
        return jsonify({"error": "no fields to update"}), 400
    return jsonify({"ok": True})


@bp.post("/documents/<int:doc_id>/link-work")
def link_document_to_work_api(doc_id):
    """Collega un text_document a un work (o scollega passando work_id=null)."""
    data = request.get_json() or {}
    work_id = data.get("work_id")  # None per scollegare
    witness_siglum = data.get("witness_siglum")
    models.link_document_to_work(get_db(), doc_id, work_id, witness_siglum)
    return jsonify({"ok": True})


@bp.get("/documents/without-work")
def documents_without_work_api():
    """Documenti non ancora collegati a un'opera."""
    return jsonify(models.documents_without_work(get_db()))


# --- WORK ANALYTICS: confronto testimoni ------------------------------------
@bp.get("/analytics/works-with-witnesses")
def analytics_works_with_witnesses_api():
    """Elenca solo le opere con >=2 testimoni (utile per il selettore)."""
    rows = [dict(r) for r in get_db().execute("""
        SELECT w.id, w.title, w.work_type, COUNT(td.id) AS n_witnesses
          FROM work w
          JOIN text_document td ON td.work_id = w.id AND td.is_active = 1
         WHERE w.is_active = 1
         GROUP BY w.id
        HAVING COUNT(td.id) >= 2
         ORDER BY w.title
    """)]
    return jsonify(rows)


@bp.get("/analytics/works/<int:work_id>/witnesses-diff")
def analytics_work_witnesses_diff_api(work_id):
    """Matrice di similarità + apparato critico dei testimoni di un'opera."""
    vtype = request.args.get("version_type", "normalized")
    ngram = request.args.get("ngram", 2, type=int)
    data = models.analytics_work_witnesses_diff(
        get_db(), work_id, version_type=vtype, ngram=ngram)
    return jsonify(data)


@bp.get("/analytics/works/<int:work_id>/pair-diff")
def analytics_work_pair_diff_api(work_id):
    """Diff dettagliato tra due testimoni. Params: a=doc_id, b=doc_id."""
    a = request.args.get("a", type=int)
    b = request.args.get("b", type=int)
    vtype = request.args.get("version_type", "normalized")
    if not a or not b:
        return jsonify({"error": "params a and b (doc ids) required"}), 400
    data = models.analytics_work_witness_pair_diff(
        get_db(), work_id, a, b, version_type=vtype)
    if data is None:
        return jsonify({"error": "docs not found or not in this work"}), 404
    return jsonify(data)
