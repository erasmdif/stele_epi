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
        "human": "Vocabolario di contesto",
        "has_labels": True,           # ha una tabella <table>_label per etichette alt.
        "assignment_table": "context_term_assignment",
        "assignment_owner": "context_id",
        "owner_table": "context",
        "owner_label_cols": ("code", "name"),
        "extra_cols": (),
    },
    "object_term": {
        "human": "Vocabolario di oggetto",
        "has_labels": True,
        "assignment_table": "object_term_assignment",
        "assignment_owner": "object_id",
        "owner_table": "object",
        "owner_label_cols": ("inventory_number", "label"),
        "extra_cols": (),
    },
    "chronology_term": {
        "human": "Vocabolario di cronologia",
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
