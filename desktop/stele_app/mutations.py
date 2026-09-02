"""
Operazioni di scrittura del DBMS con le validazioni applicative della specifica
(§23) e audit minimo su change_log. Solleva ValueError con messaggio leggibile
per le violazioni, così l'API può restituire 400.
"""
import json
from .db.project import now_iso, new_uid, nfc
from . import models


# --- helper interni ---------------------------------------------------------
def _cp_len(text):
    return len(list(text or ""))


def _cert_id(conn, code):
    if not code:
        return None
    r = conn.execute("SELECT id FROM certainty_level WHERE code=?", (code,)).fetchone()
    return r["id"] if r else None


def _rel_id(conn, code):
    r = conn.execute("SELECT id, is_hierarchical FROM relation_type WHERE code=?", (code,)).fetchone()
    if not r:
        raise ValueError(f"Unknown relation_type: {code}")
    return r["id"], bool(r["is_hierarchical"])


def _log(conn, table, entity_id, action, before=None, after=None, user=None, note=None):
    def _clean(d):
        if d is None: return None
        if isinstance(d, dict):
            return {k: (f"<bytes:{len(v)}>" if isinstance(v, (bytes, bytearray)) else v)
                    for k, v in d.items()}
        return d
    conn.execute(
        "INSERT INTO change_log (entity_table,entity_id,action,changed_by,changed_at,before_json,after_json,note) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (table, entity_id, action, user, now_iso(),
         json.dumps(_clean(before)) if before is not None else None,
         json.dumps(_clean(after)) if after is not None else None, note))


def _version_content(conn, version_id):
    r = conn.execute("SELECT content FROM text_version WHERE id=?", (version_id,)).fetchone()
    if not r:
        raise ValueError("Text version not found.")
    return r["content"] or ""


def _validate_spans(spans, content_len):
    if not spans:
        raise ValueError("An annotation must contain at least one span.")
    norm = []
    for s in spans:
        start = int(s.get("start", s.get("start_position")))
        end = int(s.get("end", s.get("end_position")))
        if start < 0:
            raise ValueError("start cannot be negative.")
        if end <= start:
            raise ValueError("A span cannot be empty or reversed; end must be greater than start.")
        if end > content_len:
            raise ValueError(f"Span [{start},{end}) exceeds the text length ({content_len} code points).")
        norm.append((start, end))
    return norm


# --- annotazioni ------------------------------------------------------------
ANNOTATION_TYPES = ("semantic", "editorial", "linguistic", "palaeographic",
                    "formulaic", "named_entity", "critical", "other")
STATUSES = ("accepted", "proposed", "rejected", "superseded")


def create_annotation(conn, version_id, annotation_type="semantic", note="",
                      status="accepted", certainty_code=None, spans=None,
                      terms=None, user_id=None):
    content = _version_content(conn, version_id)
    clen = _cp_len(content)
    norm = _validate_spans(spans or [], clen)
    if annotation_type not in ANNOTATION_TYPES:
        annotation_type = "other"
    if status not in STATUSES:
        status = "accepted"
    uid = new_uid()
    aid = conn.execute(
        "INSERT INTO annotation (uid,text_version_id,annotation_type,certainty_id,note,status,created_by,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (uid, version_id, annotation_type, _cert_id(conn, certainty_code), note or "",
         status, user_id, now_iso(), now_iso())).lastrowid
    for seq, (s, e) in enumerate(norm, start=1):
        conn.execute("INSERT INTO annotation_span (annotation_id,start_position,end_position,sequence) VALUES (?,?,?,?)",
                     (aid, s, e, seq))
    for t in (terms or []):
        add_annotation_term(conn, aid, t["term_id"], t.get("role", "primary"),
                            t.get("certainty_code"), _commit=False)
    _log(conn, "annotation", aid, "create", after={"type": annotation_type, "spans": norm}, user=user_id)
    conn.commit()
    return aid


def update_annotation(conn, aid, fields, user_id=None):
    cur = conn.execute("SELECT * FROM annotation WHERE id=?", (aid,)).fetchone()
    if not cur:
        raise ValueError("Annotation not found.")
    before = dict(cur)
    sets, vals = [], []
    if "annotation_type" in fields and fields["annotation_type"] in ANNOTATION_TYPES:
        sets.append("annotation_type=?"); vals.append(fields["annotation_type"])
    if "note" in fields:
        sets.append("note=?"); vals.append(fields["note"] or "")
    if "status" in fields and fields["status"] in STATUSES:
        sets.append("status=?"); vals.append(fields["status"])
    if "certainty_code" in fields:
        sets.append("certainty_id=?"); vals.append(_cert_id(conn, fields["certainty_code"]))
    if not sets:
        return aid
    sets.append("updated_at=?"); vals.append(now_iso())
    vals.append(aid)
    conn.execute(f"UPDATE annotation SET {','.join(sets)} WHERE id=?", vals)
    _log(conn, "annotation", aid, "update", before=before, after=fields, user=user_id)
    conn.commit()
    return aid


def delete_annotation(conn, aid, user_id=None):
    cur = conn.execute("SELECT * FROM annotation WHERE id=?", (aid,)).fetchone()
    if not cur:
        raise ValueError("Annotation not found.")
    conn.execute("DELETE FROM annotation WHERE id=?", (aid,))  # cascade span/term
    _log(conn, "annotation", aid, "other", before=dict(cur), user=user_id, note="delete")
    conn.commit()
    return True


def set_spans(conn, aid, spans, user_id=None):
    r = conn.execute("SELECT text_version_id FROM annotation WHERE id=?", (aid,)).fetchone()
    if not r:
        raise ValueError("Annotation not found.")
    content = _version_content(conn, r["text_version_id"])
    norm = _validate_spans(spans, _cp_len(content))
    conn.execute("DELETE FROM annotation_span WHERE annotation_id=?", (aid,))
    for seq, (s, e) in enumerate(norm, start=1):
        conn.execute("INSERT INTO annotation_span (annotation_id,start_position,end_position,sequence) VALUES (?,?,?,?)",
                     (aid, s, e, seq))
    conn.execute("UPDATE annotation SET updated_at=? WHERE id=?", (now_iso(), aid))
    _log(conn, "annotation", aid, "update", after={"spans": norm}, user=user_id, note="set_spans")
    conn.commit()
    return norm


# --- termini dell'annotazione ----------------------------------------------
ROLES = ("primary", "secondary", "interpretation", "expansion", "reference", "other")


def add_annotation_term(conn, aid, term_id, role="primary", certainty_code=None, _commit=True):
    if role not in ROLES:
        role = "primary"
    if not conn.execute("SELECT 1 FROM text_term WHERE id=?", (term_id,)).fetchone():
        raise ValueError("Text term not found.")
    try:
        conn.execute(
            "INSERT INTO annotation_term (annotation_id,term_id,role,certainty_id) VALUES (?,?,?,?)",
            (aid, term_id, role, _cert_id(conn, certainty_code)))
    except Exception:
        raise ValueError("The term is already linked with this role.")
    if _commit:
        conn.commit()
    return True


def remove_annotation_term(conn, aid, term_id, role=None):
    if role:
        conn.execute("DELETE FROM annotation_term WHERE annotation_id=? AND term_id=? AND role=?",
                     (aid, term_id, role))
    else:
        conn.execute("DELETE FROM annotation_term WHERE annotation_id=? AND term_id=?", (aid, term_id))
    conn.commit()
    return True


# --- vocabolario testuale ---------------------------------------------------
TEXT_TERM_TYPES = ("person", "deity", "place", "institution", "ethnonym", "plant",
                   "animal", "object_concept", "formula", "abbreviation",
                   "linguistic_feature", "palaeographic_feature", "editorial_feature",
                   "title", "office", "event", "ritual", "concept", "quantity",
                   "calendar_expression", "other")


def search_text_terms(conn, q, limit=20):
    q = (q or "").strip()
    if not q:
        rows = conn.execute("SELECT id,preferred_label,term_type FROM text_term "
                            "WHERE is_active=1 ORDER BY preferred_label LIMIT ?", (limit,))
    else:
        rows = conn.execute(
            "SELECT id,preferred_label,term_type FROM text_term "
            "WHERE is_active=1 AND preferred_label LIKE ? ORDER BY preferred_label LIMIT ?",
            ("%" + q + "%", limit))
    return [dict(r) for r in rows]


def create_text_term(conn, term_type, preferred_label, description=None, properties=None):
    if not preferred_label or not preferred_label.strip():
        raise ValueError("preferred_label is required.")
    if term_type not in TEXT_TERM_TYPES:
        term_type = "other"
    props = json.dumps(properties) if isinstance(properties, (dict, list)) else properties
    tid = conn.execute(
        "INSERT INTO text_term (uid,term_type,preferred_label,description,properties,is_active) "
        "VALUES (?,?,?,?,?,1)",
        (new_uid(), term_type, preferred_label.strip(), description, props)).lastrowid
    conn.commit()
    return dict(conn.execute("SELECT id,preferred_label,term_type FROM text_term WHERE id=?", (tid,)).fetchone())


def set_term_place(conn, term_id, lat, lon, precision="approximate", source="manual", note=None):
    r = conn.execute("SELECT term_type FROM text_term WHERE id=?", (term_id,)).fetchone()
    if not r:
        raise ValueError("Text term not found.")
    if r["term_type"] != "place":
        raise ValueError("Coordinates can only be assigned to terms of type 'place'.")
    from .db.geopackage import encode_point
    blob = encode_point(float(lon), float(lat))
    existing = conn.execute("SELECT id FROM text_term_place WHERE term_id=?", (term_id,)).fetchone()
    if existing:
        conn.execute("UPDATE text_term_place SET geometry=?,geometry_precision=?,geometry_source=?,note=? WHERE term_id=?",
                     (blob, precision, source, note, term_id))
    else:
        conn.execute("INSERT INTO text_term_place (term_id,geometry,geometry_precision,geometry_source,note) "
                     "VALUES (?,?,?,?,?)", (term_id, blob, precision, source, note))
    conn.commit()
    return True


def add_term_relation(conn, source_id, target_id, relation_code, certainty_code=None, user_id=None):
    """Aggiunge una relazione semantica fra due text_term (rete N:M).
    Impedisce auto-relazioni e cicli nelle relazioni gerarchiche (§23.5)."""
    if source_id == target_id:
        raise ValueError("Source and target cannot be the same.")
    for tid in (source_id, target_id):
        if not conn.execute("SELECT 1 FROM text_term WHERE id=?", (tid,)).fetchone():
            raise ValueError("Text term not found.")
    rel_id, hierarchical = _rel_id(conn, relation_code)
    if hierarchical:
        # ciclo se source è già antenato di target (target può risalire a source)
        anc = {a["id"] for a in models.ancestors(conn, "text_term", target_id)}
        if source_id in anc:
            raise ValueError("This relation would create a cycle in the hierarchy.")
    try:
        conn.execute(
            "INSERT INTO text_term_relation (source_term_id,target_term_id,relation_type_id,certainty_id,created_at) "
            "VALUES (?,?,?,?,?)",
            (source_id, target_id, rel_id, _cert_id(conn, certainty_code), now_iso()))
    except Exception:
        raise ValueError("The relation already exists.")
    conn.commit()
    return True


# ---------------------------------------------------------------------------
# Versioning del testo: nuova versione + remap degli offset
# Le versioni annotate sono IMMUTABILI (§9): modificare il testo crea una nuova
# text_version; le annotazioni remappabili vengono migrate, le altre restano
# sulla versione precedente (che continua a esistere) e sono segnalate.
# ---------------------------------------------------------------------------
def remap_spans(old, new, spans):
    """Remappa gli span [start,end) da 'old' a 'new' (code point) via prefisso/
    suffisso comune. Ritorna (lista_remappata, n_orfani); uno span che interseca
    solo parzialmente il confine della modifica diventa None (orfano)."""
    oa, na = list(old or ""), list(new or "")
    ol, nl = len(oa), len(na)
    p, m = 0, min(ol, nl)
    while p < m and oa[p] == na[p]:
        p += 1
    q = 0
    while q < (m - p) and oa[ol - 1 - q] == na[nl - 1 - q]:
        q += 1
    region_start, region_old_end, delta = p, ol - q, nl - ol
    out, orphan = [], 0
    for (s, e) in spans:
        if e <= region_start:
            out.append((s, e))
        elif s >= region_old_end:
            out.append((s + delta, e + delta))
        elif s <= region_start and e >= region_old_end:
            out.append((s, e + delta))
        else:
            out.append(None); orphan += 1
    return out, orphan


def revise_text_version(conn, version_id, new_content, note=None, migrate=True, user_id=None):
    v = conn.execute("SELECT * FROM text_version WHERE id=?", (version_id,)).fetchone()
    if not v:
        raise ValueError("Text version not found.")
    v = dict(v)
    old_content = v["content"] or ""
    new_content = nfc(new_content or "")
    if new_content == old_content:
        raise ValueError("The text has not changed.")
    doc_id, vtype = v["text_document_id"], v["version_type"]
    max_no = conn.execute(
        "SELECT COALESCE(MAX(version_number),0) FROM text_version WHERE text_document_id=? AND version_type=?",
        (doc_id, vtype)).fetchone()[0]
    new_vid = conn.execute(
        "INSERT INTO text_version (uid,text_document_id,version_type,language,script,content,"
        "version_number,based_on_version_id,is_current,created_by,created_at,note) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (new_uid(), doc_id, vtype, v["language"], v["script"], new_content,
         max_no + 1, version_id, 1, user_id, now_iso(), note)).lastrowid
    # la nuova diventa la corrente per (documento, tipo)
    conn.execute("UPDATE text_version SET is_current=0 WHERE text_document_id=? AND version_type=? AND id<>?",
                 (doc_id, vtype, new_vid))
    # FTS per la nuova versione
    conn.execute("INSERT INTO text_version_fts (rowid,content,text_version_id) VALUES (?,?,?)",
                 (new_vid, new_content, new_vid))
    # unità di riga rigenerate sul nuovo contenuto
    for i, _ in enumerate(new_content.split("\n"), start=1):
        conn.execute("INSERT INTO text_unit (text_version_id,unit_type,label,sequence) VALUES (?,?,?,?)",
                     (new_vid, "line", f"Line {i}", i))

    report = {"new_version_id": new_vid, "migrated": 0, "skipped": 0, "skipped_ids": []}
    if migrate:
        anns = conn.execute("SELECT * FROM annotation WHERE text_version_id=?", (version_id,)).fetchall()
        for a in anns:
            a = dict(a)
            spans = [(r["start_position"], r["end_position"]) for r in conn.execute(
                "SELECT start_position,end_position FROM annotation_span WHERE annotation_id=? ORDER BY sequence", (a["id"],))]
            remapped, orphan = remap_spans(old_content, new_content, spans)
            if orphan or any(x is None for x in remapped):
                report["skipped"] += 1; report["skipped_ids"].append(a["id"]); continue
            naid = conn.execute(
                "INSERT INTO annotation (uid,text_version_id,annotation_type,certainty_id,note,status,created_by,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (new_uid(), new_vid, a["annotation_type"], a["certainty_id"], a["note"], a["status"],
                 user_id, now_iso(), now_iso())).lastrowid
            for seq, (s, e) in enumerate(remapped, start=1):
                conn.execute("INSERT INTO annotation_span (annotation_id,start_position,end_position,sequence) VALUES (?,?,?,?)",
                             (naid, s, e, seq))
            for t in conn.execute("SELECT term_id,role,certainty_id FROM annotation_term WHERE annotation_id=?", (a["id"],)):
                conn.execute("INSERT INTO annotation_term (annotation_id,term_id,role,certainty_id) VALUES (?,?,?,?)",
                             (naid, t["term_id"], t["role"], t["certainty_id"]))
            report["migrated"] += 1
    _log(conn, "text_version", new_vid, "create", after={"based_on": version_id, "migrate": report}, user=user_id,
         note="revise")
    conn.commit()
    return report


# ---------------------------------------------------------------------------
# Scheda-record: aggiornamento termine, label alternative, ID esterni, delete
# ---------------------------------------------------------------------------
def update_text_term(conn, term_id, fields, user_id=None):
    cur = conn.execute("SELECT * FROM text_term WHERE id=?", (term_id,)).fetchone()
    if not cur:
        raise ValueError("Text term not found.")
    sets, vals = [], []
    if "preferred_label" in fields:
        v = (fields["preferred_label"] or "").strip()
        if not v:
            raise ValueError("preferred_label cannot be empty.")
        sets.append("preferred_label=?"); vals.append(v)
    if "term_type" in fields and fields["term_type"] in TEXT_TERM_TYPES:
        sets.append("term_type=?"); vals.append(fields["term_type"])
    if "description" in fields:
        sets.append("description=?"); vals.append(fields["description"])
    if "notes" in fields:
        sets.append("notes=?"); vals.append(fields["notes"])
    if not sets:
        return term_id
    vals.append(term_id)
    conn.execute(f"UPDATE text_term SET {','.join(sets)} WHERE id=?", vals)
    _log(conn, "text_term", term_id, "update", before=dict(cur), after=fields, user=user_id)
    conn.commit()
    return term_id


def delete_text_term(conn, term_id, user_id=None):
    """Elimina un text_term. Se è referenziato da annotation_term (RESTRICT)
    solleva un errore con messaggio esplicito."""
    cur = conn.execute("SELECT * FROM text_term WHERE id=?", (term_id,)).fetchone()
    if not cur:
        raise ValueError("Text term not found.")
    used = conn.execute("SELECT count(*) FROM annotation_term WHERE term_id=?", (term_id,)).fetchone()[0]
    if used:
        raise ValueError(f"Cannot delete this term: it is used in {used} annotation(s). "
                         "Unlink it from the annotations first.")
    conn.execute("DELETE FROM text_term WHERE id=?", (term_id,))
    _log(conn, "text_term", term_id, "other", before=dict(cur), user=user_id, note="delete")
    conn.commit()
    return True


LABEL_TYPES = ("preferred", "alternative", "abbreviation", "historical", "transliteration", "other")


def add_term_label(conn, term_id, label, language=None, label_type="alternative",
                   script=None, is_preferred=False):
    if not conn.execute("SELECT 1 FROM text_term WHERE id=?", (term_id,)).fetchone():
        raise ValueError("Text term not found.")
    label = (label or "").strip()
    if not label:
        raise ValueError("The label cannot be empty.")
    if label_type not in LABEL_TYPES:
        label_type = "alternative"
    lid = conn.execute(
        "INSERT INTO text_term_label (term_id,language,label,label_type,script,is_preferred) "
        "VALUES (?,?,?,?,?,?)", (term_id, language, label, label_type, script,
                                 1 if is_preferred else 0)).lastrowid
    conn.commit()
    return lid


def remove_term_label(conn, label_id):
    conn.execute("DELETE FROM text_term_label WHERE id=?", (label_id,))
    conn.commit()
    return True


def add_term_external_id(conn, term_id, authority, identifier, uri=None, note=None):
    if not conn.execute("SELECT 1 FROM text_term WHERE id=?", (term_id,)).fetchone():
        raise ValueError("Text term not found.")
    if not authority or not identifier:
        raise ValueError("authority and identifier are required.")
    try:
        xid = conn.execute(
            "INSERT INTO text_term_external_id (term_id,authority,identifier,uri,note) "
            "VALUES (?,?,?,?,?)", (term_id, authority.strip(), identifier.strip(), uri, note)).lastrowid
    except Exception:
        raise ValueError("This identifier already exists for the term.")
    conn.commit()
    return xid


def remove_term_external_id(conn, xid):
    conn.execute("DELETE FROM text_term_external_id WHERE id=?", (xid,))
    conn.commit()
    return True


def remove_term_relation(conn, source_id, target_id, relation_code):
    rid, _ = _rel_id(conn, relation_code)
    conn.execute("DELETE FROM text_term_relation WHERE source_term_id=? AND target_term_id=? AND relation_type_id=?",
                 (source_id, target_id, rid))
    conn.commit()
    return True


# ---------------------------------------------------------------------------
# Allineamento delle text_unit tra versioni parallele (gruppi N:M)
# ---------------------------------------------------------------------------
def auto_align_document(conn, doc_id, user_id=None):
    """Crea l'allineamento riga↔riga per posizione: linea i della primaria
    ↔ linea i delle altre versioni. Non-distruttivo: se ci sono già gruppi,
    li lascia stare e allinea solo le unità non ancora nei gruppi."""
    prim = conn.execute("""
        SELECT id, version_type FROM text_version
         WHERE text_document_id=? AND is_current=1
           AND version_type IN ('diplomatic_transcription','transliteration')
         ORDER BY CASE version_type WHEN 'diplomatic_transcription' THEN 0 ELSE 1 END LIMIT 1""",
        (doc_id,)).fetchone()
    if not prim:
        prim = conn.execute("SELECT id FROM text_version WHERE text_document_id=? AND is_current=1 LIMIT 1",
                            (doc_id,)).fetchone()
    if not prim:
        raise ValueError("No current version is available as the primary version.")
    prim_id = prim["id"]
    prim_units = [dict(r) for r in conn.execute(
        "SELECT id,sequence FROM text_unit WHERE text_version_id=? AND unit_type='line' ORDER BY sequence",
        (prim_id,))]
    if not prim_units:
        return {"aligned": 0, "note": "The primary version has no line units."}
    # unità delle altre versioni indicizzate per (version_id, sequence)
    others = [dict(r) for r in conn.execute("""
        SELECT u.id, u.sequence, v.id AS version_id, v.version_type
          FROM text_unit u JOIN text_version v ON v.id=u.text_version_id
         WHERE v.text_document_id=? AND v.id<>? AND u.unit_type='line' AND v.is_current=1
         ORDER BY v.version_type, u.sequence""", (doc_id, prim_id))]
    if not others:
        return {"aligned": 0, "note": "No other versions are available for alignment."}
    aligned = 0
    already_aligned = set(r["text_unit_id"] for r in conn.execute("SELECT text_unit_id FROM text_unit_alignment"))
    for pu in prim_units:
        # esiste già un gruppo con questa primaria?
        existing = conn.execute("""
            SELECT group_id FROM text_unit_alignment WHERE text_unit_id=? AND role='primary'""",
            (pu["id"],)).fetchone()
        if existing:
            gid = existing["group_id"]
        else:
            gid = conn.execute("SELECT COALESCE(MAX(group_id),0)+1 FROM text_unit_alignment").fetchone()[0]
            conn.execute("INSERT INTO text_unit_alignment (group_id,text_unit_id,role,created_at) VALUES (?,?,?,?)",
                         (gid, pu["id"], "primary", now_iso()))
            aligned += 1
        # aggiungi le corrispondenze parallele con la stessa sequence
        for o in others:
            if o["sequence"] == pu["sequence"] and o["id"] not in already_aligned:
                try:
                    conn.execute(
                        "INSERT INTO text_unit_alignment (group_id,text_unit_id,role,created_at) VALUES (?,?,?,?)",
                        (gid, o["id"], "parallel", now_iso()))
                    aligned += 1
                except Exception:
                    pass
    _log(conn, "text_unit_alignment", 0, "create",
         after={"doc_id": doc_id, "aligned": aligned}, user=user_id, note="auto_align")
    conn.commit()
    return {"aligned": aligned, "note": "ok"}


def set_alignment_group(conn, group_id, unit_ids, primary_unit_id=None, user_id=None):
    """Sostituisce l'appartenenza di un gruppo: rimuove tutte le associazioni
    correnti e ne crea di nuove con le unit_ids date. Se group_id è None,
    ne crea uno nuovo."""
    if group_id is None:
        group_id = conn.execute("SELECT COALESCE(MAX(group_id),0)+1 FROM text_unit_alignment").fetchone()[0]
    else:
        conn.execute("DELETE FROM text_unit_alignment WHERE group_id=?", (group_id,))
    for uid in unit_ids:
        role = "primary" if uid == primary_unit_id else "parallel"
        conn.execute("INSERT INTO text_unit_alignment (group_id,text_unit_id,role,created_at) VALUES (?,?,?,?)",
                     (group_id, uid, role, now_iso()))
    _log(conn, "text_unit_alignment", group_id, "update",
         after={"units": unit_ids, "primary": primary_unit_id}, user=user_id)
    conn.commit()
    return group_id


def delete_alignment_group(conn, group_id, user_id=None):
    conn.execute("DELETE FROM text_unit_alignment WHERE group_id=?", (group_id,))
    _log(conn, "text_unit_alignment", group_id, "other", user=user_id, note="delete_group")
    conn.commit()
    return True


def create_parallel_version(conn, doc_id, version_type, language, content,
                            based_on_version_id=None, note=None, auto_align=True, user_id=None):
    """Crea una nuova text_version parallela a un documento e opzionalmente
    la allinea automaticamente alla versione primaria (riga↔riga)."""
    max_no = conn.execute(
        "SELECT COALESCE(MAX(version_number),0) FROM text_version WHERE text_document_id=? AND version_type=?",
        (doc_id, version_type)).fetchone()[0]
    content = nfc(content or "")
    vid = conn.execute(
        "INSERT INTO text_version (uid,text_document_id,version_type,language,content,"
        "version_number,based_on_version_id,is_current,created_by,created_at,note) "
        "VALUES (?,?,?,?,?,?,?,1,?,?,?)",
        (new_uid(), doc_id, version_type, language, content,
         max_no + 1, based_on_version_id, user_id, now_iso(), note)).lastrowid
    # unit line
    for i, _ in enumerate((content or "").split("\n"), start=1):
        conn.execute("INSERT INTO text_unit (text_version_id,unit_type,label,sequence) VALUES (?,?,?,?)",
                     (vid, "line", f"Line {i}", i))
    conn.execute("INSERT INTO text_version_fts (rowid,content,text_version_id) VALUES (?,?,?)", (vid, content, vid))
    _log(conn, "text_version", vid, "create", after={"doc_id": doc_id, "type": version_type}, user=user_id)
    conn.commit()
    if auto_align:
        auto_align_document(conn, doc_id, user_id=user_id)
    return vid


# ---------------------------------------------------------------------------
# Mutazioni generiche per vocabolari non-testuali
# (context_term, object_term, chronology_term)
# ---------------------------------------------------------------------------
_ALLOWED_VOCAB = {"context_term", "object_term", "chronology_term"}


def _check_vocab(table):
    if table not in _ALLOWED_VOCAB:
        raise ValueError(f"Table not allowed: {table}")


def create_generic_term(conn, table, preferred_label, term_type=None,
                        description=None, extra=None):
    _check_vocab(table)
    label = (preferred_label or "").strip()
    if not label:
        raise ValueError("preferred_label is required.")
    cols = {"uid": new_uid(), "preferred_label": label,
            "description": description, "is_active": 1}
    # term_type esiste per context/object; per chronology no
    if table != "chronology_term":
        cols["term_type"] = term_type or "other"
    if extra and table == "chronology_term":
        for k in ("year_from", "year_to", "precision"):
            if k in extra and extra[k] not in (None, ""):
                cols[k] = extra[k]
    keys = ",".join(cols.keys())
    placeholders = ",".join("?" for _ in cols)
    tid = conn.execute(f"INSERT INTO {table} ({keys}) VALUES ({placeholders})",
                       tuple(cols.values())).lastrowid
    conn.commit()
    return {"id": tid, "preferred_label": label,
            "term_type": cols.get("term_type"),
            "table": table}


def update_generic_term(conn, table, term_id, fields, user_id=None):
    _check_vocab(table)
    cur = conn.execute(f"SELECT * FROM {table} WHERE id=?", (term_id,)).fetchone()
    if not cur:
        raise ValueError("Term not found.")
    sets, vals = [], []
    updatable = ["preferred_label", "description", "notes"]
    if table != "chronology_term":
        updatable.append("term_type")
    else:
        updatable += ["year_from", "year_to", "precision"]
    for k in updatable:
        if k in fields:
            v = fields[k]
            if k == "preferred_label":
                v = (v or "").strip()
                if not v:
                    raise ValueError("preferred_label cannot be empty.")
            if k in ("year_from", "year_to") and v not in (None, ""):
                try: v = int(v)
                except Exception: raise ValueError(f"{k} must be an integer.")
            sets.append(f"{k}=?"); vals.append(v if v != "" else None)
    if not sets:
        return term_id
    vals.append(term_id)
    conn.execute(f"UPDATE {table} SET {','.join(sets)} WHERE id=?", vals)
    _log(conn, table, term_id, "update", before=dict(cur), after=fields, user=user_id)
    conn.commit()
    return term_id


def delete_generic_term(conn, table, term_id, user_id=None):
    _check_vocab(table)
    cur = conn.execute(f"SELECT * FROM {table} WHERE id=?", (term_id,)).fetchone()
    if not cur:
        raise ValueError("Term not found.")
    # controllo uso
    if table == "chronology_term":
        used = (conn.execute("SELECT count(*) FROM context_chronology WHERE chronology_term_id=?",
                             (term_id,)).fetchone()[0]
                + conn.execute("SELECT count(*) FROM object_chronology WHERE chronology_term_id=?",
                               (term_id,)).fetchone()[0])
        if used:
            raise ValueError(f"Cannot delete this term: it is used in {used} dating record(s).")
    else:
        assign = table.replace("_term", "_term_assignment")
        used = conn.execute(f"SELECT count(*) FROM {assign} WHERE term_id=?", (term_id,)).fetchone()[0]
        if used:
            raise ValueError(f"Cannot delete this term: it is used in {used} assignment(s).")
    conn.execute(f"DELETE FROM {table} WHERE id=?", (term_id,))
    _log(conn, table, term_id, "other", before=dict(cur), user=user_id, note="delete")
    conn.commit()
    return True


def add_generic_term_relation(conn, table, source_id, target_id, relation_code,
                              certainty_code=None, user_id=None):
    _check_vocab(table)
    rel_table = f"{table}_relation"
    if source_id == target_id:
        raise ValueError("Source and target cannot be the same.")
    for tid in (source_id, target_id):
        if not conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (tid,)).fetchone():
            raise ValueError(f"{table} record not found.")
    rel_id, hierarchical = _rel_id(conn, relation_code)
    if hierarchical:
        anc = {a["id"] for a in models.ancestors(conn, table, target_id)}
        if source_id in anc:
            raise ValueError("This relation would create a cycle in the hierarchy.")
    try:
        # chronology_term_relation ha created_at; context/object no
        if table == "chronology_term":
            conn.execute(f"INSERT INTO {rel_table} (source_term_id,target_term_id,relation_type_id,"
                         f"certainty_id,created_at) VALUES (?,?,?,?,?)",
                         (source_id, target_id, rel_id, _cert_id(conn, certainty_code), now_iso()))
        else:
            conn.execute(f"INSERT INTO {rel_table} (source_term_id,target_term_id,relation_type_id,"
                         f"certainty_id) VALUES (?,?,?,?)",
                         (source_id, target_id, rel_id, _cert_id(conn, certainty_code)))
    except Exception:
        raise ValueError("The relation already exists.")
    conn.commit()
    return True


def remove_generic_term_relation(conn, table, source_id, target_id, relation_code):
    _check_vocab(table)
    rid, _ = _rel_id(conn, relation_code)
    conn.execute(f"DELETE FROM {table}_relation WHERE source_term_id=? AND target_term_id=? "
                 f"AND relation_type_id=?", (source_id, target_id, rid))
    conn.commit()
    return True


# etichette alternative (solo context_term e object_term)
def add_generic_term_label(conn, table, term_id, label, language=None,
                           label_type="alternative", script=None, is_preferred=False):
    _check_vocab(table)
    if table == "chronology_term":
        raise ValueError("chronology_term does not support alternative labels.")
    if not conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (term_id,)).fetchone():
        raise ValueError("Term not found.")
    label = (label or "").strip()
    if not label:
        raise ValueError("The label cannot be empty.")
    if label_type not in LABEL_TYPES:
        label_type = "alternative"
    lid = conn.execute(
        f"INSERT INTO {table}_label ({table}_id,language,label,label_type,is_preferred) "
        f"VALUES (?,?,?,?,?)",
        (term_id, language, label, label_type, 1 if is_preferred else 0)).lastrowid
    conn.commit()
    return lid


def remove_generic_term_label(conn, table, label_id):
    _check_vocab(table)
    if table == "chronology_term":
        raise ValueError("chronology_term does not have labels.")
    conn.execute(f"DELETE FROM {table}_label WHERE id={int(label_id)}")
    conn.commit()
    return True


# ---------------------------------------------------------------------------
# Iterazione 2 · Contesti e oggetti — editing dei nuovi campi archeologici
# ---------------------------------------------------------------------------
DEPOSIT_TYPES = ("fill", "floor", "burial", "cut", "structure",
                 "midden", "abandonment", "surface", "other")
EXCAVATION_TECHNIQUES = ("stratigraphic", "arbitrary", "mixed",
                          "surface", "test_pit", "other")

# Colonne editabili per context / object (usate dalle route PATCH)
CONTEXT_EDITABLE = ("code", "name", "description", "source_reference", "notes",
                    "deposit_type", "excavation_technique",
                    "excavation_method_note", "preservation_note")
OBJECT_EDITABLE = ("inventory_number", "label", "record_kind", "description",
                   "condition_note", "completeness_percentage", "notes",
                   "decoration_present", "decoration_note",
                   "restored", "restoration_date", "restoration_note")


def _validate_context_fields(fields):
    if "deposit_type" in fields and fields["deposit_type"] not in (None, "") \
            and fields["deposit_type"] not in DEPOSIT_TYPES:
        raise ValueError(f"Invalid deposit_type: {fields['deposit_type']}")
    if "excavation_technique" in fields and fields["excavation_technique"] not in (None, "") \
            and fields["excavation_technique"] not in EXCAVATION_TECHNIQUES:
        raise ValueError(f"Invalid excavation_technique: {fields['excavation_technique']}")


def update_context(conn, context_id, fields, user_id=None):
    cur = conn.execute("SELECT * FROM context WHERE id=?", (context_id,)).fetchone()
    if not cur:
        raise ValueError("Context not found.")
    _validate_context_fields(fields)
    sets, vals = [], []
    for k in CONTEXT_EDITABLE:
        if k in fields:
            v = fields[k] if fields[k] != "" else None
            sets.append(f"{k}=?"); vals.append(v)
    if not sets:
        return context_id
    sets.append("updated_at=?"); vals.append(now_iso())
    if user_id:
        sets.append("updated_by=?"); vals.append(user_id)
    vals.append(context_id)
    conn.execute(f"UPDATE context SET {','.join(sets)} WHERE id=?", vals)
    _log(conn, "context", context_id, "update", before=dict(cur), after=fields, user=user_id)
    conn.commit()
    return context_id


def update_object(conn, object_id, fields, user_id=None):
    cur = conn.execute("SELECT * FROM object WHERE id=?", (object_id,)).fetchone()
    if not cur:
        raise ValueError("Object not found.")
    # bool coercion
    for b in ("decoration_present", "restored"):
        if b in fields and fields[b] not in (None, ""):
            fields[b] = 1 if fields[b] in (True, 1, "1", "true", "on") else 0
    if "completeness_percentage" in fields and fields["completeness_percentage"] not in (None, ""):
        try:
            fields["completeness_percentage"] = float(fields["completeness_percentage"])
        except Exception:
            raise ValueError("completeness_percentage must be a number.")
        if not (0 <= fields["completeness_percentage"] <= 100):
            raise ValueError("completeness_percentage must be between 0 and 100.")
    sets, vals = [], []
    for k in OBJECT_EDITABLE:
        if k in fields:
            v = fields[k] if fields[k] != "" else None
            sets.append(f"{k}=?"); vals.append(v)
    if not sets:
        return object_id
    sets.append("updated_at=?"); vals.append(now_iso())
    if user_id:
        sets.append("updated_by=?"); vals.append(user_id)
    vals.append(object_id)
    conn.execute(f"UPDATE object SET {','.join(sets)} WHERE id=?", vals)
    _log(conn, "object", object_id, "update", before=dict(cur), after=fields, user=user_id)
    conn.commit()
    return object_id


# ---------------------------------------------------------------------------
# Iterazione 2 · Cronologia — datazioni multiple per context / object
# ---------------------------------------------------------------------------
DATING_METHODS = ("stratigraphic_context", "palaeography", "stylistic",
                   "radiocarbon", "dendrochronology", "typological",
                   "epigraphic", "historical", "other")


def _validate_dating(fields):
    if "dating_method" in fields and fields["dating_method"] and \
            fields["dating_method"] not in DATING_METHODS:
        raise ValueError(f"Invalid dating_method: {fields['dating_method']}")
    y_from = fields.get("absolute_from")
    y_to = fields.get("absolute_to")
    if y_from not in (None, "") and y_to not in (None, ""):
        try:
            yf, yt = int(y_from), int(y_to)
        except (TypeError, ValueError):
            raise ValueError("Years must be integers using astronomical numbering, where 1 BCE = 0.")
        if yf > yt:
            raise ValueError("absolute_from must be less than or equal to absolute_to.")


def _resolve_chronology_term(conn, term_id_or_none, absolute_from, absolute_to):
    """Se fornito il termine cronologico e i due anni sono vuoti, li deriva
    dai year_from/year_to del termine. Ritorna (term_id, y_from, y_to)."""
    if term_id_or_none and (absolute_from in (None, "") or absolute_to in (None, "")):
        row = conn.execute("SELECT year_from, year_to FROM chronology_term WHERE id=?",
                           (term_id_or_none,)).fetchone()
        if row:
            if absolute_from in (None, ""):
                absolute_from = row["year_from"]
            if absolute_to in (None, ""):
                absolute_to = row["year_to"]
    return term_id_or_none, absolute_from, absolute_to


def add_dating(conn, owner_kind, owner_id, chronology_term_id=None,
               absolute_from=None, absolute_to=None, dating_method=None,
               certainty_code=None, note=None, user_id=None):
    """Aggiunge una datazione a un context o object. L'utente sceglie:
      (a) un chronology_term esistente (gli anni si prendono da lì),
      (b) valori assoluti liberi + metodo + certezza,
      (c) entrambi (il termine per riferimento + valori sovrascritti)."""
    if owner_kind not in ("context", "object"):
        raise ValueError("owner_kind must be 'context' or 'object'.")
    if not conn.execute(f"SELECT 1 FROM {owner_kind} WHERE id=?", (owner_id,)).fetchone():
        raise ValueError(f"{owner_kind} not found.")
    if chronology_term_id and not conn.execute(
            "SELECT 1 FROM chronology_term WHERE id=?", (chronology_term_id,)).fetchone():
        raise ValueError("Chronology term not found.")
    _validate_dating({"dating_method": dating_method,
                       "absolute_from": absolute_from, "absolute_to": absolute_to})
    ctid, a_from, a_to = _resolve_chronology_term(conn, chronology_term_id,
                                                    absolute_from, absolute_to)
    # né termine né anni: senza senso
    if not ctid and a_from in (None, "") and a_to in (None, ""):
        raise ValueError("Provide at least one chronology term or an absolute interval.")

    table = f"{owner_kind}_chronology"
    owner_col = f"{owner_kind}_id"
    def _to_int(v):
        return int(v) if v not in (None, "") else None
    cols = {owner_col: owner_id,
            "chronology_term_id": ctid,
            "absolute_from": _to_int(a_from),
            "absolute_to": _to_int(a_to),
            "certainty_id": _cert_id(conn, certainty_code),
            "dating_method": dating_method or None,
            "note": note,
            "created_by": user_id}
    # object_chronology ha anche created_at; context_chronology no
    if owner_kind == "object":
        cols["created_at"] = now_iso()
    keys = ",".join(cols.keys())
    ph = ",".join("?" for _ in cols)
    did = conn.execute(f"INSERT INTO {table} ({keys}) VALUES ({ph})",
                       tuple(cols.values())).lastrowid
    _log(conn, table, did, "create", after=cols, user=user_id)
    conn.commit()
    return did


def update_dating(conn, owner_kind, dating_id, fields, user_id=None):
    if owner_kind not in ("context", "object"):
        raise ValueError("owner_kind must be 'context' or 'object'.")
    table = f"{owner_kind}_chronology"
    cur = conn.execute(f"SELECT * FROM {table} WHERE id=?", (dating_id,)).fetchone()
    if not cur:
        raise ValueError("Dating record not found.")
    _validate_dating(fields)
    editable = ("chronology_term_id", "absolute_from", "absolute_to",
                "dating_method", "note")
    sets, vals = [], []
    for k in editable:
        if k in fields:
            v = fields[k] if fields[k] != "" else None
            if k in ("absolute_from", "absolute_to") and v is not None:
                try: v = int(v)
                except Exception: raise ValueError(f"{k} must be an integer.")
            sets.append(f"{k}=?"); vals.append(v)
    if "certainty_code" in fields:
        sets.append("certainty_id=?"); vals.append(_cert_id(conn, fields["certainty_code"]))
    if not sets:
        return dating_id
    vals.append(dating_id)
    conn.execute(f"UPDATE {table} SET {','.join(sets)} WHERE id=?", vals)
    _log(conn, table, dating_id, "update", before=dict(cur), after=fields, user=user_id)
    conn.commit()
    return dating_id


def delete_dating(conn, owner_kind, dating_id, user_id=None):
    if owner_kind not in ("context", "object"):
        raise ValueError("owner_kind must be 'context' or 'object'.")
    table = f"{owner_kind}_chronology"
    cur = conn.execute(f"SELECT * FROM {table} WHERE id=?", (dating_id,)).fetchone()
    if not cur:
        raise ValueError("Dating record not found.")
    conn.execute(f"DELETE FROM {table} WHERE id=?", (dating_id,))
    _log(conn, table, dating_id, "other", before=dict(cur), user=user_id, note="delete")
    conn.commit()
    return True


# assegnazioni di termini a context/object (in-place dalla scheda)
def add_term_assignment(conn, owner_kind, owner_id, term_id, certainty_code=None,
                        note=None, user_id=None):
    if owner_kind not in ("context", "object"):
        raise ValueError("owner_kind must be 'context' or 'object'.")
    table = f"{owner_kind}_term_assignment"
    owner_col = f"{owner_kind}_id"
    try:
        aid = conn.execute(
            f"INSERT INTO {table} ({owner_col},term_id,certainty_id,note,created_by,created_at) "
            f"VALUES (?,?,?,?,?,?)",
            (owner_id, term_id, _cert_id(conn, certainty_code), note, user_id, now_iso())).lastrowid
    except Exception:
        raise ValueError("The term is already assigned.")
    conn.commit()
    return aid


def remove_term_assignment(conn, owner_kind, assignment_id):
    if owner_kind not in ("context", "object"):
        raise ValueError("owner_kind must be 'context' or 'object'.")
    conn.execute(f"DELETE FROM {owner_kind}_term_assignment WHERE id=?", (assignment_id,))
    conn.commit()
    return True
