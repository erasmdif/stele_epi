"""
Funzioni di accesso ai dati (repository leggero, niente ORM).
Include le CTE ricorsive sui vocabolari gerarchici N:M.
"""
from .db.geopackage import decode_point

RELATION_TABLE = {
    "text_term": "text_term_relation",
    "object_term": "object_term_relation",
    "context_term": "context_term_relation",
    "chronology_term": "chronology_term_relation",
}


def ancestors(conn, term_table, term_id, relation_codes=("IS_A", "PART_OF")):
    """Antenati di un termine risalendo le relazioni gerarchiche (CTE ricorsiva).
    Ritorna righe {id, preferred_label, depth, via} dal più vicino al più lontano."""
    rel_table = RELATION_TABLE[term_table]
    codes = ",".join("?" for _ in relation_codes)
    sql = f"""
    WITH RECURSIVE up(id, depth, via) AS (
        SELECT r.target_term_id, 1, rt.code
          FROM {rel_table} r JOIN relation_type rt ON rt.id = r.relation_type_id
         WHERE r.source_term_id = ? AND rt.code IN ({codes})
        UNION
        SELECT r.target_term_id, up.depth + 1, rt.code
          FROM {rel_table} r
          JOIN relation_type rt ON rt.id = r.relation_type_id
          JOIN up ON up.id = r.source_term_id
         WHERE rt.code IN ({codes})
    )
    SELECT t.id, t.preferred_label, up.depth, up.via
      FROM up JOIN {term_table} t ON t.id = up.id
     ORDER BY up.depth, t.preferred_label;
    """
    params = [term_id] + list(relation_codes) + list(relation_codes)
    return [dict(r) for r in conn.execute(sql, params)]


def descendants(conn, term_table, term_id, relation_codes=("IS_A", "PART_OF")):
    """Discendenti (verso il basso) di un termine."""
    rel_table = RELATION_TABLE[term_table]
    codes = ",".join("?" for _ in relation_codes)
    sql = f"""
    WITH RECURSIVE down(id, depth) AS (
        SELECT r.source_term_id, 1
          FROM {rel_table} r JOIN relation_type rt ON rt.id = r.relation_type_id
         WHERE r.target_term_id = ? AND rt.code IN ({codes})
        UNION
        SELECT r.source_term_id, down.depth + 1
          FROM {rel_table} r
          JOIN relation_type rt ON rt.id = r.relation_type_id
          JOIN down ON down.id = r.target_term_id
         WHERE rt.code IN ({codes})
    )
    SELECT t.id, t.preferred_label, down.depth
      FROM down JOIN {term_table} t ON t.id = down.id
     ORDER BY down.depth, t.preferred_label;
    """
    params = [term_id] + list(relation_codes) + list(relation_codes)
    return [dict(r) for r in conn.execute(sql, params)]


def term_neighbours(conn, term_table, term_id):
    """Tutte le relazioni dirette (in/out) di un termine, per il grafo."""
    rel_table = RELATION_TABLE[term_table]
    out = conn.execute(f"""
        SELECT r.target_term_id AS other_id, t.preferred_label AS other_label,
               rt.code AS rel, rt.label AS rel_label, 'out' AS dir
          FROM {rel_table} r JOIN relation_type rt ON rt.id=r.relation_type_id
          JOIN {term_table} t ON t.id=r.target_term_id
         WHERE r.source_term_id=?""", (term_id,)).fetchall()
    inc = conn.execute(f"""
        SELECT r.source_term_id AS other_id, t.preferred_label AS other_label,
               rt.code AS rel, COALESCE(rt.inverse_label, rt.label) AS rel_label, 'in' AS dir
          FROM {rel_table} r JOIN relation_type rt ON rt.id=r.relation_type_id
          JOIN {term_table} t ON t.id=r.source_term_id
         WHERE r.target_term_id=?""", (term_id,)).fetchall()
    return [dict(r) for r in out] + [dict(r) for r in inc]


# --- entità principali ------------------------------------------------------
def list_objects(conn, limit=200):
    return [dict(r) for r in conn.execute("""
        SELECT o.*, (SELECT count(*) FROM text_document d WHERE d.object_id=o.id) AS n_texts
          FROM object o WHERE o.is_active=1 ORDER BY o.label LIMIT ?""", (limit,))]


def get_object(conn, obj_id):
    o = conn.execute("SELECT * FROM object WHERE id=?", (obj_id,)).fetchone()
    if not o:
        return None
    o = dict(o)
    o["measurements"] = [dict(r) for r in conn.execute(
        "SELECT * FROM object_measurement WHERE object_id=?", (obj_id,))]
    o["terms"] = [dict(r) for r in conn.execute("""
        SELECT ot.id, ot.preferred_label, ot.term_type, c.label AS certainty
          FROM object_term_assignment a JOIN object_term ot ON ot.id=a.term_id
          LEFT JOIN certainty_level c ON c.id=a.certainty_id
         WHERE a.object_id=?""", (obj_id,))]
    # tipologia inferita (assegnati + antenati)
    inferred = []
    for t in o["terms"]:
        for anc in ancestors(conn, "object_term", t["id"]):
            inferred.append(anc["preferred_label"])
    o["inferred_types"] = sorted(set(inferred))
    o["components"] = [dict(r) for r in conn.execute("""
        SELECT o2.* FROM object_composition oc JOIN object o2 ON o2.id=oc.component_object_id
         WHERE oc.parent_object_id=?""", (obj_id,))]
    o["contexts"] = [dict(r) for r in conn.execute("""
        SELECT c.id, c.code, c.name, oc.relation_role FROM object_context oc
          JOIN context c ON c.id=oc.context_id WHERE oc.object_id=?""", (obj_id,))]
    o["relations"] = [dict(r) for r in conn.execute("""
        SELECT r.id, r.status, r.rationale, rt.code AS rel, rt.label AS rel_label,
               o2.id AS other_id, o2.label AS other_label, cl.label AS certainty
          FROM object_relation r JOIN relation_type rt ON rt.id=r.relation_type_id
          JOIN object o2 ON o2.id=r.target_object_id
          LEFT JOIN certainty_level cl ON cl.id=r.certainty_id
         WHERE r.source_object_id=?""", (obj_id,))]
    o["texts"] = [dict(r) for r in conn.execute(
        "SELECT * FROM text_document WHERE object_id=? AND is_active=1", (obj_id,))]
    o["chronology"] = [dict(r) for r in conn.execute("""
        SELECT oc.*, ct.preferred_label AS term_label FROM object_chronology oc
          LEFT JOIN chronology_term ct ON ct.id=oc.chronology_term_id WHERE oc.object_id=?""", (obj_id,))]
    return o


def get_text_version(conn, version_id):
    v = conn.execute("SELECT * FROM text_version WHERE id=?", (version_id,)).fetchone()
    return dict(v) if v else None


def current_version_for_document(conn, doc_id, version_type=None):
    q = "SELECT * FROM text_version WHERE text_document_id=? AND is_current=1"
    p = [doc_id]
    if version_type:
        q += " AND version_type=?"
        p.append(version_type)
    q += " ORDER BY version_number DESC LIMIT 1"
    r = conn.execute(q, p).fetchone()
    return dict(r) if r else None


def annotations_for_version(conn, version_id):
    """Ritorna le annotazioni con span e termini collegati (per il render stand-off)."""
    anns = [dict(r) for r in conn.execute("""
        SELECT a.*, cl.label AS certainty FROM annotation a
          LEFT JOIN certainty_level cl ON cl.id=a.certainty_id
         WHERE a.text_version_id=? ORDER BY a.id""", (version_id,))]
    for a in anns:
        a["spans"] = [dict(r) for r in conn.execute(
            "SELECT start_position,end_position,sequence FROM annotation_span "
            "WHERE annotation_id=? ORDER BY sequence,start_position", (a["id"],))]
        a["terms"] = [dict(r) for r in conn.execute("""
            SELECT t.id, t.preferred_label, t.term_type, at.role
              FROM annotation_term at JOIN text_term t ON t.id=at.term_id
             WHERE at.annotation_id=?""", (a["id"],))]
    return anns


def places_for_version(conn, version_id):
    """Luoghi (text_term_place) dei termini citati nelle annotazioni della versione."""
    rows = conn.execute("""
        SELECT DISTINCT t.id, t.preferred_label, p.geometry
          FROM annotation a JOIN annotation_term at ON at.annotation_id=a.id
          JOIN text_term t ON t.id=at.term_id
          JOIN text_term_place p ON p.term_id=t.id
         WHERE a.text_version_id=? AND t.term_type='place'""", (version_id,)).fetchall()
    out = []
    for r in rows:
        pt = decode_point(r["geometry"])
        if pt:
            out.append({"id": r["id"], "label": r["preferred_label"], "lon": pt[0], "lat": pt[1]})
    return out


def fulltext_search(conn, query, limit=50):
    return [dict(r) for r in conn.execute("""
        SELECT f.text_version_id, snippet(text_version_fts,0,'[',']','…',10) AS snip,
               v.version_type, d.title, d.id AS document_id
          FROM text_version_fts f
          JOIN text_version v ON v.id=f.text_version_id
          JOIN text_document d ON d.id=v.text_document_id
         WHERE text_version_fts MATCH ? LIMIT ?""", (query, limit))]


def dashboard_counts(conn):
    def c(t):
        return conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    return {t: c(t) for t in ("object", "context", "text_document", "text_version",
                              "annotation", "text_term", "object_term", "context_term",
                              "chronology_term", "bibliography", "media")}


# ---------------------------------------------------------------------------
# Grafo delle relazioni fra termini del testo (rete semantica + co-occorrenze)
# ---------------------------------------------------------------------------
def ego_graph(conn, focus_id, depth=2, kinds=("relation", "cooccur")):
    """Ego-network attorno a un text_term.
    - 'relation': archi tipizzati da text_term_relation (BFS fino a depth).
    - 'cooccur' : archi di co-occorrenza (termini che compaiono in annotazioni
      della stessa text_version del focus) — solo a distanza 1 dal focus.
    Ritorna {focus, nodes:[{id,label,type,is_focus,degree}], edges:[...]}.
    """
    focus = conn.execute("SELECT id,preferred_label,term_type FROM text_term WHERE id=?", (focus_id,)).fetchone()
    if not focus:
        return {"focus": None, "nodes": [], "edges": []}
    nodes = {}
    edges = []
    seen_edge = set()

    def add_node(row, is_focus=False):
        if row["id"] not in nodes:
            nodes[row["id"]] = {"id": row["id"], "label": row["preferred_label"],
                                "type": row["term_type"], "is_focus": is_focus, "degree": 0}

    def add_edge(s, t, rel, label, kind, hierarchical=0):
        key = (min(s, t), max(s, t), rel, kind)
        if key in seen_edge:
            return
        seen_edge.add(key)
        edges.append({"source": s, "target": t, "rel": rel, "label": label,
                      "kind": kind, "hierarchical": hierarchical})
        if s in nodes:
            nodes[s]["degree"] += 1
        if t in nodes:
            nodes[t]["degree"] += 1

    add_node(focus, is_focus=True)

    if "relation" in kinds:
        frontier = [focus_id]
        for _ in range(max(1, depth)):
            nxt = []
            for nid in frontier:
                rows = conn.execute("""
                    SELECT r.source_term_id AS s, r.target_term_id AS t, rt.code AS rel,
                           rt.label AS label, rt.is_hierarchical AS h,
                           ts.preferred_label AS s_label, ts.term_type AS s_type,
                           tt.preferred_label AS t_label, tt.term_type AS t_type
                      FROM text_term_relation r
                      JOIN relation_type rt ON rt.id=r.relation_type_id
                      JOIN text_term ts ON ts.id=r.source_term_id
                      JOIN text_term tt ON tt.id=r.target_term_id
                     WHERE r.source_term_id=? OR r.target_term_id=?""", (nid, nid)).fetchall()
                for r in rows:
                    add_node({"id": r["s"], "preferred_label": r["s_label"], "term_type": r["s_type"]})
                    add_node({"id": r["t"], "preferred_label": r["t_label"], "term_type": r["t_type"]})
                    add_edge(r["s"], r["t"], r["rel"], r["label"], "relation", r["h"])
                    other = r["t"] if r["s"] == nid else r["s"]
                    nxt.append(other)
            frontier = [n for n in set(nxt) if n not in frontier]

    if "cooccur" in kinds:
        rows = conn.execute("""
            SELECT DISTINCT t2.id AS id, t2.preferred_label AS label, t2.term_type AS type
              FROM annotation a1
              JOIN annotation_term at1 ON at1.annotation_id=a1.id AND at1.term_id=?
              JOIN annotation a2 ON a2.text_version_id=a1.text_version_id
              JOIN annotation_term at2 ON at2.annotation_id=a2.id
              JOIN text_term t2 ON t2.id=at2.term_id
             WHERE t2.id<>?""", (focus_id, focus_id)).fetchall()
        for r in rows:
            add_node({"id": r["id"], "preferred_label": r["label"], "term_type": r["type"]})
            add_edge(focus_id, r["id"], "COOCCURS", "co-occorre", "cooccur", 0)

    return {"focus": {"id": focus["id"], "label": focus["preferred_label"], "type": focus["term_type"]},
            "nodes": list(nodes.values()), "edges": edges}


def graph_stats(conn):
    return {
        "text_terms": conn.execute("SELECT count(*) FROM text_term").fetchone()[0],
        "relations": conn.execute("SELECT count(*) FROM text_term_relation").fetchone()[0],
        "hierarchical": conn.execute("""SELECT count(*) FROM text_term_relation r
            JOIN relation_type rt ON rt.id=r.relation_type_id WHERE rt.is_hierarchical=1""").fetchone()[0],
    }


def default_focus_term(conn):
    """Un termine con relazioni, per aprire il grafo su qualcosa di significativo."""
    r = conn.execute("""SELECT t.id FROM text_term t
        JOIN text_term_relation r ON r.source_term_id=t.id OR r.target_term_id=t.id
        GROUP BY t.id ORDER BY count(*) DESC LIMIT 1""").fetchone()
    if r:
        return r["id"]
    r = conn.execute("SELECT id FROM text_term ORDER BY id LIMIT 1").fetchone()
    return r["id"] if r else None


# ---------------------------------------------------------------------------
# Scheda-record del dizionario testuale (text_term)
# ---------------------------------------------------------------------------
def get_term_detail(conn, term_id):
    """Tutto ciò che serve alla scheda di un text_term: dati, label alternative,
    ID esterni, geometria (se place), vicini della rete, antenati e discendenti,
    e le occorrenze nei testi (annotazioni che lo riferiscono)."""
    t = conn.execute("SELECT * FROM text_term WHERE id=?", (term_id,)).fetchone()
    if not t:
        return None
    out = dict(t)
    out["labels"] = [dict(r) for r in conn.execute(
        "SELECT id,language,label,label_type,script,is_preferred "
        "FROM text_term_label WHERE term_id=? ORDER BY is_preferred DESC,label", (term_id,))]
    out["external_ids"] = [dict(r) for r in conn.execute(
        "SELECT id,authority,identifier,uri,note FROM text_term_external_id WHERE term_id=?", (term_id,))]
    out["neighbours"] = term_neighbours(conn, "text_term", term_id)
    out["ancestors"] = ancestors(conn, "text_term", term_id)
    out["descendants"] = descendants(conn, "text_term", term_id)
    if out["term_type"] == "place":
        pr = conn.execute("SELECT geometry,geometry_precision,geometry_source,note "
                          "FROM text_term_place WHERE term_id=?", (term_id,)).fetchone()
        if pr and pr["geometry"]:
            pt = decode_point(pr["geometry"])
            if pt:
                out["place"] = {"lon": pt[0], "lat": pt[1],
                                "precision": pr["geometry_precision"],
                                "source": pr["geometry_source"], "note": pr["note"]}
    out["occurrences"] = [dict(r) for r in conn.execute("""
        SELECT a.id AS annotation_id, a.annotation_type, a.text_version_id,
               d.id AS document_id, d.siglum, d.title,
               s.start_position, s.end_position, v.content
          FROM annotation_term at
          JOIN annotation a ON a.id=at.annotation_id
          JOIN text_version v ON v.id=a.text_version_id
          JOIN text_document d ON d.id=v.text_document_id
          LEFT JOIN annotation_span s ON s.annotation_id=a.id
         WHERE at.term_id=?
         GROUP BY a.id
         ORDER BY d.siglum, a.id""", (term_id,))]
    return out


# ---------------------------------------------------------------------------
# Vista parallela: versioni di un text_document, con allineamento a gruppi.
# Le righe (text_unit) di una versione principale (primary) sono affiancate
# alle text_unit corrispondenti nelle altre versioni tramite text_unit_alignment.
# ---------------------------------------------------------------------------
def document_versions(conn, doc_id):
    return [dict(r) for r in conn.execute(
        "SELECT id,version_type,version_number,language,script,is_current,note "
        "FROM text_version WHERE text_document_id=? ORDER BY version_type,version_number", (doc_id,))]


def primary_version(conn, doc_id):
    """Convenzione: la diplomatic_transcription è la primaria; altrimenti la prima corrente."""
    for vt in ("diplomatic_transcription", "transliteration"):
        r = conn.execute(
            "SELECT * FROM text_version WHERE text_document_id=? AND version_type=? AND is_current=1 "
            "ORDER BY version_number DESC LIMIT 1", (doc_id, vt)).fetchone()
        if r: return dict(r)
    r = conn.execute(
        "SELECT * FROM text_version WHERE text_document_id=? AND is_current=1 "
        "ORDER BY version_number DESC LIMIT 1", (doc_id,)).fetchone()
    return dict(r) if r else None


def _line_bounds(content):
    """Ritorna [(start_cp, end_cp), ...] per ogni riga (in code point)."""
    cp = list(content or "")
    out, s = [], 0
    for i, c in enumerate(cp):
        if c == "\n":
            out.append((s, i)); s = i + 1
    out.append((s, len(cp)))
    return out


def parallel_view(conn, doc_id, active_version_types=None):
    """Costruisce la vista affiancata per riga.
    Ritorna:
      {
        'primary': {id, version_type, ...},
        'versions': [{id, version_type, language, is_current, ...}],
        'rows': [
           {'group_id': N, 'primary_line_idx': i,
            'cells': [{version_id, version_type, unit_id, text, ann_count}]},
           ...
        ]
      }
    L'annotazione avviene sempre sulla versione primaria (diplomatica).
    Per le versioni parallele, ann_count è il numero di annotazioni sulla
    corrispondente riga della primaria (marcatore discreto).
    """
    prim = primary_version(conn, doc_id)
    if not prim:
        return None
    vers_all = document_versions(conn, doc_id)
    if active_version_types is None:
        active_version_types = [v["version_type"] for v in vers_all]
    # includi sempre la primaria fra le attive
    if prim["version_type"] not in active_version_types:
        active_version_types = [prim["version_type"]] + list(active_version_types)

    # righe della primaria come base
    prim_lines = _line_bounds(prim["content"] or "")
    prim_units = [dict(r) for r in conn.execute(
        "SELECT * FROM text_unit WHERE text_version_id=? AND unit_type='line' ORDER BY sequence",
        (prim["id"],))]
    # per ogni riga primaria: quali annotazioni la coprono
    ann_count_by_line = [0] * len(prim_lines)
    for a in conn.execute("""SELECT s.start_position, s.end_position FROM annotation a
        JOIN annotation_span s ON s.annotation_id=a.id WHERE a.text_version_id=?""", (prim["id"],)):
        for i, (ls, le) in enumerate(prim_lines):
            if a["start_position"] < le and a["end_position"] > ls:
                ann_count_by_line[i] += 1

    # unità per ciascuna versione attiva, indicizzate per group_id
    other_versions = [v for v in vers_all if v["version_type"] in active_version_types
                      and v["id"] != prim["id"]]
    version_by_id = {v["id"]: v for v in vers_all}

    # mappa: primary_unit_id -> group_id
    unit_to_group = {}
    for r in conn.execute("SELECT group_id, text_unit_id, role FROM text_unit_alignment"):
        unit_to_group.setdefault(r["text_unit_id"], []).append((r["group_id"], r["role"]))
    # mappa: group_id -> [text_unit_id]
    group_to_units = {}
    for r in conn.execute("SELECT group_id, text_unit_id FROM text_unit_alignment"):
        group_to_units.setdefault(r["group_id"], []).append(r["text_unit_id"])
    # tutte le text_unit toccate
    all_uids = {u for uids in group_to_units.values() for u in uids} | {u["id"] for u in prim_units}
    unit_by_id = {}
    if all_uids:
        placeholders = ",".join("?" for _ in all_uids)
        for r in conn.execute(f"SELECT * FROM text_unit WHERE id IN ({placeholders})", tuple(all_uids)):
            unit_by_id[r["id"]] = dict(r)
    # contenuto per riga per ciascuna versione — carico i content on-demand
    contents = {}
    def line_text(version_id, seq):
        if version_id not in contents:
            r = conn.execute("SELECT content FROM text_version WHERE id=?", (version_id,)).fetchone()
            contents[version_id] = (r["content"] if r else "") or ""
        lines = contents[version_id].split("\n")
        return lines[seq - 1] if 0 <= seq - 1 < len(lines) else ""

    rows = []
    for i, pu in enumerate(prim_units):
        groups = unit_to_group.get(pu["id"], [])
        # cerca il gruppo con questa unità come primary; se assente, prendi il primo
        gid = None
        for g, role in groups:
            if role == "primary":
                gid = g; break
        if gid is None and groups:
            gid = groups[0][0]

        cells = [{
            "version_id": prim["id"], "version_type": prim["version_type"],
            "language": prim.get("language"), "unit_id": pu["id"],
            "seq": pu["sequence"], "text": line_text(prim["id"], pu["sequence"]),
            "role": "primary", "ann_count": ann_count_by_line[i] if i < len(ann_count_by_line) else 0,
            "is_primary_version": True,
        }]
        seen = {prim["id"]}
        if gid is not None:
            for uid in group_to_units.get(gid, []):
                u = unit_by_id.get(uid)
                if not u: continue
                if u["text_version_id"] in seen: continue
                v = version_by_id.get(u["text_version_id"])
                if not v or v["version_type"] not in active_version_types: continue
                cells.append({
                    "version_id": v["id"], "version_type": v["version_type"],
                    "language": v.get("language"), "unit_id": u["id"],
                    "seq": u["sequence"], "text": line_text(v["id"], u["sequence"]),
                    "role": "parallel",
                    "ann_count": ann_count_by_line[i] if i < len(ann_count_by_line) else 0,
                    "is_primary_version": False,
                })
                seen.add(v["id"])
        rows.append({"group_id": gid, "primary_line_idx": i, "cells": cells})

    return {
        "document_id": doc_id,
        "primary": {"id": prim["id"], "version_type": prim["version_type"],
                    "language": prim.get("language"), "script": prim.get("script")},
        "versions": vers_all,
        "active": active_version_types,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Scheda-record generica per vocabolari (context_term, object_term, chronology_term)
# ---------------------------------------------------------------------------
# Metadati per ciascun vocabolario: come si trovano occorrenze, chi ha label,
# quali colonne extra ci sono (year_from/year_to per chronology, ecc.)
VOCAB_META = {
    "context_term": {
        "human": "Context vocabulary",
        "has_labels": True,           # ha una tabella <table>_label per etichette alt.
        "assignment_table": "context_term_assignment",
        "assignment_owner": "context_id",
        "owner_table": "context",
        "owner_label_cols": ("code", "name"),
        "extra_cols": (),
    },
    "object_term": {
        "human": "Object vocabulary",
        "has_labels": True,
        "assignment_table": "object_term_assignment",
        "assignment_owner": "object_id",
        "owner_table": "object",
        "owner_label_cols": ("inventory_number", "label"),
        "extra_cols": (),
    },
    "chronology_term": {
        "human": "Chronology vocabulary",
        "has_labels": False,          # non ha una tabella di label alternative
        # cronologia ha DUE tabelle di uso (context_chronology e object_chronology)
        "assignment_table": None,     # gestito a parte
        "extra_cols": ("year_from", "year_to", "precision"),
    },
}


def get_generic_term_detail(conn, table, term_id):
    """Analogo di get_term_detail per vocabolari non-testuali. Ritorna
    identità, relazioni (rete N:M), occorrenze reali (dove il termine è
    assegnato a un context/object) o usi (per chronology)."""
    if table not in VOCAB_META:
        return None
    meta = VOCAB_META[table]
    t = conn.execute(f"SELECT * FROM {table} WHERE id=?", (term_id,)).fetchone()
    if not t:
        return None
    out = dict(t)
    out["_meta"] = meta
    out["_table"] = table

    # etichette alternative (solo dove esiste la tabella)
    if meta["has_labels"]:
        # le tabelle <table>_label hanno FK <table>_id (non term_id) e non hanno script
        fk_col = f"{table}_id"
        rows = conn.execute(f"SELECT id,language,label,label_type,is_preferred "
                            f"FROM {table}_label WHERE {fk_col}=? "
                            f"ORDER BY is_preferred DESC,label",
                            (term_id,)).fetchall()
        out["labels"] = [dict(r) for r in rows]
    else:
        out["labels"] = []

    # rete semantica (funziona uniformemente per tutte le tabelle di vocab)
    out["neighbours"] = term_neighbours(conn, table, term_id)
    out["ancestors"] = ancestors(conn, table, term_id)
    out["descendants"] = descendants(conn, table, term_id)

    # occorrenze
    if table == "chronology_term":
        # usato in context_chronology e object_chronology
        rows_c = conn.execute("""SELECT cc.id AS use_id, cc.dating_method, cc.absolute_from, cc.absolute_to,
                                        c.id AS owner_id, c.code, c.name
                                   FROM context_chronology cc
                                   JOIN context c ON c.id=cc.context_id
                                  WHERE cc.chronology_term_id=?""", (term_id,)).fetchall()
        rows_o = conn.execute("""SELECT oc.id AS use_id, oc.dating_method, oc.absolute_from, oc.absolute_to,
                                        o.id AS owner_id, o.inventory_number AS code, o.label AS name
                                   FROM object_chronology oc
                                   JOIN object o ON o.id=oc.object_id
                                  WHERE oc.chronology_term_id=?""", (term_id,)).fetchall()
        out["occurrences"] = ([{"owner_kind": "context", **dict(r)} for r in rows_c]
                              + [{"owner_kind": "object", **dict(r)} for r in rows_o])
    else:
        # context_term_assignment o object_term_assignment
        owner = meta["assignment_owner"]
        owner_table = meta["owner_table"]
        cols = meta["owner_label_cols"]
        col_expr = ",".join(f"o.{c}" for c in cols)
        rows = conn.execute(f"""SELECT a.id AS use_id, a.note, {col_expr},
                                       o.id AS owner_id
                                  FROM {meta['assignment_table']} a
                                  JOIN {owner_table} o ON o.id=a.{owner}
                                 WHERE a.term_id=?""", (term_id,)).fetchall()
        out["occurrences"] = [{"owner_kind": owner_table, **dict(r)} for r in rows]
    return out


def search_generic_terms(conn, table, q, limit=20):
    """Come mutations.search_text_terms ma per una tabella di vocabolario qualsiasi."""
    q = (q or "").strip()
    has_type = any(r["name"] == "term_type" for r in conn.execute(f"PRAGMA table_info({table})"))
    cols = "id, preferred_label" + (", term_type" if has_type else "")
    if not q:
        rows = conn.execute(f"SELECT {cols} FROM {table} WHERE is_active=1 "
                            f"ORDER BY preferred_label LIMIT ?", (limit,))
    else:
        rows = conn.execute(f"SELECT {cols} FROM {table} WHERE is_active=1 AND preferred_label LIKE ? "
                            f"ORDER BY preferred_label LIMIT ?", ("%" + q + "%", limit))
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Iterazione 2 · Scheda contesto (completa)
# ---------------------------------------------------------------------------
def list_contexts(conn, limit=200):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM context WHERE is_active=1 ORDER BY code LIMIT ?", (limit,))]


def get_context(conn, ctx_id):
    ctx = conn.execute("SELECT * FROM context WHERE id=?", (ctx_id,)).fetchone()
    if not ctx:
        return None
    ctx = dict(ctx)
    # geometria
    if ctx.get("geometry"):
        try:
            pt = decode_point(ctx["geometry"])
            if pt:
                ctx["point"] = {"lon": pt[0], "lat": pt[1]}
        except Exception:
            pass
    ctx.pop("geometry", None)  # non serializzabile
    # termini assegnati
    ctx["terms"] = [dict(r) for r in conn.execute("""
        SELECT a.id AS assignment_id, ct.id, ct.preferred_label, ct.term_type,
               cl.label AS certainty
          FROM context_term_assignment a
          JOIN context_term ct ON ct.id=a.term_id
          LEFT JOIN certainty_level cl ON cl.id=a.certainty_id
         WHERE a.context_id=?""", (ctx_id,))]
    # tipologia inferita
    inferred = []
    for t in ctx["terms"]:
        for anc in ancestors(conn, "context_term", t["id"]):
            inferred.append(anc["preferred_label"])
    ctx["inferred_types"] = sorted(set(inferred))
    # oggetti trovati nel contesto
    ctx["objects"] = [dict(r) for r in conn.execute("""
        SELECT o.id, o.inventory_number, o.label, oc.relation_role
          FROM object_context oc JOIN object o ON o.id=oc.object_id
         WHERE oc.context_id=?""", (ctx_id,))]
    # datazioni
    ctx["chronology"] = [dict(r) for r in conn.execute("""
        SELECT cc.*, ct.preferred_label AS term_label,
               ct.year_from AS term_year_from, ct.year_to AS term_year_to,
               cl.label AS certainty
          FROM context_chronology cc
          LEFT JOIN chronology_term ct ON ct.id=cc.chronology_term_id
          LEFT JOIN certainty_level cl ON cl.id=cc.certainty_id
         WHERE cc.context_id=? ORDER BY cc.absolute_from""", (ctx_id,))]
    # bibliografia
    ctx["bibliography"] = [dict(r) for r in conn.execute("""
        SELECT cb.id AS link_id, cb.locator, cb.role, cb.note, b.*
          FROM context_bibliography cb JOIN bibliography b ON b.id=cb.bibliography_id
         WHERE cb.context_id=?""", (ctx_id,))]
    return ctx


# scheda oggetto arricchita: aggiungo bibliografia (ora esposta) e datazioni con term label
def get_object_full(conn, obj_id):
    """Come get_object ma con bibliografia + datazioni arricchite dai term."""
    o = get_object(conn, obj_id)
    if not o:
        return None
    # ricalcolo chronology con dati del termine
    o["chronology"] = [dict(r) for r in conn.execute("""
        SELECT oc.*, ct.preferred_label AS term_label,
               ct.year_from AS term_year_from, ct.year_to AS term_year_to,
               cl.label AS certainty
          FROM object_chronology oc
          LEFT JOIN chronology_term ct ON ct.id=oc.chronology_term_id
          LEFT JOIN certainty_level cl ON cl.id=oc.certainty_id
         WHERE oc.object_id=? ORDER BY oc.absolute_from""", (obj_id,))]
    o["bibliography"] = [dict(r) for r in conn.execute("""
        SELECT ob.id AS link_id, ob.locator, ob.role, ob.note, b.*
          FROM object_bibliography ob JOIN bibliography b ON b.id=ob.bibliography_id
         WHERE ob.object_id=?""", (obj_id,))]
    return o


# ============================================================================
# ANALYTICS — query per la dashboard analitica
# ============================================================================

def analytics_semantic_search(conn, term_id, *, deposit_type=None,
                               year_from=None, year_to=None):
    """Ricerca semantica gerarchica: dato un termine, cerca tutte le
    annotazioni che puntano a quel termine o ai suoi discendenti.
    Restituisce i documenti trovati con contesto, oggetto, cronologia."""
    # 1. discendenti del termine (incluso se stesso)
    desc = descendants(conn, "text_term", term_id)
    term_ids = [term_id] + [d["id"] for d in desc]
    ph = ",".join("?" for _ in term_ids)

    sql = f"""
    SELECT DISTINCT
        td.id AS doc_id, td.siglum, td.title,
        o.id AS object_id, o.label AS object_label,
        o.inventory_number,
        c.id AS context_id, c.code AS context_code, c.name AS context_name,
        c.deposit_type, c.excavation_technique,
        tt.id AS term_id, tt.preferred_label AS matched_term,
        a.annotation_type, a.id AS annotation_id,
        tv.content AS version_content, tv.version_type,
        asp.start_position, asp.end_position
      FROM annotation_term at2
      JOIN annotation a ON a.id = at2.annotation_id
      JOIN annotation_span asp ON asp.annotation_id = a.id
      JOIN text_version tv ON tv.id = a.text_version_id
      JOIN text_document td ON td.id = tv.text_document_id
      JOIN text_term tt ON tt.id = at2.term_id
      LEFT JOIN object o ON o.id = td.object_id
      LEFT JOIN object_context oc ON oc.object_id = o.id
      LEFT JOIN context c ON c.id = oc.context_id
     WHERE at2.term_id IN ({ph})
       AND a.status = 'accepted'
    """
    params = list(term_ids)
    if deposit_type:
        sql += " AND c.deposit_type = ?"
        params.append(deposit_type)
    if year_from is not None:
        sql += """
        AND EXISTS (
            SELECT 1 FROM object_chronology och
             WHERE och.object_id = o.id
               AND och.absolute_to >= ?
        )"""
        params.append(year_from)
    if year_to is not None:
        sql += """
        AND EXISTS (
            SELECT 1 FROM object_chronology och
             WHERE och.object_id = o.id
               AND och.absolute_from <= ?
        )"""
        params.append(year_to)
    sql += " ORDER BY td.siglum, asp.start_position"
    return [dict(r) for r in conn.execute(sql, params)]


def analytics_cooccurrence(conn, *, scope="version", min_count=1):
    """Grafo delle co-occorrenze: coppie di termini annotati nella
    stessa unità (scope='unit') o nello stesso text_version (scope='version').
    Ritorna nodes:[{id,label,count}] e edges:[{source,target,weight}]."""
    if scope == "unit":
        sql = """
        SELECT at1.term_id AS t1, at2.term_id AS t2, COUNT(*) AS w
          FROM annotation_term at1
          JOIN annotation a1 ON a1.id = at1.annotation_id AND a1.status='accepted'
          JOIN annotation_span asp1 ON asp1.annotation_id = a1.id
          JOIN annotation_term at2
          JOIN annotation a2 ON a2.id = at2.annotation_id AND a2.status='accepted'
          JOIN annotation_span asp2 ON asp2.annotation_id = a2.id
         WHERE a1.text_version_id = a2.text_version_id
           AND at1.term_id < at2.term_id
           AND EXISTS (
               SELECT 1 FROM text_unit tu
                WHERE tu.text_version_id = a1.text_version_id
                  AND asp1.start_position >= tu.start_position
                  AND asp1.end_position   <= tu.end_position
                  AND asp2.start_position >= tu.start_position
                  AND asp2.end_position   <= tu.end_position
           )
         GROUP BY at1.term_id, at2.term_id
        HAVING COUNT(*) >= ?
        """
    else:
        sql = """
        SELECT at1.term_id AS t1, at2.term_id AS t2, COUNT(*) AS w
          FROM annotation_term at1
          JOIN annotation a1 ON a1.id = at1.annotation_id AND a1.status='accepted'
          JOIN annotation_term at2
          JOIN annotation a2 ON a2.id = at2.annotation_id AND a2.status='accepted'
         WHERE a1.text_version_id = a2.text_version_id
           AND at1.term_id < at2.term_id
         GROUP BY at1.term_id, at2.term_id
        HAVING COUNT(*) >= ?
        """
    edges = [dict(r) for r in conn.execute(sql, (min_count,))]
    # raccogli nodi unici
    node_ids = set()
    for e in edges:
        node_ids.add(e["t1"])
        node_ids.add(e["t2"])
    if not node_ids:
        return {"nodes": [], "edges": []}
    ph = ",".join("?" for _ in node_ids)
    nodes_raw = conn.execute(f"""
        SELECT tt.id, tt.preferred_label AS label,
               COUNT(at2.id) AS total_annotations
          FROM text_term tt
          LEFT JOIN annotation_term at2 ON at2.term_id = tt.id
         WHERE tt.id IN ({ph})
         GROUP BY tt.id
    """, list(node_ids)).fetchall()
    nodes = [dict(r) for r in nodes_raw]
    return {
        "nodes": nodes,
        "edges": [{"source": e["t1"], "target": e["t2"], "weight": e["w"]}
                  for e in edges]
    }


def analytics_text_concept_matrix(conn):
    """Matrice testi × categorie concettuali. Per ogni documento,
    conta quante annotazioni appartengono a ciascun ramo semantico
    di primo livello (termini radice, esclusi i nomi propri di persona)."""
    # 1. Trova radici (termini senza IS_A verso l'alto, no person)
    roots_sql = """
        SELECT id, preferred_label FROM text_term
         WHERE id NOT IN (
             SELECT r.source_term_id FROM text_term_relation r
               JOIN relation_type rt ON rt.id = r.relation_type_id
              WHERE rt.code = 'IS_A'
         )
           AND term_type != 'person'
         ORDER BY preferred_label
    """
    roots = [dict(r) for r in conn.execute(roots_sql)]

    # 2. Per ciascuna radice, trova i discendenti
    root_to_terms = {}
    for root in roots:
        desc = descendants(conn, "text_term", root["id"],
                           relation_codes=("IS_A",))
        term_ids = [root["id"]] + [d["id"] for d in desc]
        root_to_terms[root["id"]] = term_ids

    # 3. Per ciascun documento, conta le annotazioni in ciascun ramo
    docs = [dict(r) for r in conn.execute("""
        SELECT id, siglum, title FROM text_document ORDER BY siglum
    """)]

    matrix = []
    for doc in docs:
        row = {"doc_id": doc["id"],
               "siglum": doc["siglum"] or doc["title"] or f"Doc {doc['id']}",
               "counts": {}}
        for root in roots:
            term_ids = root_to_terms[root["id"]]
            ph = ",".join("?" for _ in term_ids)
            cnt = conn.execute(f"""
                SELECT COUNT(DISTINCT a.id) FROM annotation a
                  JOIN annotation_term at2 ON at2.annotation_id = a.id
                  JOIN text_version tv ON tv.id = a.text_version_id
                 WHERE tv.text_document_id = ?
                   AND at2.term_id IN ({ph})
                   AND a.status = 'accepted'
            """, [doc["id"]] + term_ids).fetchone()[0]
            row["counts"][root["preferred_label"]] = cnt
        matrix.append(row)

    return {"columns": [r["preferred_label"] for r in roots],
            "rows": matrix}


def analytics_text_archaeology_cross(conn):
    """Incrocio contenuto testuale × realtà archeologica.
    Matrice: rami semantici (righe) × deposit_type dei contesti (colonne).
    Conta le annotazioni distinte per ciascuna cella. Esclude i nomi
    propri di persona dalle righe."""
    # Radici semantiche (escluse le persone)
    roots_sql = """
        SELECT id, preferred_label FROM text_term
         WHERE id NOT IN (
             SELECT r.source_term_id FROM text_term_relation r
               JOIN relation_type rt ON rt.id = r.relation_type_id
              WHERE rt.code = 'IS_A'
         )
           AND term_type != 'person'
         ORDER BY preferred_label
    """
    roots = [dict(r) for r in conn.execute(roots_sql)]
    root_to_terms = {}
    for root in roots:
        desc = descendants(conn, "text_term", root["id"],
                           relation_codes=("IS_A",))
        root_to_terms[root["id"]] = [root["id"]] + [d["id"] for d in desc]

    # Tipi di deposito presenti
    dep_types = [r[0] for r in conn.execute("""
        SELECT DISTINCT deposit_type FROM context
         WHERE deposit_type IS NOT NULL ORDER BY deposit_type
    """)]

    matrix = []
    for root in roots:
        row = {"category": root["preferred_label"], "counts": {}}
        term_ids = root_to_terms[root["id"]]
        ph = ",".join("?" for _ in term_ids)
        for dt in dep_types:
            cnt = conn.execute(f"""
                SELECT COUNT(DISTINCT a.id)
                  FROM annotation a
                  JOIN annotation_term at2 ON at2.annotation_id = a.id
                  JOIN text_version tv ON tv.id = a.text_version_id
                  JOIN text_document td ON td.id = tv.text_document_id
                  JOIN object o ON o.id = td.object_id
                  JOIN object_context oc ON oc.object_id = o.id
                  JOIN context c ON c.id = oc.context_id
                 WHERE at2.term_id IN ({ph})
                   AND c.deposit_type = ?
                   AND a.status = 'accepted'
            """, term_ids + [dt]).fetchone()[0]
            row["counts"][dt] = cnt
        matrix.append(row)

    return {"columns": dep_types, "rows": matrix}




# ============================================================================
# FRAGMENTS — vista ricostruita da frammenti
# ============================================================================

def get_fragments(conn, parent_object_id):
    """Restituisce i frammenti di un oggetto ricostruito, ordinati per sequence.
    Usa object_relation con FRAGMENT_OF, oppure object_composition come fallback."""
    # Prova FRAGMENT_OF relation
    frags = [dict(r) for r in conn.execute("""
        SELECT o.id, o.uid, o.inventory_number, o.label, o.record_kind,
               o.description, o.completeness_percentage,
               orel.sequence, orel.id AS relation_id
          FROM object_relation orel
          JOIN relation_type rt ON rt.id = orel.relation_type_id
          JOIN object o ON o.id = orel.source_object_id
         WHERE orel.target_object_id = ?
           AND rt.code = 'FRAGMENT_OF'
         ORDER BY COALESCE(orel.sequence, 999), o.label
    """, (parent_object_id,))]
    if frags:
        return frags
    # Fallback: object_composition
    return [dict(r) for r in conn.execute("""
        SELECT o.id, o.uid, o.inventory_number, o.label, o.record_kind,
               o.description, o.completeness_percentage,
               oc.id AS relation_id, NULL AS sequence
          FROM object_composition oc
          JOIN object o ON o.id = oc.component_object_id
         WHERE oc.parent_object_id = ?
         ORDER BY o.label
    """, (parent_object_id,))]


def get_reconstructed_text(conn, parent_object_id):
    """Vista ricostruita: aggrega i text_document dai frammenti in ordine.
    Restituisce una struttura con i frammenti e i loro testi, più una
    vista combinata per ciascun version_type."""
    frags = get_fragments(conn, parent_object_id)
    if not frags:
        return None

    fragments_data = []
    all_version_types = set()

    for frag in frags:
        docs = [dict(r) for r in conn.execute("""
            SELECT id, siglum, title, surface, position_on_object
              FROM text_document WHERE object_id = ?
        """, (frag["id"],))]
        frag_info = {
            "fragment": frag,
            "documents": []
        }
        for doc in docs:
            versions = [dict(r) for r in conn.execute("""
                SELECT id, version_type, content, language, script,
                       version_number, is_current
                  FROM text_version
                 WHERE text_document_id = ? AND is_current = 1
                 ORDER BY version_type
            """, (doc["id"],))]
            doc["versions"] = versions
            for v in versions:
                all_version_types.add(v["version_type"])
            frag_info["documents"].append(doc)
        fragments_data.append(frag_info)

    # Costruisci vista combinata per ciascun version_type
    combined = {}
    for vtype in sorted(all_version_types):
        parts = []
        for frag_info in fragments_data:
            for doc in frag_info["documents"]:
                for v in doc["versions"]:
                    if v["version_type"] == vtype and v["content"]:
                        parts.append({
                            "fragment_label": frag_info["fragment"]["label"],
                            "fragment_id": frag_info["fragment"]["id"],
                            "doc_id": doc["id"],
                            "version_id": v["id"],
                            "content": v["content"],
                        })
        if parts:
            combined[vtype] = {
                "parts": parts,
                "full_text": "\n".join(p["content"] for p in parts),
            }

    return {
        "parent_object_id": parent_object_id,
        "fragments": fragments_data,
        "combined": combined,
        "version_types": sorted(all_version_types),
    }


# ============================================================================
# ANALYTICS FASE 3 — spazio-temporale, formule/paralleli, timeline
# ============================================================================

def analytics_spatiotemporal(conn, *, term_id=None, year_from=None,
                              year_to=None, mode="findspot"):
    """Distribuzione spazio-temporale delle attestazioni.

    mode='findspot' → coordinate del contesto di rinvenimento
    mode='mention' → coordinate dei luoghi menzionati nel testo (text_term_place)

    Se term_id è passato, filtra alle attestazioni di quel termine (con gerarchia).
    year_from/year_to filtrano per range cronologico.

    Ritorna: [{lat, lon, siglum, object_label, matched_term, year_from, year_to,
              context_name, deposit_type, precision, doc_id}]
    """
    from .db import geopackage as gpkg

    if mode == "mention":
        # Coordinate dai luoghi menzionati (text_term_place)
        sql = """
        SELECT DISTINCT
            ttp.geometry, ttp.geometry_precision,
            tt.preferred_label AS matched_term, tt.id AS term_id,
            td.id AS doc_id, td.siglum,
            o.label AS object_label,
            c.name AS context_name, c.deposit_type,
            och.absolute_from AS year_from, och.absolute_to AS year_to
          FROM annotation_term at2
          JOIN annotation a ON a.id = at2.annotation_id
          JOIN text_version tv ON tv.id = a.text_version_id
          JOIN text_document td ON td.id = tv.text_document_id
          JOIN text_term tt ON tt.id = at2.term_id
          JOIN text_term_place ttp ON ttp.term_id = tt.id
          LEFT JOIN object o ON o.id = td.object_id
          LEFT JOIN object_context oc ON oc.object_id = o.id
          LEFT JOIN context c ON c.id = oc.context_id
          LEFT JOIN object_chronology och ON och.object_id = o.id
         WHERE a.status = 'accepted' AND ttp.geometry IS NOT NULL
        """
    else:
        # Coordinate del findspot (context)
        sql = """
        SELECT DISTINCT
            c.geometry, c.geometry_precision,
            tt.preferred_label AS matched_term, tt.id AS term_id,
            td.id AS doc_id, td.siglum,
            o.label AS object_label,
            c.name AS context_name, c.deposit_type,
            och.absolute_from AS year_from, och.absolute_to AS year_to
          FROM annotation_term at2
          JOIN annotation a ON a.id = at2.annotation_id
          JOIN text_version tv ON tv.id = a.text_version_id
          JOIN text_document td ON td.id = tv.text_document_id
          JOIN text_term tt ON tt.id = at2.term_id
          JOIN object o ON o.id = td.object_id
          JOIN object_context oc ON oc.object_id = o.id
          JOIN context c ON c.id = oc.context_id
          LEFT JOIN object_chronology och ON och.object_id = o.id
         WHERE a.status = 'accepted' AND c.geometry IS NOT NULL
        """

    params = []
    if term_id:
        desc = descendants(conn, "text_term", term_id)
        ids = [term_id] + [d["id"] for d in desc]
        ph = ",".join("?" for _ in ids)
        sql += f" AND at2.term_id IN ({ph})"
        params.extend(ids)

    if year_from is not None:
        sql += " AND (och.absolute_to IS NULL OR och.absolute_to >= ?)"
        params.append(year_from)
    if year_to is not None:
        sql += " AND (och.absolute_from IS NULL OR och.absolute_from <= ?)"
        params.append(year_to)

    results = []
    for r in conn.execute(sql, params):
        d = dict(r)
        # Decodifica geometria in lat/lon
        try:
            pt = gpkg.decode_point(d["geometry"])
            if pt:
                d["lon"] = pt[0]
                d["lat"] = pt[1]
                del d["geometry"]
                results.append(d)
        except Exception:
            pass
    return results


def _normalize_for_similarity(text):
    """Normalizza un testo per il confronto di paralleli:
    - lowercase
    - rimuovi punti interpuntivi antichi (·), doppi spazi
    - unisce le righe
    """
    import re
    if not text:
        return ""
    t = text.lower()
    t = re.sub(r'[·•\.]+', ' ', t)  # elimina interpunzione
    t = re.sub(r'\s+', ' ', t)       # collassa whitespace
    return t.strip()


def _tokenize(text, n=3):
    """Ritorna set di n-grammi di parole del testo normalizzato."""
    words = text.split()
    if len(words) < n:
        return set([" ".join(words)]) if words else set()
    return set(" ".join(words[i:i+n]) for i in range(len(words) - n + 1))


def _jaccard(set_a, set_b):
    if not set_a and not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def analytics_formula_search(conn, *, version_type="normalized",
                              min_similarity=0.3, ngram=3):
    """Cerca formule e paralleli testuali tra tutte le versioni di un dato tipo.
    Restituisce coppie di testi con similarità Jaccard sopra la soglia.

    Ritorna: {texts:[{id,siglum,object_label,content}],
              matches:[{a:doc_id, b:doc_id, similarity, shared_ngrams}]}
    """
    # Prendi tutte le versioni del tipo richiesto
    versions = [dict(r) for r in conn.execute("""
        SELECT tv.id AS version_id, tv.content,
               td.id AS doc_id, td.siglum, td.title,
               o.label AS object_label
          FROM text_version tv
          JOIN text_document td ON td.id = tv.text_document_id
          LEFT JOIN object o ON o.id = td.object_id
         WHERE tv.version_type = ? AND tv.is_current = 1
    """, (version_type,))]

    # Normalizza e tokenizza
    for v in versions:
        v["_norm"] = _normalize_for_similarity(v["content"])
        v["_ngrams"] = _tokenize(v["_norm"], n=ngram)

    # Confronta a coppie
    matches = []
    for i in range(len(versions)):
        for j in range(i + 1, len(versions)):
            sim = _jaccard(versions[i]["_ngrams"], versions[j]["_ngrams"])
            if sim >= min_similarity:
                shared = versions[i]["_ngrams"] & versions[j]["_ngrams"]
                matches.append({
                    "a_doc_id": versions[i]["doc_id"],
                    "a_siglum": versions[i]["siglum"],
                    "b_doc_id": versions[j]["doc_id"],
                    "b_siglum": versions[j]["siglum"],
                    "similarity": round(sim, 3),
                    "shared_ngrams": sorted(list(shared))[:10],  # top 10
                    "n_shared": len(shared),
                })
    matches.sort(key=lambda x: -x["similarity"])

    return {
        "version_type": version_type,
        "n_texts": len(versions),
        "texts": [{
            "doc_id": v["doc_id"], "siglum": v["siglum"],
            "title": v["title"], "object_label": v["object_label"],
            "content": v["content"],
        } for v in versions],
        "matches": matches,
        "params": {"min_similarity": min_similarity, "ngram": ngram},
    }


def analytics_ngram_frequency(conn, *, version_type="normalized",
                               ngram=2, min_count=2, limit=30):
    """Frequenza degli n-grammi più comuni. Utile per scoprire formule
    ricorrenti senza sapere in anticipo cosa cercare."""
    from collections import Counter
    versions = conn.execute("""
        SELECT content FROM text_version
         WHERE version_type = ? AND is_current = 1
    """, (version_type,)).fetchall()
    counter = Counter()
    for v in versions:
        norm = _normalize_for_similarity(v[0])
        for ng in _tokenize(norm, n=ngram):
            counter[ng] += 1
    top = [{"ngram": ng, "count": c}
           for ng, c in counter.most_common(limit)
           if c >= min_count]
    return {"version_type": version_type, "ngram": ngram,
            "top_ngrams": top, "n_texts": len(versions)}


def analytics_concept_timeline(conn, *, granularity="century"):
    """Distribuzione dei rami semantici nel tempo. Bins per secolo o 50 anni.
    Restituisce una matrice bin × ramo con conteggi di annotazioni.

    granularity: 'century' (100 anni) o 'half' (50 anni).

    Nota: esclude i termini di tipo 'person' dalle radici (sarebbero centinaia).
    Include solo concetti, formule, divinità, luoghi, titoli.
    """
    bin_size = 100 if granularity == "century" else 50

    # 1. Trova radici semantiche (senza IS_A verso l'alto) — escludendo 'person'
    roots = [dict(r) for r in conn.execute("""
        SELECT id, preferred_label, term_type FROM text_term
         WHERE id NOT IN (
             SELECT r.source_term_id FROM text_term_relation r
               JOIN relation_type rt ON rt.id = r.relation_type_id
              WHERE rt.code = 'IS_A'
         )
           AND term_type != 'person'
         ORDER BY preferred_label
    """)]

    # 2. Per ogni radice, calcola discendenti
    root_to_terms = {}
    for root in roots:
        desc = descendants(conn, "text_term", root["id"],
                           relation_codes=("IS_A",))
        root_to_terms[root["id"]] = [root["id"]] + [d["id"] for d in desc]

    # 3. Trova tutte le annotazioni con la loro cronologia (dall'oggetto)
    rows = conn.execute("""
        SELECT at2.term_id, och.absolute_from, och.absolute_to, a.id AS ann_id
          FROM annotation a
          JOIN annotation_term at2 ON at2.annotation_id = a.id
          JOIN text_version tv ON tv.id = a.text_version_id
          JOIN text_document td ON td.id = tv.text_document_id
          JOIN object o ON o.id = td.object_id
          JOIN object_chronology och ON och.object_id = o.id
         WHERE a.status = 'accepted'
           AND och.absolute_from IS NOT NULL
           AND och.absolute_to IS NOT NULL
    """).fetchall()

    if not rows:
        return {"bins": [], "series": [], "granularity": granularity}

    # 4. Determina range globale
    all_from = [r[1] for r in rows]
    all_to = [r[2] for r in rows]
    global_min = min(all_from)
    global_max = max(all_to)

    # Arrotonda ai bin
    def floor_bin(y):
        return (y // bin_size) * bin_size
    bin_start = floor_bin(global_min)
    bin_end = floor_bin(global_max) + bin_size
    bins = list(range(bin_start, bin_end + 1, bin_size))
    bin_labels = [f"{b} — {b+bin_size-1}" for b in bins[:-1]]

    # 5. Per ciascuna radice, calcola i conteggi per bin
    # Un'annotazione con range [from, to] è distribuita proporzionalmente
    # su tutti i bin che interseca (semplicemente contata 1 per bin che tocca)
    series = []
    for root in roots:
        term_ids = set(root_to_terms[root["id"]])
        counts = [0] * len(bin_labels)
        seen_ann_per_bin = [set() for _ in bin_labels]
        for r in rows:
            if r[0] not in term_ids:
                continue
            f, t, ann_id = r[1], r[2], r[3]
            for i, b in enumerate(bins[:-1]):
                bin_lo, bin_hi = b, b + bin_size - 1
                if f <= bin_hi and t >= bin_lo:
                    if ann_id not in seen_ann_per_bin[i]:
                        counts[i] += 1
                        seen_ann_per_bin[i].add(ann_id)
        if any(counts):
            series.append({
                "label": root["preferred_label"],
                "counts": counts,
            })

    return {
        "granularity": granularity,
        "bin_size": bin_size,
        "bins": bin_labels,
        "series": series,
    }


# ============================================================================
# WORK — opera intellettuale astratta (raggruppa più text_document come testimoni)
# ============================================================================

def list_works(conn, *, include_witness_count=True):
    """Elenca tutte le opere attive, opzionalmente con il numero di testimoni."""
    if include_witness_count:
        rows = conn.execute("""
            SELECT w.*, COUNT(td.id) AS witness_count
              FROM work w
              LEFT JOIN text_document td ON td.work_id = w.id AND td.is_active = 1
             WHERE w.is_active = 1
             GROUP BY w.id
             ORDER BY w.title
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM work WHERE is_active = 1 ORDER BY title
        """).fetchall()
    return [dict(r) for r in rows]


def get_work(conn, work_id):
    """Restituisce un work con la lista dei testimoni (text_document + oggetto + contesto)."""
    w = conn.execute("SELECT * FROM work WHERE id = ?", (work_id,)).fetchone()
    if not w:
        return None
    w = dict(w)
    witnesses = conn.execute("""
        SELECT td.id, td.siglum, td.witness_siglum, td.title,
               td.main_language, td.description,
               o.id AS object_id, o.label AS object_label,
               o.record_kind AS object_kind,
               c.id AS context_id, c.name AS context_name,
               och.absolute_from AS year_from, och.absolute_to AS year_to,
               (SELECT COUNT(*) FROM text_version tv
                 WHERE tv.text_document_id = td.id AND tv.is_current = 1) AS n_versions
          FROM text_document td
          LEFT JOIN object o ON o.id = td.object_id
          LEFT JOIN object_context oc ON oc.object_id = o.id
          LEFT JOIN context c ON c.id = oc.context_id
          LEFT JOIN object_chronology och ON och.object_id = o.id
         WHERE td.work_id = ? AND td.is_active = 1
         ORDER BY COALESCE(td.witness_siglum, td.siglum, td.id)
    """, (work_id,)).fetchall()
    w["witnesses"] = [dict(r) for r in witnesses]
    w["witness_count"] = len(w["witnesses"])
    return w


def create_work(conn, *, title, author=None, work_type=None,
                canonical_dating=None, composition_from=None,
                composition_to=None, language=None, description=None,
                bibliography=None, notes=None):
    """Crea una nuova opera."""
    from .db.project import new_uid, now_iso
    now = now_iso()
    cur = conn.execute("""
        INSERT INTO work (uid, title, author, work_type, canonical_dating,
                          composition_from, composition_to, language,
                          description, bibliography, notes,
                          is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
    """, (new_uid(), title, author, work_type, canonical_dating,
          composition_from, composition_to, language,
          description, bibliography, notes, now, now))
    conn.commit()
    return cur.lastrowid


def update_work(conn, work_id, **fields):
    """Aggiorna i campi consentiti di un'opera."""
    from .db.project import now_iso
    allowed = {"title", "author", "work_type", "canonical_dating",
               "composition_from", "composition_to", "language",
               "description", "bibliography", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = now_iso()
    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    params = list(updates.values()) + [work_id]
    conn.execute(f"UPDATE work SET {set_clause} WHERE id = ?", params)
    conn.commit()
    return True


def link_document_to_work(conn, doc_id, work_id, witness_siglum=None):
    """Collega un text_document a un work (o scollega passando work_id=None)."""
    from .db.project import now_iso
    conn.execute(
        "UPDATE text_document SET work_id = ?, witness_siglum = ?, updated_at = ? WHERE id = ?",
        (work_id, witness_siglum, now_iso(), doc_id))
    conn.commit()
    return True


def documents_without_work(conn, *, limit=100):
    """Elenca i text_document non ancora collegati a un work (per collegamento UI)."""
    return [dict(r) for r in conn.execute("""
        SELECT td.id, td.siglum, td.title, o.label AS object_label
          FROM text_document td
          LEFT JOIN object o ON o.id = td.object_id
         WHERE td.work_id IS NULL AND td.is_active = 1
         ORDER BY td.siglum, td.title
         LIMIT ?
    """, (limit,))]


# ============================================================================
# WORK ANALYTICS — confronto testimoni di una stessa opera
# ============================================================================

def analytics_work_witnesses_diff(conn, work_id, *, version_type="normalized",
                                    ngram=2):
    """Confronta i testimoni di una stessa opera.

    Restituisce:
      - matrix: matrice NxN di similarità Jaccard tra tutti i testimoni
      - variants: apparato critico automatico (varianti per riga)
      - stats: numeri di sintesi (n_witnesses, avg_similarity, min, max)

    Il diff pairwise dettagliato è lazy: si calcola su richiesta con
    analytics_work_witness_pair_diff(...) per una coppia specifica.
    """
    from difflib import SequenceMatcher

    # Prendi i testimoni con la loro versione richiesta
    witnesses = [dict(r) for r in conn.execute("""
        SELECT td.id AS doc_id, td.siglum, td.witness_siglum,
               o.label AS object_label,
               tv.id AS version_id, tv.content
          FROM text_document td
          JOIN text_version tv ON tv.text_document_id = td.id
                              AND tv.is_current = 1
                              AND tv.version_type = ?
          LEFT JOIN object o ON o.id = td.object_id
         WHERE td.work_id = ? AND td.is_active = 1
         ORDER BY COALESCE(td.witness_siglum, td.siglum, td.id)
    """, (version_type, work_id))]

    if len(witnesses) < 2:
        return {
            "work_id": work_id,
            "version_type": version_type,
            "witnesses": witnesses,
            "matrix": [],
            "variants": [],
            "stats": {"n_witnesses": len(witnesses)},
            "message": ("At least two witnesses are required for comparison"
                        if witnesses else "No witnesses")
        }

    # ── 1. Matrice di similarità NxN ────────────────────────────────
    for w in witnesses:
        w["_norm"] = _normalize_for_similarity(w["content"])
        w["_ngrams"] = _tokenize(w["_norm"], n=ngram)

    n = len(witnesses)
    matrix = []
    sims = []
    for i in range(n):
        row = []
        for j in range(n):
            if i == j:
                row.append(1.0)
            else:
                sim = _jaccard(witnesses[i]["_ngrams"], witnesses[j]["_ngrams"])
                row.append(round(sim, 3))
                if i < j:
                    sims.append(sim)
        matrix.append(row)

    # ── 2. Apparato critico: per ogni "riga slot" trova le varianti ─
    # Approccio: usiamo l'allineamento per posizione tra righe.
    # Se i testimoni hanno n righe diverse, prendiamo il massimo e le celle
    # mancanti sono "omit.".
    max_lines = max(len(w["content"].split("\n")) for w in witnesses)
    variants = []
    for line_idx in range(max_lines):
        readings = {}  # reading_text → [witness_siglum]
        for w in witnesses:
            lines = w["content"].split("\n")
            if line_idx < len(lines):
                reading = lines[line_idx].strip()
            else:
                reading = "[omit.]"
            reading_norm = _normalize_for_similarity(reading) or "[omit.]"
            readings.setdefault(reading_norm, {"reading": reading, "witnesses": []})
            readings[reading_norm]["witnesses"].append(
                w["witness_siglum"] or w["siglum"] or f"doc-{w['doc_id']}")
        # Solo righe con effettiva varianza (>1 reading) o dove qualcuno omette
        if len(readings) > 1:
            variants.append({
                "line": line_idx + 1,
                "n_readings": len(readings),
                "readings": [
                    {"reading": r["reading"], "witnesses": r["witnesses"],
                     "count": len(r["witnesses"])}
                    for r in sorted(readings.values(),
                                     key=lambda x: -len(x["witnesses"]))
                ]
            })

    # ── 3. Stats ────────────────────────────────────────────────────
    stats = {
        "n_witnesses": n,
        "n_lines_with_variants": len(variants),
        "n_lines_total": max_lines,
        "avg_similarity": round(sum(sims) / len(sims), 3) if sims else None,
        "min_similarity": round(min(sims), 3) if sims else None,
        "max_similarity": round(max(sims), 3) if sims else None,
    }

    return {
        "work_id": work_id,
        "version_type": version_type,
        "ngram": ngram,
        "witnesses": [{
            "doc_id": w["doc_id"], "siglum": w["siglum"],
            "witness_siglum": w["witness_siglum"],
            "object_label": w["object_label"],
            "content": w["content"],
            "n_lines": len(w["content"].split("\n")),
        } for w in witnesses],
        "matrix": matrix,
        "variants": variants,
        "stats": stats,
    }


def analytics_work_witness_pair_diff(conn, work_id, doc_a_id, doc_b_id,
                                       *, version_type="normalized"):
    """Diff dettagliato riga-per-riga tra due testimoni specifici.
    Usa difflib per allineare le righe in modo ottimale (non per posizione)."""
    from difflib import SequenceMatcher

    def _load(doc_id):
        r = conn.execute("""
            SELECT td.id AS doc_id, td.siglum, td.witness_siglum,
                   tv.content
              FROM text_document td
              JOIN text_version tv ON tv.text_document_id = td.id
                                  AND tv.is_current = 1
                                  AND tv.version_type = ?
             WHERE td.id = ? AND td.work_id = ?
        """, (version_type, doc_id, work_id)).fetchone()
        return dict(r) if r else None

    a = _load(doc_a_id)
    b = _load(doc_b_id)
    if not a or not b:
        return None

    lines_a = a["content"].split("\n")
    lines_b = b["content"].split("\n")

    # SequenceMatcher su liste di righe (matching esatto per riga)
    matcher = SequenceMatcher(None, lines_a, lines_b, autojunk=False)

    aligned = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                aligned.append({
                    "status": "equal",
                    "a": lines_a[i1 + k],
                    "b": lines_b[j1 + k],
                    "similarity": 1.0,
                })
        elif tag == "replace":
            # Un blocco cambiato: match line-by-line dentro il blocco per similarità
            len_a = i2 - i1
            len_b = j2 - j1
            for k in range(max(len_a, len_b)):
                a_line = lines_a[i1 + k] if k < len_a else None
                b_line = lines_b[j1 + k] if k < len_b else None
                if a_line is not None and b_line is not None:
                    # Calcola similarità intra-riga carattere-per-carattere
                    sim = SequenceMatcher(
                        None,
                        _normalize_for_similarity(a_line),
                        _normalize_for_similarity(b_line)
                    ).ratio()
                    status = ("variant" if sim >= 0.5 else "conflict")
                    aligned.append({
                        "status": status,
                        "a": a_line,
                        "b": b_line,
                        "similarity": round(sim, 2),
                    })
                elif a_line is not None:
                    aligned.append({"status": "only_a", "a": a_line, "b": None,
                                     "similarity": 0.0})
                else:
                    aligned.append({"status": "only_b", "a": None, "b": b_line,
                                     "similarity": 0.0})
        elif tag == "delete":
            for k in range(i2 - i1):
                aligned.append({"status": "only_a", "a": lines_a[i1 + k],
                                 "b": None, "similarity": 0.0})
        elif tag == "insert":
            for k in range(j2 - j1):
                aligned.append({"status": "only_b", "a": None,
                                 "b": lines_b[j1 + k], "similarity": 0.0})

    summary = {
        "equal": sum(1 for x in aligned if x["status"] == "equal"),
        "variant": sum(1 for x in aligned if x["status"] == "variant"),
        "conflict": sum(1 for x in aligned if x["status"] == "conflict"),
        "only_a": sum(1 for x in aligned if x["status"] == "only_a"),
        "only_b": sum(1 for x in aligned if x["status"] == "only_b"),
        "total": len(aligned),
    }
    # Ratio globale su tutte le righe
    global_sim = SequenceMatcher(
        None,
        _normalize_for_similarity(a["content"]),
        _normalize_for_similarity(b["content"])
    ).ratio()

    return {
        "a": {"doc_id": a["doc_id"], "siglum": a["siglum"],
              "witness_siglum": a["witness_siglum"]},
        "b": {"doc_id": b["doc_id"], "siglum": b["siglum"],
              "witness_siglum": b["witness_siglum"]},
        "version_type": version_type,
        "lines": aligned,
        "summary": summary,
        "global_similarity": round(global_sim, 3),
    }
