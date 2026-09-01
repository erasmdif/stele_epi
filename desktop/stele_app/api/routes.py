"""API JSON del DBMS."""
from flask import Blueprint, jsonify, request, Response
from .. import models, tei, mutations
from .. import get_db

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
        return _err("content mancante")
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
        return _err("term inesistente", 404)
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
        return _err("documento vuoto", 404)
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
        return _err("tabella non consentita", 404)
    q = request.args.get("q", "")
    return jsonify(models.search_generic_terms(get_db(), table, q))


@bp.get("/vocab/<string:table>/<int:term_id>")
def generic_vocab_detail(table, term_id):
    if table not in _ALLOWED_VOCAB_ROUTE:
        return _err("tabella non consentita", 404)
    d = models.get_generic_term_detail(get_db(), table, term_id)
    if not d:
        return _err("term inesistente", 404)
    d.pop("_meta", None)
    return jsonify(d)


@bp.post("/vocab/<string:table>")
def generic_vocab_create(table):
    if table not in _ALLOWED_VOCAB_ROUTE:
        return _err("tabella non consentita", 404)
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
        return _err("tabella non consentita", 404)
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
        return _err("tabella non consentita", 404)
    db = get_db()
    try:
        mutations.delete_generic_term(db, table, term_id, user_id=_current_user(db))
    except ValueError as e:
        return _err(e)
    return jsonify({"ok": True})


@bp.post("/vocab/<string:table>/<int:term_id>/labels")
def generic_vocab_add_label(table, term_id):
    if table not in _ALLOWED_VOCAB_ROUTE:
        return _err("tabella non consentita", 404)
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
        return _err("tabella non consentita", 404)
    try:
        mutations.remove_generic_term_label(get_db(), table, label_id)
    except ValueError as e:
        return _err(e)
    return jsonify({"ok": True})


@bp.post("/vocab/<string:table>/relations")
def generic_vocab_add_relation(table):
    if table not in _ALLOWED_VOCAB_ROUTE:
        return _err("tabella non consentita", 404)
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
        return _err("tabella non consentita", 404)
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
