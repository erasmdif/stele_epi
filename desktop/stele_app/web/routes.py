"""Pagine HTML del workbench."""
from flask import Blueprint, render_template, abort
from .. import models
from .. import get_db
from ..db import project as project_lib

bp = Blueprint("web", __name__)

NAV = [
    ("dashboard", "Dashboard", "▤"),
    ("contexts", "Contexts", "◈"),
    ("objects", "Objects", "▦"),
    ("texts", "Texts", "☰"),
    ("works", "Works", "❦"),
    ("vocabularies", "Vocabularies", "≣"),
    ("relations", "Relations", "⁂"),
    ("chronology", "Chronology", "◔"),
    ("search", "Search", "⌕"),
    ("analytics", "Analytics", "◉"),
]


@bp.get("/")
def dashboard():
    db = get_db()
    return render_template("dashboard.html", nav=NAV, active="dashboard",
                           counts=models.dashboard_counts(db),
                           has_sample_data=project_lib.has_sample_data(db))


@bp.get("/objects")
def objects():
    db = get_db()
    return render_template("objects.html", nav=NAV, active="objects",
                           objects=models.list_objects(db))


@bp.get("/objects/<int:obj_id>")
def object_detail(obj_id):
    db = get_db()
    o = models.get_object_full(db, obj_id)
    if not o:
        abort(404)
    return render_template("object_detail.html", nav=NAV, active="objects", o=o)


@bp.get("/texts")
def texts():
    db = get_db()
    docs = [dict(r) for r in db.execute("""
        SELECT d.*, o.label AS object_label, o.record_kind AS object_kind, o.id AS object_id,
               (SELECT count(*) FROM text_version v WHERE v.text_document_id=d.id) AS n_versions
          FROM text_document d LEFT JOIN object o ON o.id=d.object_id
         WHERE d.is_active=1
         ORDER BY d.siglum, d.title
    """)]
    # Trova frammenti raggruppati sotto il loro oggetto ricostruito
    frag_to_parent = {}
    for r in db.execute("""
        SELECT orel.source_object_id AS frag_id,
               orel.target_object_id AS parent_id,
               orel.sequence,
               p.label AS parent_label
          FROM object_relation orel
          JOIN relation_type rt ON rt.id=orel.relation_type_id
          JOIN object p ON p.id=orel.target_object_id
         WHERE rt.code='FRAGMENT_OF'
    """):
        frag_to_parent[r["frag_id"]] = {
            "parent_id": r["parent_id"],
            "parent_label": r["parent_label"],
            "sequence": r["sequence"],
        }

    # Costruisci raggruppamenti
    groups = {}  # parent_id → { parent_label, fragments: [doc, ...], has_reconstructed: bool }
    standalone = []
    for d in docs:
        oid = d.get("object_id")
        if oid and oid in frag_to_parent:
            pinfo = frag_to_parent[oid]
            pid = pinfo["parent_id"]
            if pid not in groups:
                groups[pid] = {
                    "parent_id": pid,
                    "parent_label": pinfo["parent_label"],
                    "fragments": [],
                }
            d["_sequence"] = pinfo["sequence"]
            groups[pid]["fragments"].append(d)
        else:
            standalone.append(d)
    # Ordina i frammenti per sequence
    for g in groups.values():
        g["fragments"].sort(key=lambda x: x.get("_sequence") or 999)
    return render_template("texts.html", nav=NAV, active="texts",
                           docs=standalone, groups=list(groups.values()))


@bp.get("/annotate/<int:doc_id>")
def annotate(doc_id):
    db = get_db()
    doc = db.execute("SELECT * FROM text_document WHERE id=?", (doc_id,)).fetchone()
    if not doc:
        abort(404)
    version = models.current_version_for_document(db, doc_id, "transliteration") \
        or models.current_version_for_document(db, doc_id)
    versions = [dict(r) for r in db.execute(
        "SELECT id,version_type,version_number,is_current FROM text_version "
        "WHERE text_document_id=? ORDER BY version_number", (doc_id,))]
    return render_template("annotate.html", nav=NAV, active="texts",
                           doc=dict(doc), version=version, versions=versions)


@bp.get("/vocabularies")
def vocabularies():
    db = get_db()
    vocabs = {}
    for table, human in (("text_term", "Text"), ("object_term", "Object"),
                         ("context_term", "Context"), ("chronology_term", "Chronology")):
        type_col = "'period' AS term_type" if table == "chronology_term" else "term_type"
        vocabs[table] = {"human": human, "terms": [dict(r) for r in db.execute(
            f"SELECT id, preferred_label, {type_col} "
            f"FROM {table} WHERE is_active=1 ORDER BY preferred_label LIMIT 500")]}
    return render_template("vocabularies.html", nav=NAV, active="vocabularies", vocabs=vocabs)


@bp.get("/contexts")
def contexts():
    db = get_db()
    rows = [dict(r) for r in db.execute("SELECT * FROM context WHERE is_active=1 ORDER BY code")]
    return render_template("contexts.html", nav=NAV, active="contexts", contexts=rows)


@bp.get("/contexts/<int:ctx_id>")
def context_detail(ctx_id):
    db = get_db()
    ctx = models.get_context(db, ctx_id)
    if not ctx:
        abort(404)
    return render_template("context_detail.html", nav=NAV, active="contexts", ctx=ctx)


@bp.get("/chronology")
def chronology():
    db = get_db()
    rows = [dict(r) for r in db.execute(
        "SELECT * FROM chronology_term WHERE is_active=1 ORDER BY year_from")]
    return render_template("chronology.html", nav=NAV, active="chronology", terms=rows)


@bp.get("/relations")
def relations():
    db = get_db()
    return render_template("relations.html", nav=NAV, active="relations",
                           stats=models.graph_stats(db),
                           focus=models.default_focus_term(db))


@bp.get("/search")
def search():
    from flask import request
    q = (request.args.get("q") or "").strip()
    results = models.fulltext_search(get_db(), q) if q else []
    return render_template("search.html", nav=NAV, active="search", q=q, results=results)


@bp.get("/vocabularies/<int:term_id>")
def term_page(term_id):
    db = get_db()
    from .. import models
    d = models.get_term_detail(db, term_id)
    if not d:
        from flask import abort; abort(404)
    return render_template("term_detail.html", nav=NAV, active="vocabularies", t=d)


@bp.get("/vocab/<string:table>/<int:term_id>")
def generic_term_page(table, term_id):
    if table not in ("context_term", "object_term", "chronology_term"):
        from flask import abort; abort(404)
    db = get_db()
    from .. import models
    d = models.get_generic_term_detail(db, table, term_id)
    if not d:
        from flask import abort; abort(404)
    return render_template("term_detail_generic.html", nav=NAV, active="vocabularies",
                           t=d, table=table)


@bp.get("/analytics")
def analytics():
    return render_template("analytics.html", nav=NAV, active="analytics")


@bp.get("/reconstructed/<int:obj_id>")
def reconstructed_view(obj_id):
    """Vista ricostruita: mostra il testo intero ricomposto dai frammenti."""
    db = get_db()
    obj = db.execute("SELECT * FROM object WHERE id=?", (obj_id,)).fetchone()
    if not obj:
        return "Not found", 404
    from stele_app.models import get_reconstructed_text
    recon = get_reconstructed_text(db, obj_id)
    return render_template("reconstructed.html", nav=NAV, active="texts",
                           obj=dict(obj), recon=recon)


@bp.get("/works")
def works():
    """Elenca le opere intellettuali con numero testimoni."""
    from stele_app.models import list_works
    ws = list_works(get_db())
    return render_template("works.html", nav=NAV, active="works", works=ws)


@bp.get("/works/<int:work_id>")
def work_detail(work_id):
    """Dettaglio di un'opera con i suoi testimoni."""
    from stele_app.models import get_work
    w = get_work(get_db(), work_id)
    if not w:
        return "Not found", 404
    return render_template("work_detail.html", nav=NAV, active="works", work=w)
