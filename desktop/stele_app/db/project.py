"""
Ciclo di vita del progetto Stele: creazione/apertura del database,
generazione delle junction ripetitive, seeding dei vocabolari e dati demo.
"""
import os
import uuid
import datetime
import unicodedata

from . import geopackage as gpkg
from .database import connect_sqlite

HERE = os.path.dirname(__file__)


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_uid():
    return str(uuid.uuid4())


def nfc(s):
    return unicodedata.normalize("NFC", s) if s else s


def _read(fname):
    with open(os.path.join(HERE, fname), "r", encoding="utf-8") as f:
        return f.read()


# --- junction bibliografia/media (generate) --------------------------------
BIBLIO_JUNCTIONS = [
    ("context_bibliography", "context_id", "context"),
    ("object_bibliography", "object_id", "object"),
    ("text_document_bibliography", "text_document_id", "text_document"),
    ("text_version_bibliography", "text_version_id", "text_version"),
    ("annotation_bibliography", "annotation_id", "annotation"),
    ("text_term_bibliography", "text_term_id", "text_term"),
    ("object_term_bibliography", "object_term_id", "object_term"),
    ("context_term_bibliography", "context_term_id", "context_term"),
    ("chronology_term_bibliography", "chronology_term_id", "chronology_term"),
    ("object_relation_bibliography", "object_relation_id", "object_relation"),
    ("apparatus_reading_bibliography", "apparatus_reading_id", "apparatus_reading"),
]
MEDIA_JUNCTIONS = [
    ("context_media", "context_id", "context"),
    ("object_media", "object_id", "object"),
    ("text_document_media", "text_document_id", "text_document"),
    ("text_version_media", "text_version_id", "text_version"),
    ("annotation_media", "annotation_id", "annotation"),
]


def _create_junctions(conn):
    for t, ecol, ref in BIBLIO_JUNCTIONS:
        conn.execute(f"""
          CREATE TABLE {t} (
            id INTEGER PRIMARY KEY,
            {ecol} INTEGER NOT NULL REFERENCES {ref}(id) ON DELETE CASCADE,
            bibliography_id INTEGER NOT NULL REFERENCES bibliography(id) ON DELETE RESTRICT,
            locator TEXT, role TEXT NOT NULL, note TEXT,
            created_by INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL,
            UNIQUE({ecol}, bibliography_id, locator, role)
          ) STRICT;""")
    for t, ecol, ref in MEDIA_JUNCTIONS:
        conn.execute(f"""
          CREATE TABLE {t} (
            id INTEGER PRIMARY KEY,
            {ecol} INTEGER NOT NULL REFERENCES {ref}(id) ON DELETE CASCADE,
            media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE RESTRICT,
            role TEXT NOT NULL, caption TEXT, sequence INTEGER,
            created_by INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL,
            UNIQUE({ecol}, media_id, role)
          ) STRICT;""")


# --- helper di inserimento --------------------------------------------------
class Ins:
    """Piccolo helper: inserisce e ritorna lastrowid; aggiunge uid/created_at/
    updated_at automaticamente se non forniti e se la colonna esiste."""
    def __init__(self, conn):
        self.conn = conn
        self._cols = {}

    def cols(self, table):
        if table not in self._cols:
            rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
            self._cols[table] = {r["name"] for r in rows}
        return self._cols[table]

    def __call__(self, table, **vals):
        cols = self.cols(table)
        if "uid" in cols and "uid" not in vals:
            vals["uid"] = new_uid()
        ts = now_iso()
        for c in ("created_at", "updated_at"):
            if c in cols and c not in vals:
                vals[c] = ts
        keys = [k for k in vals if k in cols]
        ph = ",".join("?" for _ in keys)
        sql = f"INSERT INTO {table} ({','.join(keys)}) VALUES ({ph})"
        cur = self.conn.execute(sql, [vals[k] for k in keys])
        return cur.lastrowid


# --- seeding vocabolari di dominio -----------------------------------------
def seed_domain_vocabularies(conn):
    ins = Ins(conn)
    rel = {r["code"]: r["id"] for r in conn.execute("SELECT id,code FROM relation_type")}

    def term(table, term_type, label, **extra):
        return ins(table, term_type=term_type, preferred_label=label, **extra)

    def relate(table, src, tgt, code):
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        fields = ["source_term_id", "target_term_id", "relation_type_id"]
        vals = [src, tgt, rel[code]]
        if "created_at" in cols:
            fields.append("created_at"); vals.append(now_iso())
        ph = ",".join("?" for _ in fields)
        conn.execute(f"INSERT INTO {table} ({','.join(fields)}) VALUES ({ph})", vals)

    ids = {"context": {}, "object": {}, "text": {}, "chron": {}}

    # context_term
    ct = ids["context"]
    for tt, labels in {
        "culture": ["Roman", "Republican Roman", "Imperial Roman", "Greek", "Hellenistic", "Etruscan"],
        "context_function": ["Cultic area", "Domestic area", "Funerary area",
                             "Production area", "Administrative area", "Military area"],
        "site_type": ["Sanctuary", "Temple", "Necropolis", "Settlement",
                      "Workshop", "Villa", "Fortification"],
    }.items():
        for lb in labels:
            ct[lb] = term("context_term", tt, lb)
    relate("context_term_relation", ct["Republican Roman"], ct["Roman"], "IS_A")
    relate("context_term_relation", ct["Imperial Roman"], ct["Roman"], "IS_A")

    # object_term (morfologia/supporto + materiale) con gerarchia della spec
    ot = ids["object"]
    support = ["Ceramic support", "Vessel", "Amphora", "Dressel amphora", "Tablet",
               "Stone slab", "Stele", "Wall surface", "Metal object", "Coin",
               "Seal", "Ostracon"]
    for lb in support:
        ot[lb] = term("object_term", "support_type", lb)
    materials = ["Ceramic", "Stone", "Marble", "Limestone", "Bronze", "Iron",
                 "Lead", "Gold", "Silver", "Wood", "Papyrus", "Bone", "Ivory", "Plaster"]
    for lb in materials:
        ot[lb] = term("object_term", "material", lb)
    ot["Ceramic tablet"] = term("object_term", "support_type", "Ceramic tablet")
    relate("object_term_relation", ot["Dressel amphora"], ot["Amphora"], "IS_A")
    relate("object_term_relation", ot["Amphora"], ot["Vessel"], "IS_A")
    relate("object_term_relation", ot["Vessel"], ot["Ceramic support"], "IS_A")
    relate("object_term_relation", ot["Ceramic tablet"], ot["Tablet"], "IS_A")
    relate("object_term_relation", ot["Ceramic tablet"], ot["Ceramic support"], "IS_A")

    # text_term (esempio Minerva + fenomeni editoriali + formule)
    tt = ids["text"]
    tt["Minerva"] = term("text_term", "deity", "Minerva",
                         description="Roman goddess of wisdom and war.")
    tt["Roman deity"] = term("text_term", "deity", "Roman deity")
    tt["Female deity"] = term("text_term", "deity", "Female deity")
    tt["War deity"] = term("text_term", "deity", "War deity")
    tt["Classical pantheon"] = term("text_term", "concept", "Classical pantheon")
    tt["Standard dedicatory formula"] = term("text_term", "formula", "Standard dedicatory formula")
    for lb in ["Abbreviation", "Expansion", "Lacuna", "Supplied text", "Unclear reading",
               "Ligature", "Damaged text"]:
        tt[lb] = term("text_term", "editorial_feature", lb)
    relate("text_term_relation", tt["Minerva"], tt["Roman deity"], "IS_A")
    relate("text_term_relation", tt["Minerva"], tt["Female deity"], "IS_A")
    relate("text_term_relation", tt["Minerva"], tt["War deity"], "IS_A")
    relate("text_term_relation", tt["Roman deity"], tt["Classical pantheon"], "IS_A")
    # etichette alternative di Minerva
    conn.execute("INSERT INTO text_term_label (term_id,language,label,label_type,is_preferred) "
                 "VALUES (?,?,?,?,1)", (tt["Minerva"], "la", "Minerva", "preferred"))
    for ab in ("Miner.", "Min."):
        conn.execute("INSERT INTO text_term_label (term_id,language,label,label_type,is_preferred) "
                     "VALUES (?,?,?,?,0)", (tt["Minerva"], "la", ab, "abbreviation"))

    # chronology_term con gerarchia
    chr_ = ids["chron"]
    def cterm(label, yf=None, yt=None, prec="conventional"):
        return ins("chronology_term", preferred_label=label, year_from=yf, year_to=yt, precision=prec)
    chr_["Roman period"] = cterm("Roman period", -509, 476)
    chr_["Roman Imperial period"] = cterm("Roman Imperial period", -27, 476)
    chr_["Early Empire"] = cterm("Early Empire", -27, 96)
    chr_["Augustan Age"] = cterm("Augustan Age", -27, 14, "approximate")
    relate("chronology_term_relation", chr_["Augustan Age"], chr_["Early Empire"], "PART_OF")
    relate("chronology_term_relation", chr_["Early Empire"], chr_["Roman Imperial period"], "IS_A")
    relate("chronology_term_relation", chr_["Roman Imperial period"], chr_["Roman period"], "IS_A")
    return ids


# --- creazione progetto -----------------------------------------------------
def create_project(db_path, with_demo=True, overwrite=False):
    if os.path.exists(db_path):
        if overwrite:
            for suff in ("", "-wal", "-shm"):
                p = db_path + suff
                if os.path.exists(p):
                    os.remove(p)
        else:
            raise FileExistsError(f"Il file esiste già: {db_path}")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = connect_sqlite(db_path)
    try:
        gpkg.init_geopackage(conn)
        conn.executescript(_read("schema_sqlite.sql"))
        _create_junctions(conn)
        conn.executescript(_read("seeds.sql"))
        seed_domain_vocabularies(conn)
        # registra le feature table spaziali
        gpkg.register_feature_table(conn, "context", "GEOMETRY",
                                    description="Contesti di provenienza")
        gpkg.register_feature_table(conn, "text_term_place", "POINT",
                                    description="Luoghi citati nel testo")
        conn.commit()
        if with_demo:
            load_demo(conn)
            conn.commit()
    finally:
        conn.close()
    return db_path


def open_project(db_path):
    if not os.path.exists(db_path):
        raise FileNotFoundError(db_path)
    conn = connect_sqlite(db_path)
    # migrazioni non-distruttive per progetti creati con versioni precedenti
    from . import migrations
    migrations.apply_migrations(conn)
    return conn


def rebuild_fts(conn):
    conn.execute("DELETE FROM text_version_fts;")
    conn.execute("INSERT INTO text_version_fts (rowid, content, text_version_id) "
                 "SELECT id, content, id FROM text_version;")


# --- dati demo (esempio della specifica + tavoletta KN Fk 1) ---------------
def load_demo(conn):
    ins = Ins(conn)
    cl = {r["code"]: r["id"] for r in conn.execute("SELECT id,code FROM certainty_level")}
    rl = {r["code"]: r["id"] for r in conn.execute("SELECT id,code FROM reliability_level")}
    rel = {r["code"]: r["id"] for r in conn.execute("SELECT id,code FROM relation_type")}
    ot = {r["preferred_label"]: r["id"] for r in conn.execute("SELECT id,preferred_label FROM object_term")}
    ctx_term = {r["preferred_label"]: r["id"] for r in conn.execute("SELECT id,preferred_label FROM context_term")}
    tt = {r["preferred_label"]: r["id"] for r in conn.execute("SELECT id,preferred_label FROM text_term")}
    chron = {r["preferred_label"]: r["id"] for r in conn.execute("SELECT id,preferred_label FROM chronology_term")}

    user = ins("app_user", display_name="Marco Di Giovanni", affiliation="Stele demo")

    # --- contesto (con geometria puntuale: Sanctuary area A, presso Tebe/Beozia)
    ctx = ins("context", code="CTX-A-001", name="Sanctuary area A",
              description="Area cultuale, livello IIIb.",
              geometry=gpkg.encode_point(23.318, 38.322),
              geometry_precision="approximate", reliability_id=rl["high"],
              source_reference="Thespiai 2021–2023", created_by=user, updated_by=user)
    for lbl in ("Cultic area", "Roman", "Sanctuary"):
        if lbl in ctx_term:
            ins("context_term_assignment", context_id=ctx, term_id=ctx_term[lbl],
                certainty_id=cl["certain"], created_by=user)
    ins("context_chronology", context_id=ctx, chronology_term_id=chron.get("Roman Imperial period"),
        absolute_from=-100, absolute_to=100, certainty_id=cl["probable"],
        dating_method="archaeological_context")

    # --- oggetto ricostruito TAB001 + tre frammenti
    tab = ins("object", inventory_number="MC-12-001", label="TAB001",
              record_kind="reconstructed_object",
              description="Tavoletta ricostruita in Lineare B.",
              completeness_percentage=78, condition_note="Superficie leggermente abrasa.",
              created_by=user, updated_by=user)
    frags = {}
    for code, cov in (("FR001", 92), ("FR003", 65), ("FR012", 88)):
        fid = ins("object", inventory_number="MC-12-001-" + code, label=code,
                  record_kind="fragment", completeness_percentage=cov, created_by=user, updated_by=user)
        frags[code] = fid
        ins("object_composition", parent_object_id=tab, component_object_id=fid,
            certainty_id=cl["certain"])
    ins("object_context", object_id=tab, context_id=ctx, relation_role="findspot",
        certainty_id=cl["probable"])
    for mt, val, unit in (("height", 10.2, "cm"), ("width", 8.1, "cm"), ("thickness", 1.8, "cm"),
                          ("weight", 312.4, "g")):
        ins("object_measurement", object_id=tab, measurement_type=mt, value=val, unit=unit,
            qualifier="preserved", certainty_id=cl["certain"])
    for lbl in ("Ceramic tablet", "Tablet", "Ceramic"):
        if lbl in ot:
            ins("object_term_assignment", object_id=tab, term_id=ot[lbl],
                certainty_id=cl["certain"], created_by=user)
    ins("object_chronology", object_id=tab, chronology_term_id=chron.get("Roman Imperial period"),
        absolute_from=-100, absolute_to=100, certainty_id=cl["probable"], dating_method="palaeography",
        created_by=user)
    # una seconda tavoletta per la relazione SAME_SCRIBE
    tab2 = ins("object", inventory_number="MC-12-002", label="TAB002",
               record_kind="reconstructed_object", description="Tavoletta associata.",
               created_by=user, updated_by=user)
    ins("object_relation", source_object_id=tab, target_object_id=tab2,
        relation_type_id=rel["SAME_SCRIBE"], certainty_id=cl["probable"],
        rationale="Ductus e segni caratteristici concordanti.", status="accepted",
        asserted_by=user)

    # --- documento di testo + versioni PARALLELE allineate riga↔riga --------
    # Modello (b): un solo text_document con più text_version di *tipi diversi*.
    # La versione principale è la diplomatic_transcription (fedele al supporto).
    # Le altre (traslitterazione, traduzione) sono letture parallele.
    doc = ins("text_document", object_id=tab, siglum="TAB001-text-LB",
              title="Iscrizione in Lineare B", surface="recto",
              main_language="gmy", script="Linb",
              description="Testo dimostrativo su tavoletta ricostruita.", created_at=now_iso())

    # Versione principale: TRASCRIZIONE DIPLOMATICA (sillabari originali)
    v_dipl_content = nfc(
        "\U00010012\U0001001C\U00010030 \U00010030\U00010001\U0001001B\U00010001\U0001001F\n"
        "\U00010030 \U00010025\U00010001 \U00010030\U00010007\U0001001F"
    )  # due righe di Lineare B: "ko-no-so so-e-ni-e-qe" (illustrativa) / "so qe-e so-de-qe"
    # In realtà mettiamo qualcosa di leggibile a scopo demo, con struttura chiara:
    v_dipl_content = nfc(
        "\U00010012\U0001001C\U00010030 | \U00010000\U00010002\U00010012\U00010028\U00010029\U00010001 "
        "  \U00010025\U0001001F\U00010030\U00010028\U00010007\U0001001B"
    )
    # Righe illustrative con \n; le righe sono realmente 2 righe di segni Lineare B
    v_dipl_content = nfc(
        "\U00010012\U0001001C\U00010030   \U00010000\U00010002\U00010012\U00010028\U00010029\U00010001   \U00010025\U0001001F\U00010030\U00010028\U00010007\U0001001B\n"
        "\U00010028\U00010029\U00010030\U0001001B\U00010009\U00010001   \U00010007\U00010025\U00010028\U00010029\U00010028"
    )
    vdip = ins("text_version", text_document_id=doc, version_type="diplomatic_transcription",
               language="gmy", script="Linb", content=v_dipl_content, version_number=1,
               is_current=1, created_by=user, note="Trascrizione diplomatica (segni sul supporto).")
    dipl_units = []
    for i, ln in enumerate(v_dipl_content.split("\n"), start=1):
        uid_ = ins("text_unit", text_version_id=vdip, unit_type="line", label=f"Line {i}",
                   sequence=i)
        dipl_units.append(uid_)

    # Versione parallela: TRASLITTERAZIONE (segni resi in caratteri latini)
    v_trans_content = nfc(
        "ko-no-so | a-i-ke-re-u   qa-si-re-we\n"
        "e-re-si-ja   qe-re-si-je"
    )
    vtrans = ins("text_version", text_document_id=doc, version_type="transliteration",
                 language="gmy", script="Latn", content=v_trans_content, version_number=1,
                 is_current=1, created_by=user, based_on_version_id=vdip,
                 note="Traslitterazione in caratteri latini.")
    trans_units = []
    for i, ln in enumerate(v_trans_content.split("\n"), start=1):
        uid_ = ins("text_unit", text_version_id=vtrans, unit_type="line", label=f"Line {i}",
                   sequence=i)
        trans_units.append(uid_)

    # Versione parallela: TRADUZIONE italiana (lettura interpretativa)
    v_tr_content = nfc(
        "Cnosso: per Aikereu, al Qasirewe.\n"
        "Eresija (offerta): tre giare."
    )
    vtr = ins("text_version", text_document_id=doc, version_type="translation",
              language="it", script="Latn", content=v_tr_content, version_number=1,
              is_current=1, created_by=user, based_on_version_id=vdip,
              note="Traduzione italiana (lettura illustrativa).")
    tr_units = []
    for i, ln in enumerate(v_tr_content.split("\n"), start=1):
        uid_ = ins("text_unit", text_version_id=vtr, unit_type="line", label=f"Line {i}",
                   sequence=i)
        tr_units.append(uid_)

    # Allineamenti riga↔riga (gruppi N:M via text_unit_alignment)
    from .database import connect_sqlite  # noqa
    for i, dipl_uid in enumerate(dipl_units):
        gid = conn.execute("SELECT COALESCE(MAX(group_id),0)+1 FROM text_unit_alignment").fetchone()[0]
        conn.execute("INSERT INTO text_unit_alignment (group_id,text_unit_id,role,created_at) VALUES (?,?,?,?)",
                     (gid, dipl_uid, "primary", now_iso()))
        if i < len(trans_units):
            conn.execute("INSERT INTO text_unit_alignment (group_id,text_unit_id,role,created_at) VALUES (?,?,?,?)",
                         (gid, trans_units[i], "parallel", now_iso()))
        if i < len(tr_units):
            conn.execute("INSERT INTO text_unit_alignment (group_id,text_unit_id,role,created_at) VALUES (?,?,?,?)",
                         (gid, tr_units[i], "parallel", now_iso()))

    # --- annotazioni stand-off — SEMPRE sulla versione principale (diplomatica)
    def cp_index(text, sub, start=0):
        arr = list(text); s = list(sub)
        for i in range(start, len(arr) - len(s) + 1):
            if arr[i:i + len(s)] == s:
                return i, i + len(s)
        raise ValueError("substring non trovata: " + sub)

    def annotate_on(vid_target, content_target, sub, atype, term_labels,
                    note="", certainty="certain"):
        a = ins("annotation", text_version_id=vid_target, annotation_type=atype,
                certainty_id=cl[certainty], note=note, status="accepted", created_by=user)
        s, e = cp_index(content_target, sub)
        ins("annotation_span", annotation_id=a, start_position=s, end_position=e, sequence=1)
        for role_i, lbl in enumerate(term_labels):
            if lbl in tt:
                ins("annotation_term", annotation_id=a, term_id=tt[lbl],
                    role="primary" if role_i == 0 else "secondary", certainty_id=cl[certainty])
        return a

    # Creo i termini di dizionario che servono
    if "Aikereu" not in tt:
        tt["Aikereu"] = ins("text_term", term_type="person", preferred_label="Aikereu",
                            description="Antroponimo miceneo (lettura illustrativa).")
    if "Qasirewe" not in tt:
        tt["Qasirewe"] = ins("text_term", term_type="place", preferred_label="Qasirewe",
                            description="Toponimo/qualifica (lettura illustrativa).")
        ins("text_term_place", term_id=tt["Qasirewe"],
            geometry=gpkg.encode_point(23.318, 38.322),
            geometry_precision="approximate", geometry_source="demo")
        ins("text_term_external_id", term_id=tt["Qasirewe"], authority="GeoNames",
            identifier="000000", uri="https://www.geonames.org/")
    if "Konoso" not in tt:
        tt["Konoso"] = ins("text_term", term_type="place", preferred_label="Konoso",
                           description="Cnosso — centro palaziale (lettura illustrativa).")
        ins("text_term_place", term_id=tt["Konoso"],
            geometry=gpkg.encode_point(25.163, 35.298),
            geometry_precision="approximate", geometry_source="demo")

    # Annotazioni sulla DIPLOMATICA — offset in code point sui segni originali
    # Riga 1 di v_dipl_content: ko-no-so (3 segni), poi separatore, ecc.
    # Annotazione 1: "ko-no-so" (i primi 3 code point della riga 1)
    a1 = ins("annotation", text_version_id=vdip, annotation_type="named_entity",
             certainty_id=cl["certain"], note="Toponimo: Cnosso.", status="accepted", created_by=user)
    ins("annotation_span", annotation_id=a1, start_position=0, end_position=3, sequence=1)
    ins("annotation_term", annotation_id=a1, term_id=tt["Konoso"], role="primary", certainty_id=cl["certain"])
    # Annotazione 2: "a-i-ke-re-u" — 5 segni; li ricavo dal contenuto reale
    cp = list(v_dipl_content)
    # posizione dopo "ko-no-so   " (3 segni + 3 spazi = 6 code point)
    aike_start = 6
    aike_end = aike_start + 5  # 5 sillabogrammi
    a2 = ins("annotation", text_version_id=vdip, annotation_type="named_entity",
             certainty_id=cl["probable"], note="Nome proprio: Aikereu.", status="accepted", created_by=user)
    ins("annotation_span", annotation_id=a2, start_position=aike_start, end_position=aike_end, sequence=1)
    ins("annotation_term", annotation_id=a2, term_id=tt["Aikereu"], role="primary", certainty_id=cl["probable"])
    # Annotazione 3: "qa-si-re-we" — 4 segni finali di riga 1
    qasi_start = aike_end + 3  # 3 spazi
    qasi_end = qasi_start + 4
    a3 = ins("annotation", text_version_id=vdip, annotation_type="named_entity",
             certainty_id=cl["probable"], note="Toponimo/qualifica: Qasirewe.", status="accepted", created_by=user)
    ins("annotation_span", annotation_id=a3, start_position=qasi_start, end_position=qasi_end, sequence=1)
    ins("annotation_term", annotation_id=a3, term_id=tt["Qasirewe"], role="primary", certainty_id=cl["probable"])
    # Annotazione 4: relazione tra Aikereu e la formula standard (secondary)
    if "Standard dedicatory formula" in tt:
        ins("annotation_term", annotation_id=a2, term_id=tt["Standard dedicatory formula"],
            role="reference", certainty_id=cl["possible"])

    # --- bibliografia + collegamento
    bib = ins("bibliography", citation_key="DiGiovanni2021", entry_type="book",
              authors="Di Giovanni, M.", year=2021, title="I testi della Casa delle Tavolette",
              container_title="Quaderni di Micenologia", volume="14")
    conn.execute("INSERT INTO object_bibliography (object_id,bibliography_id,locator,role,created_at) "
                 "VALUES (?,?,?,?,?)", (tab, bib, "p. 134", "publication", now_iso()))

    # --- media + collegamento
    med = ins("media", media_type="photo", file_path="media/objects/MC-12-001_front.jpg",
              mime_type="image/jpeg", title="TAB001 recto", license="CC BY 4.0")
    conn.execute("INSERT INTO object_media (object_id,media_id,role,created_at) VALUES (?,?,?,?)",
                 (tab, med, "primary", now_iso()))

    rebuild_fts(conn)
