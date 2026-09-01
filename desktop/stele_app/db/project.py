"""
Ciclo di vita del progetto Stele: creazione/apertura del database,
generazione delle junction ripetitive, seeding dei vocabolari e dati demo.
"""
import os
import shutil
import uuid
import datetime
import unicodedata

from . import geopackage as gpkg
from .database import connect_sqlite

HERE = os.path.dirname(__file__)
DEMO_PROJECT = os.path.join(os.path.dirname(HERE), "data", "demo_project.gpkg")


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
            raise FileExistsError(f"The file already exists: {db_path}")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    # Release bundles ship with a canonical sample project. Copying that file
    # keeps the first-run dataset identical on every platform. Source builds
    # without the bundled resource still fall back to the generated demo below.
    if with_demo and os.path.exists(DEMO_PROJECT):
        shutil.copy2(DEMO_PROJECT, db_path)
        conn = connect_sqlite(db_path)
        try:
            from . import migrations
            migrations.apply_migrations(conn)
        finally:
            conn.close()
        return db_path

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


def has_sample_data(conn):
    """Return True when the canonical Stele sample corpus is present."""
    return bool(conn.execute(
        "SELECT 1 FROM app_user WHERE affiliation='Stele demo' LIMIT 1"
    ).fetchone())


def replace_sample_with_blank(conn, db_path):
    """Back up the current project and replace it with a clean project.

    The operation is deliberately limited to databases carrying the canonical
    sample marker. The backup is a complete GeoPackage and is written next to
    the live project before any data are changed.
    """
    if not has_sample_data(conn):
        raise ValueError("No sample dataset was found in this project.")

    project_dir = os.path.dirname(os.path.abspath(db_path))
    backup_dir = os.path.join(project_dir, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = os.path.join(backup_dir, f"project-before-sample-removal-{stamp}.gpkg")

    conn.commit()
    backup_conn = connect_sqlite(backup_path)
    try:
        conn.backup(backup_conn)
        backup_conn.commit()
    finally:
        backup_conn.close()

    blank_path = os.path.join(project_dir, f".stele-blank-{uuid.uuid4().hex}.gpkg")
    try:
        create_project(blank_path, with_demo=False, overwrite=False)
        blank_conn = connect_sqlite(blank_path)
        try:
            blank_conn.backup(conn)
            conn.commit()
        finally:
            blank_conn.close()
    finally:
        for suffix in ("", "-wal", "-shm"):
            candidate = blank_path + suffix
            if os.path.exists(candidate):
                os.unlink(candidate)

    return backup_path


def rebuild_fts(conn):
    conn.execute("DELETE FROM text_version_fts;")
    conn.execute("INSERT INTO text_version_fts (rowid, content, text_version_id) "
                 "SELECT id, content, id FROM text_version;")


# --- dati demo (esempio della specifica + tavoletta KN Fk 1) ---------------
# --- dati demo estesi: ~10 contesti, ~100 oggetti, ~150 frammenti ---------
# Arco cronologico: I sec a.C. → III sec d.C.
# Geografia: Roma + province (Ostia, Pompei, Aquileia, Ampurias/Hispania,
#   Massilia/Gallia, Verulamium/Britannia, Thysdrus/Africa, Efeso/Asia)
# Categorie: funerarie, votive, onorarie, amministrative, graffiti.
def load_demo(conn):
    """Dataset epigrafico latino su larga scala (~10 contesti, ~100 oggetti,
    ~150 frammenti). Dati verosimili, non certificati."""
    import random
    r = random.Random(42)  # seed fisso per riproducibilità

    ins = Ins(conn)
    cl = {row["code"]: row["id"] for row in conn.execute("SELECT id,code FROM certainty_level")}
    rl = {row["code"]: row["id"] for row in conn.execute("SELECT id,code FROM reliability_level")}
    rel = {row["code"]: row["id"] for row in conn.execute("SELECT id,code FROM relation_type")}
    ot = {row["preferred_label"]: row["id"] for row in conn.execute("SELECT id,preferred_label FROM object_term")}
    ctx_term = {row["preferred_label"]: row["id"] for row in conn.execute("SELECT id,preferred_label FROM context_term")}
    tt = {row["preferred_label"]: row["id"] for row in conn.execute("SELECT id,preferred_label FROM text_term")}
    chron = {row["preferred_label"]: row["id"] for row in conn.execute("SELECT id,preferred_label FROM chronology_term")}

    user = ins("app_user", display_name="A. Mommsen", affiliation="Stele demo")

    # ══════════════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════════════
    def _safe_tt_rel(src, tgt, rel_type_id):
        if not conn.execute(
            "SELECT 1 FROM text_term_relation WHERE source_term_id=? AND target_term_id=? AND relation_type_id=?",
            (src, tgt, rel_type_id)).fetchone():
            ins("text_term_relation", source_term_id=src, target_term_id=tgt,
                relation_type_id=rel_type_id)

    def add_tt(label, ttype, desc, parent_label=None, parent_rel="IS_A"):
        if label in tt:
            return tt[label]
        tid = ins("text_term", term_type=ttype, preferred_label=label, description=desc)
        tt[label] = tid
        if parent_label and parent_label in tt:
            _safe_tt_rel(tid, tt[parent_label], rel[parent_rel])
        return tid

    def add_place(label, desc, lon, lat, precision="approximate", parent=None):
        add_tt(label, "place", desc, parent)
        if not conn.execute("SELECT 1 FROM text_term_place WHERE term_id=?", (tt[label],)).fetchone():
            ins("text_term_place", term_id=tt[label],
                geometry=gpkg.encode_point(lon, lat),
                geometry_precision=precision, geometry_source="demo")

    def make_versions(doc_id, texts, user_id):
        versions = []
        for vtype, lang, scr, content, note in texts:
            vid = ins("text_version", text_document_id=doc_id,
                      version_type=vtype, language=lang, script=scr,
                      content=nfc(content), version_number=1, is_current=1,
                      created_by=user_id, note=note)
            units = []
            for i, ln in enumerate(content.split("\n"), start=1):
                # Trova la posizione reale (per gestire righe identiche uso l'indice progressivo)
                start = 0
                cursor = 0
                for k, existing in enumerate(content.split("\n")):
                    if k < i - 1:
                        cursor += len(existing) + 1  # +1 per \n
                    else:
                        start = cursor
                        break
                end = start + len(ln)
                uid_ = ins("text_unit", text_version_id=vid, unit_type="line",
                           label=f"l.{i}", sequence=i,
                           start_position=start, end_position=end)
                units.append(uid_)
            versions.append({"id": vid, "type": vtype, "units": units, "content": content})
            conn.execute("INSERT INTO text_version_fts (content, text_version_id) VALUES (?,?)",
                         (nfc(content), vid))
        # Allineamento riga↔riga
        if versions:
            max_lines = max(len(v["units"]) for v in versions)
            for i in range(max_lines):
                gid = conn.execute("SELECT COALESCE(MAX(group_id),0)+1 FROM text_unit_alignment").fetchone()[0]
                for vi, v in enumerate(versions):
                    if i < len(v["units"]):
                        role = "primary" if vi == 0 else "parallel"
                        conn.execute("""INSERT INTO text_unit_alignment
                            (group_id,text_unit_id,role,created_at) VALUES (?,?,?,?)""",
                            (gid, v["units"][i], role, now_iso()))
        return versions

    def annotate(vid, content, substring, atype, term_labels, certainty="certain"):
        if substring not in content:
            return None
        a = ins("annotation", text_version_id=vid, annotation_type=atype,
                certainty_id=cl[certainty], status="accepted", created_by=user)
        start = content.index(substring)
        end = start + len(substring)
        ins("annotation_span", annotation_id=a, start_position=start,
            end_position=end, sequence=1)
        for ri, lbl in enumerate(term_labels):
            if lbl in tt:
                ins("annotation_term", annotation_id=a, term_id=tt[lbl],
                    role="primary" if ri == 0 else "secondary",
                    certainty_id=cl[certainty])
        return a

    def add_measurements(obj_id, dims):
        for mt, val in dims.items():
            if val:
                ins("object_measurement", object_id=obj_id, measurement_type=mt,
                    value=val, unit="cm", qualifier="total",
                    certainty_id=cl["certain"])

    def add_terms(obj_id, labels, vocab="object"):
        seen = set()
        for lbl in labels:
            if lbl in seen:
                continue
            seen.add(lbl)
            if vocab == "object" and lbl in ot:
                if not conn.execute(
                    "SELECT 1 FROM object_term_assignment WHERE object_id=? AND term_id=?",
                    (obj_id, ot[lbl])).fetchone():
                    ins("object_term_assignment", object_id=obj_id, term_id=ot[lbl],
                        certainty_id=cl["certain"], created_by=user)
            elif vocab == "context" and lbl in ctx_term:
                if not conn.execute(
                    "SELECT 1 FROM context_term_assignment WHERE context_id=? AND term_id=?",
                    (obj_id, ctx_term[lbl])).fetchone():
                    ins("context_term_assignment", context_id=obj_id, term_id=ctx_term[lbl],
                        certainty_id=cl["certain"], created_by=user)

    # ══════════════════════════════════════════════════════════════════════
    # VOCABOLARIO SEMANTICO ESTESO
    # ══════════════════════════════════════════════════════════════════════
    # Divinità (gerarchia estesa)
    add_tt("Deity", "concept", "A divine being worshipped in cult practice.")
    add_tt("Roman deity", "concept", "Deity of the Roman pantheon.", "Deity")
    add_tt("Greek deity", "concept", "Deity of the Greek pantheon (also worshipped in the Roman world).", "Deity")
    add_tt("Oriental deity", "concept", "Deity of Eastern origin, adopted in the Roman world.", "Deity")
    add_tt("Iuppiter", "deity", "Jupiter, king of the gods.", "Roman deity")
    add_tt("Iuno", "deity", "Juno, queen of the gods, protector of women.", "Roman deity")
    add_tt("Minerva", "deity", "Minerva, goddess of wisdom and craft.", "Roman deity")
    add_tt("Mars", "deity", "Mars, god of war and agriculture.", "Roman deity")
    add_tt("Venus", "deity", "Venus, goddess of love.", "Roman deity")
    add_tt("Mercurius", "deity", "Mercury, messenger and god of commerce.", "Roman deity")
    add_tt("Apollo", "deity", "Apollo, god of light, music, prophecy.", "Roman deity")
    add_tt("Diana", "deity", "Diana, goddess of the hunt and moon.", "Roman deity")
    add_tt("Vulcanus", "deity", "Vulcan, god of fire and metalworking.", "Roman deity")
    add_tt("Ceres", "deity", "Ceres, goddess of agriculture.", "Roman deity")
    add_tt("Neptunus", "deity", "Neptune, god of the sea.", "Roman deity")
    add_tt("Hercules", "deity", "Hercules, deified hero.", "Roman deity")
    add_tt("Silvanus", "deity", "Silvanus, god of woods and boundaries.", "Roman deity")
    add_tt("Fortuna", "deity", "Fortuna, goddess of fortune.", "Roman deity")
    add_tt("Isis", "deity", "Isis, Egyptian goddess widely worshipped in the Empire.", "Oriental deity")
    add_tt("Mithras", "deity", "Mithras, Persian solar god, mystery cult.", "Oriental deity")
    add_tt("Sol Invictus", "deity", "Sol Invictus, official sun cult of the late Empire.", "Roman deity")

    add_tt("Female deity", "concept", "A female divine being.", "Deity")
    for f in ("Iuno","Minerva","Venus","Diana","Ceres","Fortuna","Isis"):
        _safe_tt_rel(tt[f], tt["Female deity"], rel["IS_A"])
    add_tt("War deity", "concept", "A deity associated with warfare.", "Deity")
    for f in ("Mars","Minerva"): _safe_tt_rel(tt[f], tt["War deity"], rel["IS_A"])

    # Formule
    add_tt("Funerary formula", "concept", "Standard expression in funerary inscriptions.")
    add_tt("Dis Manibus", "formula", "D(is) M(anibus) — to the spirits of the dead.", "Funerary formula")
    add_tt("Hic situs est", "formula", "H(ic) S(itus) E(st) — here lies.", "Funerary formula")
    add_tt("Bene merenti", "formula", "B(ene) M(erenti) — to the well-deserving.", "Funerary formula")
    add_tt("Vixit annis", "formula", "V(ixit) A(nnis) — lived years.", "Funerary formula")
    add_tt("Fecit filio", "formula", "Made for one's son/daughter (dedicant formula).", "Funerary formula")

    add_tt("Dedicatory formula", "concept", "Standard expression in votive inscriptions.")
    add_tt("Votum solvit", "formula", "V(otum) S(olvit) L(ibens) M(erito).", "Dedicatory formula")
    add_tt("Sacrum", "formula", "Sacrum — sacred (dedication to a deity).", "Dedicatory formula")
    add_tt("Ex voto", "formula", "Ex voto — in fulfilment of a vow.", "Dedicatory formula")
    add_tt("Pro salute", "formula", "Pro salute — for the well-being of.", "Dedicatory formula")

    add_tt("Honorary formula", "concept", "Standard expression in honorary inscriptions.")
    add_tt("Optimo principi", "formula", "O(ptimo) P(rincipi) — to the best emperor.", "Honorary formula")
    add_tt("Ob merita", "formula", "Ob merita — for his merits.", "Honorary formula")

    # Ruoli sociali/militari/civili
    add_tt("Military rank", "concept", "A rank in the Roman military hierarchy.")
    add_tt("Praefectus cohortis", "title", "Prefect of a cohort.", "Military rank")
    add_tt("Centurio", "title", "Centurion.", "Military rank")
    add_tt("Legatus", "title", "Legate, commander of a legion.", "Military rank")
    add_tt("Tribunus militum", "title", "Military tribune.", "Military rank")
    add_tt("Miles", "title", "Common soldier.", "Military rank")
    add_tt("Optio", "title", "Officer's assistant.", "Military rank")
    add_tt("Veteranus", "title", "Discharged soldier.", "Military rank")
    add_tt("Beneficiarius", "title", "Officer's aide.", "Military rank")

    add_tt("Civil title", "concept", "A civic or magisterial title.")
    add_tt("Aedilis", "title", "Aedile (public works magistrate).", "Civil title")
    add_tt("Duumvir", "title", "Duumvir (chief municipal magistrate).", "Civil title")
    add_tt("Decurio", "title", "Decurion (member of local senate).", "Civil title")
    add_tt("Quaestor", "title", "Quaestor (financial magistrate).", "Civil title")
    add_tt("Praetor", "title", "Praetor.", "Civil title")
    add_tt("Consul", "title", "Consul.", "Civil title")

    add_tt("Priesthood", "concept", "A religious office.")
    add_tt("Flamen", "title", "Flamen (priest of a specific deity).", "Priesthood")
    add_tt("Pontifex", "title", "Pontifex (member of the pontifical college).", "Priesthood")
    add_tt("Augur", "title", "Augur.", "Priesthood")
    add_tt("Vestal", "title", "Vestal virgin.", "Priesthood")

    # Attività / concetti
    add_tt("Ritual", "concept", "Formal or ceremonial acts of worship.")
    add_tt("Sacrifice", "concept", "Ritual offering to a deity.", "Ritual")
    add_tt("Vow", "concept", "Promise to a deity, later fulfilled.", "Ritual")
    add_tt("Taxation", "concept", "Assessment and collection of taxes.")
    add_tt("Agriculture", "concept", "Cultivation of land and livestock rearing.")
    add_tt("Commerce", "concept", "Trade and commercial activities.")
    add_tt("Craft production", "concept", "Manufacture of goods.")
    add_tt("Building activity", "concept", "Construction, restoration of public works.")
    add_tt("Legal action", "concept", "Judicial or administrative acts.")
    add_tt("Freedman status", "concept", "Manumission and freedman status.")
    add_tt("Slavery", "concept", "Enslavement.")
    add_tt("Marriage", "concept", "Marital relationship.")
    add_tt("Death", "concept", "Death and commemoration.")
    add_tt("Family", "concept", "Family relations.")
    add_tt("Collegium", "concept", "Professional or religious association.")

    _safe_tt_rel(tt["Votum solvit"], tt["Vow"], rel["ASSOCIATED_WITH"])
    _safe_tt_rel(tt["Sacrum"], tt["Ritual"], rel["ASSOCIATED_WITH"])
    _safe_tt_rel(tt["Ex voto"], tt["Vow"], rel["ASSOCIATED_WITH"])
    _safe_tt_rel(tt["Dis Manibus"], tt["Death"], rel["ASSOCIATED_WITH"])
    _safe_tt_rel(tt["Hic situs est"], tt["Death"], rel["ASSOCIATED_WITH"])

    # Luoghi (con geometrie)
    add_place("Roma", "Capital of the Roman Empire.", 12.4964, 41.9028, "precise")
    add_place("Ostia", "Port city of Rome, at the mouth of the Tiber.", 12.2917, 41.7550, "precise", "Roma")
    add_place("Pompeii", "City buried by Vesuvius in 79 CE.", 14.4922, 40.7492, "precise")
    add_place("Herculaneum", "City buried by Vesuvius in 79 CE.", 14.3486, 40.8058, "precise")
    add_place("Aquileia", "Roman colony in northeastern Italy.", 13.3703, 45.7714, "precise")
    add_place("Verona", "Roman city in northern Italy.", 10.9917, 45.4386, "precise")
    add_place("Massilia", "Marseille — Greek/Roman port in Gaul.", 5.3698, 43.2965, "precise")
    add_place("Lugdunum", "Lyon — capital of Roman Gaul.", 4.8357, 45.7640, "precise")
    add_place("Emerita Augusta", "Mérida — capital of Roman Lusitania.", -6.3437, 38.9165, "precise")
    add_place("Corduba", "Córdoba — capital of Baetica.", -4.7794, 37.8882, "precise")
    add_place("Tarraco", "Tarragona — capital of Hispania Citerior.", 1.2445, 41.1189, "precise")
    add_place("Verulamium", "St Albans — Roman town in Britain.", -0.3543, 51.7513, "precise")
    add_place("Londinium", "London — Roman city in Britain.", -0.1276, 51.5074, "precise")
    add_place("Thysdrus", "El Djem — Roman city in Africa Proconsularis.", 10.7167, 35.3000, "precise")
    add_place("Carthago", "Carthage — capital of Africa Proconsularis.", 10.3236, 36.8532, "precise")
    add_place("Ephesus", "Ephesus — major city of Asia province.", 27.3411, 37.9411, "precise")
    add_place("Hispania", "Iberian Peninsula.", -3.7038, 40.4168, "approximate")
    add_place("Gallia", "Roman Gaul.", 2.2137, 46.2276, "approximate")
    add_place("Britannia", "Roman Britain.", -1.5, 52.5, "approximate")
    add_place("Africa Proconsularis", "Roman province in North Africa.", 10.0, 35.0, "approximate")
    add_place("Asia", "Province of Asia (western Anatolia).", 28.0, 38.5, "approximate")

    # ══════════════════════════════════════════════════════════════════════
    # CONTESTI ARCHEOLOGICI (10)
    # ══════════════════════════════════════════════════════════════════════
    contexts_spec = [
        # (code, name, description, deposit_type, technique, lon, lat, precision, culture_labels, year_from, year_to)
        ("CTX-001", "Necropolis Via Appia (Roma)",
         "Southern sector of the Via Appia necropolis, km 3.2.",
         "burial", "stratigraphic", 12.5143, 41.8647, "approximate",
         ["Funerary","Roman"], 1, 250),
        ("CTX-002", "Sanctuary of Minerva (Roma)",
         "Sacred area on the Capitoline slope, votive deposit.",
         "structure", "stratigraphic", 12.4853, 41.8928, "approximate",
         ["Cultic area","Roman","Sanctuary"], 50, 250),
        ("CTX-003", "Forum area — west sector (Roma)",
         "Portico west of the Forum. Paved level.",
         "floor", "stratigraphic", 12.4855, 41.8925, "precise",
         ["Roman"], 80, 200),
        ("CTX-004", "Isola Sacra necropolis (Ostia)",
         "Necropolis between Ostia and Portus.",
         "burial", "stratigraphic", 12.2500, 41.7700, "precise",
         ["Funerary","Roman"], 50, 250),
        ("CTX-005", "Ostia — Piazzale delle Corporazioni",
         "Commercial forum with shop tabernae bearing mosaic emblems.",
         "structure", "stratigraphic", 12.2917, 41.7550, "precise",
         ["Roman"], 100, 220),
        ("CTX-006", "Pompeii — House of the Faun",
         "Domestic context, tablinum area.",
         "structure", "stratigraphic", 14.4863, 40.7500, "precise",
         ["Roman"], -100, 79),
        ("CTX-007", "Aquileia — forum east portico",
         "East portico of the forum, epigraphic pavement.",
         "floor", "stratigraphic", 13.3703, 45.7714, "precise",
         ["Roman"], 1, 200),
        ("CTX-008", "Massilia — necropolis of St-Victor",
         "Roman-period necropolis reused in late antiquity.",
         "burial", "stratigraphic", 5.3648, 43.2895, "approximate",
         ["Funerary","Roman"], 100, 300),
        ("CTX-009", "Emerita Augusta — theatre foundations",
         "Foundation deposit of the theatre, honorary inscriptions.",
         "structure", "stratigraphic", -6.3437, 38.9165, "precise",
         ["Roman"], -20, 100),
        ("CTX-010", "Thysdrus — amphitheatre annexes",
         "Annex rooms of the amphitheatre.",
         "structure", "stratigraphic", 10.7167, 35.2950, "precise",
         ["Roman"], 200, 280),
    ]

    ctx_ids = {}  # code → id
    for code, name, desc, dtype, tech, lon, lat, prec, cult_labels, y_from, y_to in contexts_spec:
        cid = ins("context", code=code, name=name, description=desc,
                  deposit_type=dtype, excavation_technique=tech,
                  geometry=gpkg.encode_point(lon, lat),
                  geometry_precision=prec, reliability_id=rl["high"],
                  source_reference=f"Demo — {code}",
                  created_by=user, updated_by=user)
        for lbl in cult_labels:
            if lbl in ctx_term:
                ins("context_term_assignment", context_id=cid, term_id=ctx_term[lbl],
                    certainty_id=cl["certain"], created_by=user)
        ins("context_chronology", context_id=cid,
            chronology_term_id=chron.get("Roman Imperial period"),
            absolute_from=y_from, absolute_to=y_to,
            certainty_id=cl["certain"], dating_method="archaeological_context")
        ctx_ids[code] = cid

    # ══════════════════════════════════════════════════════════════════════
    # PERSONAGGI (~50 nomi realistici latini per popolare le epigrafi)
    # ══════════════════════════════════════════════════════════════════════
    people_pool = [
        # praenomen, nomen, cognomen, sex, age_at_death, notes
        ("L", "Cornelius", "Primus", "M", 35, "Freedman."),
        ("L", "Valerius", "Proculus", "M", None, "Dedicant."),
        ("C", "Iulius", "Verecundus", "M", None, "Praefectus cohortis."),
        ("M", "Aemilius", "Rufus", "M", None, "Centurion."),
        ("T", "Flavius", "Sabinus", "M", None, "Altar dedicant."),
        (None, "Aurelia", "Prisca", "F", 28, "Deceased woman."),
        ("Q", "Fabius", "Maximus", "M", 62, "Decurio at Aquileia."),
        ("P", "Terentius", "Varro", "M", None, "Duumvir at Emerita."),
        ("Cn", "Pompeius", "Rufus", "M", 45, "Veteran of legio X."),
        ("A", "Manlius", "Torquatus", "M", None, "Consul designate."),
        (None, "Livia", "Drusilla", "F", 66, "Matrona from Rome."),
        (None, "Cornelia", "Gallia", "F", 22, "Deceased young."),
        (None, "Iulia", "Maior", "F", 40, "Wife of Q. Fabius."),
        ("Sex", "Pompeius", "Festus", "M", 51, "Merchant, Ostia."),
        ("M", "Antonius", "Rufinus", "M", None, "Beneficiarius."),
        ("Cn", "Cornelius", "Lentulus", "M", 74, "Ex-praetor."),
        (None, "Claudia", "Marcella", "F", 30, "Deceased matron."),
        (None, "Flavia", "Domitilla", "F", 12, "Deceased child."),
        ("D", "Iunius", "Silanus", "M", None, "Legatus in Britannia."),
        ("M", "Ulpius", "Traianus", "M", None, "Namesake dedicant."),
        ("C", "Plinius", "Secundus", "M", None, "Freedman scribe."),
        ("L", "Licinius", "Crassus", "M", 68, "Wealthy landowner."),
        (None, "Sulpicia", "Lepidina", "F", None, "Wife of tribune."),
        ("T", "Vibius", "Fronto", "M", 40, "Miles, legio II."),
        ("Q", "Marcius", "Rex", "M", None, "Praetor."),
        (None, "Antonia", "Caenis", "F", 55, "Freedwoman."),
        ("M", "Caelius", "Rufus", "M", 34, "Miles, legio VI."),
        (None, "Vibia", "Sabina", "F", 60, "Wife of a decurio."),
        ("P", "Ovidius", "Naso", "M", 60, "Poet, honored posthumously."),
        (None, "Caecilia", "Attica", "F", 18, "Deceased maiden."),
        ("L", "Sergius", "Catilina", "M", None, "Dedicant, votive altar."),
        ("A", "Postumius", "Albinus", "M", None, "Aedile."),
        ("Cn", "Domitius", "Corbulo", "M", None, "General honored."),
        ("Ti", "Claudius", "Nero", "M", None, "Freedman."),
        ("M", "Livius", "Salinator", "M", 55, "Veteranus."),
        (None, "Vipsania", "Agrippina", "F", 44, "Matrona."),
        ("Q", "Sertorius", "Macro", "M", None, "Optio."),
        ("L", "Munatius", "Plancus", "M", None, "Consul, honored."),
        ("C", "Cassius", "Longinus", "M", None, "Legatus."),
        ("M", "Porcius", "Cato", "M", 80, "Elder Cato imitator."),
        ("T", "Terentius", "Africanus", "M", 51, "Merchant."),
        (None, "Fulvia", "Plautilla", "F", 25, "Dead in childbirth."),
        (None, "Marcia", "Furnilla", "F", 33, "Freedwoman."),
        ("P", "Rutilius", "Rufus", "M", None, "Quaestor."),
        ("Sex", "Aelius", "Catus", "M", None, "Jurist."),
        ("Cn", "Papirius", "Carbo", "M", None, "Tribunus militum."),
        ("L", "Calpurnius", "Piso", "M", 62, "Decurio."),
        (None, "Aemilia", "Tertia", "F", 71, "Matrona."),
        ("M", "Furius", "Camillus", "M", None, "Honored ancestor."),
        (None, "Terentia", "Prima", "F", 45, "Freedwoman."),
        ("D", "Laberius", "Maximus", "M", None, "Beneficiarius."),
        ("M", "Ulpius", "Marcellus", "M", None, "Legatus, Britain."),
        ("C", "Iulius", "Agricola", "M", None, "Governor of Britain."),
        (None, "Servilia", "Nais", "F", 26, "Deceased maiden."),
    ]

    person_labels = []
    for pren, nom, cog, sex, age, notes in people_pool:
        parts = [x for x in (pren, nom, cog) if x]
        label = " ".join(parts) if pren else " ".join([nom, cog] if cog else [nom])
        # Formato display: "L. Cornelius Primus" per uomini, "Aurelia Prisca" per donne senza praenomen
        display = f"{pren}. {nom} {cog}" if pren else f"{nom} {cog}"
        add_tt(display, "person", notes or "Person attested in the corpus.")
        person_labels.append({"label": display, "praen": pren, "nomen": nom,
                              "cognomen": cog, "sex": sex, "age": age})

    # ══════════════════════════════════════════════════════════════════════
    # GENERATORE PROCEDURALE DI OGGETTI/TESTI
    # ══════════════════════════════════════════════════════════════════════
    def gen_praenomen_abbr(p):
        return p if p else ""

    def make_funerary_text(person, deity_prob=0.85):
        """Genera testo funerario (dipl / normalized / translation).
        Formule: DM, VIXIT, HSE, BM, filius/coniunx dedicat."""
        pren = person["praen"] or ""
        nom = person["nomen"]
        cog = person["cognomen"] or ""
        sex = person["sex"]
        age = person["age"]

        # DIPLOMATICA (con · e maiuscole)
        dm = "D · M" if r.random() < deity_prob else None
        # Riga nome
        if sex == "M":
            name_dipl = (f"{pren} · {nom.upper()} · {cog.upper()}" if pren
                          else f"{nom.upper()} · {cog.upper()}").strip(" ·")
            name_norm = f"{pren}({pren}. praenomen)" if False else (
                f"{pren}({pren}) {nom} {cog}" if pren else f"{nom} {cog}")
            name_trad = f"{pren}. {nom} {cog}".strip() if pren else f"{nom} {cog}".strip()
        else:
            # femminile: dativo -AE
            nom_f = nom
            cog_f = cog + "E" if cog and cog.endswith("A") else cog
            name_dipl = f"{nom_f.upper()}{'E' if nom_f.endswith('a') else ''} · {cog_f.upper()}"
            name_norm = f"{nom_f}{'e' if nom_f.endswith('a') else ''} {cog_f.lower().capitalize()}"
            name_trad = f"For {nom_f} {cog}"

        lines_dipl = []
        lines_norm = []
        lines_trad = []
        if dm:
            lines_dipl.append(dm)
            lines_norm.append("D(is) M(anibus)")
            lines_trad.append("To the spirits of the dead.")

        lines_dipl.append(name_dipl)
        lines_norm.append(name_norm)
        lines_trad.append(name_trad if sex == "M" else name_trad)

        if age:
            lines_dipl.append(f"VIXIT · ANNIS · {_roman(age)}")
            lines_norm.append(f"vixit annis {_roman(age)}")
            lines_trad.append(f"lived {age} years.")

        # HSE o BM
        if r.random() < 0.7:
            if sex == "M":
                lines_dipl.append("H · S · E")
                lines_norm.append("h(ic) s(itus) e(st)")
                lines_trad.append("Here he lies.")
            else:
                lines_dipl.append("H · S · E")
                lines_norm.append("h(ic) sit(a) e(st)")
                lines_trad.append("Here she lies.")
        elif r.random() < 0.5:
            lines_dipl.append("B · M · F")
            lines_norm.append("b(ene) m(erenti) f(ecit)")
            lines_trad.append("made for the well-deserving.")

        return ("\n".join(lines_dipl), "\n".join(lines_norm), "\n".join(lines_trad))

    def _roman(n):
        roman_map = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),
                     (90,"XC"),(50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
        s = ""
        for val, sym in roman_map:
            while n >= val:
                s += sym
                n -= val
        return s

    def make_votive_text(person, deity):
        """Formula votiva: DEITAS SACRVM / NAME / ARAM POSVIT / VSLM."""
        pren = person["praen"] or ""
        nom = person["nomen"]
        cog = person["cognomen"] or ""
        deity_dat = {
            "Iuppiter": "IOVI · OPTIMO · MAXIMO", "Iuno": "IVNONI · REGINAE",
            "Minerva": "MINERVAE · AVG · SAC", "Mars": "MARTI · SACRVM",
            "Venus": "VENERI · SAC", "Mercurius": "MERCVRIO · SAC",
            "Apollo": "APOLLINI · SAC", "Diana": "DIANAE · SAC",
            "Vulcanus": "VOLCANO · SAC", "Ceres": "CERERI · SAC",
            "Neptunus": "NEPTVNO · SAC", "Hercules": "HERCVLI · INVICTO",
            "Silvanus": "SILVANO · SAC", "Fortuna": "FORTVNAE · AVG",
            "Isis": "ISIDI · REG", "Mithras": "DEO · SOLI · INVICTO · MITHRAE",
            "Sol Invictus": "SOLI · INVICTO",
        }
        deity_dat_norm = {
            "Iuppiter": "Iovi Optimo Maximo", "Iuno": "Iunoni Reginae",
            "Minerva": "Minervae Aug(ustae) sac(rum)", "Mars": "Marti sacrum",
            "Venus": "Veneri sac(rum)", "Mercurius": "Mercurio sac(rum)",
            "Apollo": "Apollini sac(rum)", "Diana": "Dianae sac(rum)",
            "Vulcanus": "Volcano sac(rum)", "Ceres": "Cereri sac(rum)",
            "Neptunus": "Neptuno sac(rum)", "Hercules": "Herculi invicto",
            "Silvanus": "Silvano sac(rum)", "Fortuna": "Fortunae Aug(ustae)",
            "Isis": "Isidi Reg(inae)", "Mithras": "Deo Soli Invicto Mithrae",
            "Sol Invictus": "Soli Invicto",
        }
        deity_dat_trad = {
            "Iuppiter": "To Jupiter, Best and Greatest,",
            "Iuno": "To Juno the Queen,",
            "Minerva": "Sacred to Minerva Augusta,",
            "Mars": "Sacred to Mars,",
            "Venus": "Sacred to Venus,",
            "Mercurius": "Sacred to Mercury,",
            "Apollo": "Sacred to Apollo,",
            "Diana": "Sacred to Diana,",
            "Vulcanus": "Sacred to Vulcan,",
            "Ceres": "Sacred to Ceres,",
            "Neptunus": "Sacred to Neptune,",
            "Hercules": "To Hercules the Invincible,",
            "Silvanus": "Sacred to Silvanus,",
            "Fortuna": "To Fortuna Augusta,",
            "Isis": "To Isis the Queen,",
            "Mithras": "To the Invincible Sun-God Mithras,",
            "Sol Invictus": "To the Invincible Sun,",
        }
        name_dipl = f"{pren} · {nom.upper()} · {cog.upper()}".strip(" ·") if pren else f"{nom.upper()} · {cog.upper()}".strip(" ·")
        name_norm = f"{pren}({pren}) {nom} {cog}".strip() if pren else f"{nom} {cog}".strip()
        name_trad = f"{pren}. {nom} {cog}".strip() if pren else f"{nom} {cog}".strip()

        dipl = f"{deity_dat[deity]}\n{name_dipl}\nARAM · POSVIT\nV · S · L · M"
        norm = f"{deity_dat_norm[deity]}\n{name_norm}\naram posuit\nv(otum) s(olvit) l(ibens) m(erito)"
        trad = f"{deity_dat_trad[deity]}\n{name_trad}\nset up this altar,\nhaving fulfilled his vow willingly and deservedly."
        return (dipl, norm, trad)

    def make_honorary_text(person, addressee_deity=None):
        pren = person["praen"] or ""
        nom = person["nomen"]
        cog = person["cognomen"] or ""
        name_dipl = f"{pren} · {nom.upper()} · {cog.upper()}".strip(" ·") if pren else f"{nom.upper()} · {cog.upper()}".strip(" ·")
        name_norm = f"{pren}({pren}) {nom} {cog}".strip() if pren else f"{nom} {cog}".strip()
        name_trad = f"{pren}. {nom} {cog}".strip() if pren else f"{nom} {cog}".strip()
        dipl = f"{name_dipl}\nOB · MERITA · EIVS\nORDO · DECVRIONVM · POSVIT"
        norm = f"{name_norm}\nob merita eius\nordo decurionum posuit"
        trad = f"To {name_trad}\nfor his merits\nthe order of decurions set (this) up."
        return (dipl, norm, trad)

    # ══════════════════════════════════════════════════════════════════════
    # GENERAZIONE DEGLI OGGETTI (~100)
    # ══════════════════════════════════════════════════════════════════════
    # Distribuzione target:
    # - 40 stele funerarie integre (con testo)
    # - 25 altari votivi integri (con testo)
    # - 8 basi onorarie integre (con testo)
    # - 5 tabulae bronzee amministrative (con testo)
    # - 4 graffiti su ceramica (con testo)
    # - 3 oggetti ricostruiti (ognuno con 5-8 frammenti; totale ~20 frr, di cui ~12 iscritti)
    # - Poi frammenti isolati: ~130 frammenti sciolti (con o senza testo)
    # In modo che frammenti totali = 150 e oggetti totali (integri+ricostruiti+frammenti) = 100+
    #   Contiamo differently: se voglio ~100 oggetti visibili nelle liste (non contando i frr):
    #   integri (funerarie 40 + votivi 25 + onorari 8 + tabulae 5 + graffiti 4) = 82
    #   ricostruiti = 3
    #   totale "oggetti" 85, poi frammenti = 150 (di cui ~20 sotto i ricostruiti e ~130 sciolti).

    all_objects = []  # per tracking

    def _create_object_with_text(idx, kind, ctx_code, person_idx, dating_range, deity=None):
        """Crea un oggetto integro con testo. Ritorna (obj_id, doc_id)."""
        person = person_labels[person_idx % len(person_labels)]
        year_from, year_to = dating_range

        # Materiale e dimensioni per tipo
        if kind == "funerary":
            label = f"Funerary stele of {person['label']}"
            desc = "Rectangular funerary stele."
            obj_terms = ["Stele", "Stone"] + r.choice([["Marble"],["Limestone"],["Sandstone"]])
            dims = {"height": r.randint(60, 130), "width": r.randint(35, 60), "thickness": r.randint(8, 18)}
            surface = "front"
            dipl, norm, trad = make_funerary_text(person)
            title = f"Funerary inscription of {person['label']}"
            atype = "funerary"
        elif kind == "votive":
            label = f"Votive altar to {deity}, dedicated by {person['label']}"
            desc = "Small votive altar with molded top."
            obj_terms = ["Altar", "Stone"] + r.choice([["Marble"],["Limestone"],["Travertine"] if "Travertine" in ot else ["Stone"]])
            dims = {"height": r.randint(70, 110), "width": r.randint(40, 55), "depth": r.randint(35, 50)}
            surface = "front"
            dipl, norm, trad = make_votive_text(person, deity)
            title = f"Votive inscription to {deity}"
            atype = "votive"
        elif kind == "honorary":
            label = f"Honorary base for {person['label']}"
            desc = "Statue base with honorary inscription."
            obj_terms = ["Base", "Stone", "Marble"] if "Base" in ot else ["Stone","Marble"]
            dims = {"height": r.randint(90, 140), "width": r.randint(50, 80), "depth": r.randint(50, 70)}
            surface = "front"
            dipl, norm, trad = make_honorary_text(person)
            title = f"Honorary inscription for {person['label']}"
            atype = "honorary"
        elif kind == "tabula":
            label = f"Administrative tabula of {person['label']}"
            desc = "Bronze tabula with administrative text."
            obj_terms = ["Tablet", "Metal", "Bronze"] if "Tablet" in ot else ["Metal","Bronze"]
            dims = {"height": r.randint(25, 40), "width": r.randint(35, 55)}
            surface = "front"
            # Formula amministrativa breve
            pren = person["praen"] or ""
            nom, cog = person["nomen"], person["cognomen"] or ""
            name = f"{pren} · {nom.upper()} · {cog.upper()}".strip(" ·") if pren else f"{nom.upper()} · {cog.upper()}"
            dipl = (f"{name} · DECVRIO\n"
                    f"FRVMENTVM · IN · PVBLICVM · CONTVLIT\n"
                    f"EX · AGRIS · COLONIAE")
            name_n = f"{pren}({pren}) {nom} {cog}".strip() if pren else f"{nom} {cog}"
            norm = (f"{name_n}, decurio,\n"
                    "frumentum in publicum contulit\n"
                    "ex agris coloniae.")
            trad = (f"{name_n if not pren else pren + '. ' + nom + ' ' + cog}, decurion,\n"
                    "contributed grain to the public stores\n"
                    "from the fields of the colony.")
            title = f"Administrative tabula of {person['label']}"
            atype = "administrative"
        elif kind == "graffito":
            label = f"Ceramic vessel with graffito ({person['nomen']})"
            desc = "Small vessel with owner's mark scratched after firing."
            obj_terms = ["Ceramic"]
            dims = {"height": r.randint(10, 22), "width": r.randint(8, 20)}
            surface = "exterior"
            dipl = person["nomen"].upper()
            norm = person["nomen"].capitalize() + "(i)"
            trad = f"(Property) of {person['nomen']}."
            title = f"Graffito on ceramic vessel"
            atype = "graffito"
        else:
            return None

        completeness = r.choice([100,100,100,95,95,90,90,85,80])
        obj_id = ins("object",
                     inventory_number=f"INV-{2015+idx%10}-{idx:04d}",
                     label=label,
                     record_kind="physical_object",
                     description=desc,
                     completeness_percentage=completeness,
                     created_by=user, updated_by=user)
        ins("object_context", object_id=obj_id, context_id=ctx_ids[ctx_code],
            relation_role="findspot", certainty_id=cl["certain"])
        add_measurements(obj_id, dims)
        add_terms(obj_id, obj_terms)
        ins("object_chronology", object_id=obj_id,
            absolute_from=year_from, absolute_to=year_to,
            certainty_id=cl["probable"], dating_method="palaeography",
            created_by=user)

        doc_id = ins("text_document", object_id=obj_id,
                     siglum=f"CIL-DEMO-{idx:04d}",
                     title=title, surface=surface,
                     main_language="la", script="Latn",
                     description=f"{kind.capitalize()} inscription.")
        vs = make_versions(doc_id, [
            ("diplomatic_transcription", "la", "Latn", dipl, "Diplomatica."),
            ("normalized", "la", "Latn", norm, "Scioglimento."),
            ("translation", "en", "Latn", trad, "English translation."),
        ], user)
        vid_dipl = vs[0]["id"]

        # ANNOTAZIONI a seconda del tipo
        if kind == "funerary":
            if "D · M" in dipl:
                annotate(vid_dipl, dipl, "D · M", "formula", ["Dis Manibus","Funerary formula","Death"])
            # Nome persona
            name_parts = [p for p in (person["praen"], person["nomen"], person["cognomen"]) if p]
            substring = " · ".join(x.upper() if x != person["praen"] else x for x in name_parts)
            annotate(vid_dipl, dipl, substring, "named_entity", [person["label"]])
            if "H · S · E" in dipl:
                annotate(vid_dipl, dipl, "H · S · E", "formula", ["Hic situs est","Funerary formula"])
            if "B · M · F" in dipl:
                annotate(vid_dipl, dipl, "B · M · F", "formula", ["Bene merenti","Funerary formula"])
            if "VIXIT" in dipl:
                # Trova l'intera riga VIXIT · ANNIS · X
                for line in dipl.split("\n"):
                    if line.startswith("VIXIT"):
                        annotate(vid_dipl, dipl, line, "formula", ["Vixit annis","Funerary formula"])
                        break
        elif kind == "votive":
            deity_line = dipl.split("\n")[0]
            annotate(vid_dipl, dipl, deity_line, "named_entity", [deity, "Deity", "Sacrum", "Dedicatory formula"])
            name_parts = [p for p in (person["praen"], person["nomen"], person["cognomen"]) if p]
            substring = " · ".join(x.upper() if x != person["praen"] else x for x in name_parts)
            annotate(vid_dipl, dipl, substring, "named_entity", [person["label"]])
            annotate(vid_dipl, dipl, "V · S · L · M", "formula",
                     ["Votum solvit","Dedicatory formula","Vow","Ritual"])
            annotate(vid_dipl, dipl, "ARAM · POSVIT", "named_entity",
                     ["Ritual"])
        elif kind == "honorary":
            name_parts = [p for p in (person["praen"], person["nomen"], person["cognomen"]) if p]
            substring = " · ".join(x.upper() if x != person["praen"] else x for x in name_parts)
            annotate(vid_dipl, dipl, substring, "named_entity", [person["label"]])
            annotate(vid_dipl, dipl, "OB · MERITA · EIVS", "formula", ["Ob merita","Honorary formula"])
            annotate(vid_dipl, dipl, "ORDO · DECVRIONVM · POSVIT", "named_entity", ["Decurio","Civil title"])
        elif kind == "tabula":
            annotate(vid_dipl, dipl, "FRVMENTVM · IN · PVBLICVM · CONTVLIT", "named_entity",
                     ["Taxation","Agriculture","Commerce"])
            annotate(vid_dipl, dipl, "DECVRIO", "named_entity", ["Decurio","Civil title"])
        elif kind == "graffito":
            annotate(vid_dipl, dipl, person["nomen"].upper(), "named_entity",
                     [person["label"]], "probable")

        all_objects.append({"id": obj_id, "kind": kind, "ctx": ctx_code})
        return obj_id, doc_id

    # ══════════════════════════════════════════════════════════════════════
    # POPOLAMENTO EFFETTIVO
    # ══════════════════════════════════════════════════════════════════════
    # Mappa contesti → range cronologici plausibili (I sec a.C. — III sec d.C.)
    ctx_dating = {
        "CTX-001": [(-30, 30), (10, 80), (60, 120), (100, 180), (150, 230)],  # necropoli lunga durata
        "CTX-002": [(50, 130), (100, 180), (150, 230)],
        "CTX-003": [(80, 160), (120, 200)],
        "CTX-004": [(60, 130), (100, 180), (150, 220), (200, 270)],
        "CTX-005": [(100, 170), (150, 220)],
        "CTX-006": [(-50, 30), (0, 79)],  # Pompei termina 79
        "CTX-007": [(10, 90), (80, 160), (150, 220)],
        "CTX-008": [(100, 180), (180, 260), (240, 310)],
        "CTX-009": [(-20, 60), (30, 110)],
        "CTX-010": [(200, 280), (240, 320)],
    }

    ctx_codes = list(ctx_dating.keys())
    person_idx = 0
    obj_idx = 100  # partiamo da INV-...-0100

    # 40 funerarie integrate
    for i in range(40):
        ctx = r.choice(ctx_codes)
        dating = r.choice(ctx_dating[ctx])
        _create_object_with_text(obj_idx, "funerary", ctx, person_idx, dating)
        obj_idx += 1; person_idx += 1

    # 25 altari votivi
    votive_deities = ["Iuppiter","Iuno","Minerva","Mars","Venus","Mercurius","Apollo","Diana",
                       "Hercules","Fortuna","Silvanus","Ceres","Isis","Mithras","Sol Invictus"]
    for i in range(25):
        ctx = r.choice([c for c in ctx_codes if c not in ("CTX-001","CTX-004","CTX-008")])  # non nelle necropoli
        dating = r.choice(ctx_dating[ctx])
        deity = r.choice(votive_deities)
        # Sol Invictus e Mithras solo tardi
        if deity in ("Sol Invictus","Mithras") and dating[1] < 150:
            deity = r.choice(["Iuppiter","Minerva","Mars"])
        _create_object_with_text(obj_idx, "votive", ctx, person_idx, dating, deity=deity)
        obj_idx += 1; person_idx += 1

    # 8 basi onorarie
    for i in range(8):
        ctx = r.choice(["CTX-003","CTX-005","CTX-007","CTX-009","CTX-010"])
        dating = r.choice(ctx_dating[ctx])
        _create_object_with_text(obj_idx, "honorary", ctx, person_idx, dating)
        obj_idx += 1; person_idx += 1

    # 5 tabulae bronzee
    for i in range(5):
        ctx = r.choice(["CTX-003","CTX-005","CTX-007","CTX-009"])
        dating = r.choice(ctx_dating[ctx])
        _create_object_with_text(obj_idx, "tabula", ctx, person_idx, dating)
        obj_idx += 1; person_idx += 1

    # 4 graffiti
    for i in range(4):
        ctx = r.choice(["CTX-004","CTX-005","CTX-006"])
        dating = r.choice(ctx_dating[ctx])
        _create_object_with_text(obj_idx, "graffito", ctx, person_idx, dating)
        obj_idx += 1; person_idx += 1

    # ══════════════════════════════════════════════════════════════════════
    # OGGETTI RICOSTRUITI (3, ognuno con 5-8 frammenti, alcuni iscritti)
    # ══════════════════════════════════════════════════════════════════════
    # Stele votiva ricostruita (5 frr, 3 iscritti)
    def make_reconstructed(idx, ctx, dating, kind_label, n_frags, n_inscribed, deity=None, person=None):
        parent_id = ins("object",
            inventory_number=f"INV-2020-{idx:04d}",
            label=f"{kind_label} (reconstructed)",
            record_kind="reconstructed_object",
            description=f"Reconstructed from {n_frags} fragments.",
            completeness_percentage=r.randint(60, 85),
            restored=1, restoration_date="2021",
            restoration_note=f"Recomposed from {n_frags} fragments.",
            created_by=user, updated_by=user)
        ins("object_context", object_id=parent_id, context_id=ctx_ids[ctx],
            relation_role="findspot", certainty_id=cl["probable"])
        ins("object_chronology", object_id=parent_id,
            absolute_from=dating[0], absolute_to=dating[1],
            certainty_id=cl["probable"], dating_method="palaeography",
            created_by=user)

        # Genera testo totale come se fosse un'iscrizione unica
        if deity and person:
            full_dipl, full_norm, full_trad = make_votive_text(person, deity)
        elif person:
            full_dipl, full_norm, full_trad = make_funerary_text(person)
        else:
            full_dipl = "FRAGMENT · TEXT"; full_norm = "fragment text"; full_trad = "fragmentary."

        dipl_lines = full_dipl.split("\n")
        norm_lines = full_norm.split("\n")
        trad_lines = full_trad.split("\n")
        n_lines = len(dipl_lines)
        # Distribuiamo le n_lines righe tra n_inscribed frammenti
        # E i frammenti non iscritti sono anepigrafe
        inscribed_indices = sorted(r.sample(range(n_frags), n_inscribed))
        # Divisione righe: se n_inscribed=3 e n_lines=4, primi 1 riga, poi 2, poi 1 (o simili)
        lines_per_frag = [n_lines // n_inscribed] * n_inscribed
        for i in range(n_lines % n_inscribed):
            lines_per_frag[i] += 1
        # Assegna consecutive righe a ciascun frammento iscritto
        frag_texts = []
        cursor = 0
        for lpf in lines_per_frag:
            frag_texts.append({
                "dipl": "\n".join(dipl_lines[cursor:cursor+lpf]),
                "norm": "\n".join(norm_lines[cursor:cursor+lpf]),
                "trad": "\n".join(trad_lines[cursor:cursor+lpf]),
            })
            cursor += lpf

        inscribed_seq = 0
        frag_ids = []
        for j in range(n_frags):
            letter = chr(ord('a') + j)
            frag_id = ins("object",
                inventory_number=f"INV-2020-{idx:04d}{letter}",
                label=f"Fr. {letter.upper()}",
                record_kind="fragment",
                description=f"Fragment {letter.upper()} of reconstructed object {idx}.",
                completeness_percentage=r.randint(40, 90),
                created_by=user, updated_by=user)
            ins("object_relation",
                source_object_id=frag_id, target_object_id=parent_id,
                relation_type_id=rel["FRAGMENT_OF"], certainty_id=cl["certain"],
                status="accepted", asserted_by=user, sequence=j+1)
            frag_ids.append(frag_id)

            if j in inscribed_indices:
                ft = frag_texts[inscribed_seq]
                inscribed_seq += 1
                doc_id = ins("text_document", object_id=frag_id,
                             siglum=f"CIL-DEMO-{idx:04d}{letter}",
                             title=f"Inscription on fr. {letter.upper()}",
                             surface="front", main_language="la", script="Latn",
                             description=f"Portion of the {kind_label.lower()}.")
                vs = make_versions(doc_id, [
                    ("diplomatic_transcription", "la", "Latn", ft["dipl"], f"Fr. {letter.upper()}."),
                    ("normalized", "la", "Latn", ft["norm"], f"Fr. {letter.upper()}."),
                    ("translation", "en", "Latn", ft["trad"], f"Fr. {letter.upper()}."),
                ], user)
                # Annotazioni base
                if "D · M" in ft["dipl"]:
                    annotate(vs[0]["id"], ft["dipl"], "D · M", "formula",
                             ["Dis Manibus","Funerary formula","Death"])
                if "V · S · L · M" in ft["dipl"]:
                    annotate(vs[0]["id"], ft["dipl"], "V · S · L · M", "formula",
                             ["Votum solvit","Dedicatory formula","Vow"])
                if deity and deity in ft["norm"]:
                    # trova la riga della divinità
                    for line in ft["dipl"].split("\n"):
                        if any(k in line for k in ["IOVI","MINERVAE","MARTI","IVNONI","VENERI",
                                                    "MERCVRIO","APOLLINI","DIANAE","VOLCANO",
                                                    "CERERI","NEPTVNO","HERCVLI","SILVANO",
                                                    "FORTVNAE","ISIDI","SOLI"]):
                            annotate(vs[0]["id"], ft["dipl"], line, "named_entity",
                                     [deity,"Deity","Sacrum"])
                            break
        return parent_id, frag_ids

    # 3 oggetti ricostruiti
    recon1_person = person_labels[person_idx % len(person_labels)]; person_idx += 1
    make_reconstructed(500, "CTX-002", (100, 160),
                       "Votive stele to Minerva", n_frags=5, n_inscribed=3,
                       deity="Minerva", person=recon1_person)

    recon2_person = person_labels[person_idx % len(person_labels)]; person_idx += 1
    make_reconstructed(501, "CTX-001", (50, 120),
                       "Funerary stele", n_frags=6, n_inscribed=3,
                       person=recon2_person)

    recon3_person = person_labels[person_idx % len(person_labels)]; person_idx += 1
    make_reconstructed(502, "CTX-007", (150, 220),
                       "Votive altar to Iuppiter", n_frags=4, n_inscribed=2,
                       deity="Iuppiter", person=recon3_person)

    # Totale frammenti sotto oggetti ricostruiti = 5+6+4 = 15

    # ══════════════════════════════════════════════════════════════════════
    # FRAMMENTI SCIOLTI (~135 per arrivare a ~150 totali)
    # Molti anepigrafi, alcuni con brevi testi (formule spezzate)
    # ══════════════════════════════════════════════════════════════════════
    partial_formulas = [
        # (dipl, norm, trad, term_labels_to_annotate)
        ("D · M\n[---]", "D(is) M(anibus)\n[---]", "To the spirits of the dead\n[---]",
         [("D · M", "formula", ["Dis Manibus","Funerary formula"])]),
        ("[---] · VIXIT · ANNIS · [---]", "[---] vixit annis [---]", "[---] lived years [---]",
         [("VIXIT · ANNIS", "formula", ["Vixit annis","Funerary formula"])]),
        ("V · S · L · M", "v(otum) s(olvit) l(ibens) m(erito)",
         "having fulfilled his vow willingly and deservedly",
         [("V · S · L · M", "formula", ["Votum solvit","Dedicatory formula"])]),
        ("[---] · IOVI · O · M · [---]", "[---] Iovi O(ptimo) M(aximo) [---]",
         "[---] to Jupiter Best and Greatest [---]",
         [("IOVI · O · M", "named_entity", ["Iuppiter","Deity"])]),
        ("H · S · E", "h(ic) s(itus) e(st)", "here he lies",
         [("H · S · E", "formula", ["Hic situs est","Funerary formula"])]),
        ("[---] · SACRVM", "[---] sacrum", "[---] sacred",
         [("SACRVM", "formula", ["Sacrum","Dedicatory formula"])]),
        ("[---] · CENT · LEG · [---]", "[---] cent(urio) leg(ionis) [---]",
         "[---] centurion of the legion [---]",
         [("CENT · LEG", "named_entity", ["Centurio","Military rank"])]),
    ]

    n_loose_fragments = 135
    for i in range(n_loose_fragments):
        ctx = r.choice(ctx_codes)
        dating = r.choice(ctx_dating[ctx])
        frag_id = ins("object",
            inventory_number=f"INV-FR-{i:04d}",
            label=f"Loose fragment #{i+1}",
            record_kind="fragment",
            description=r.choice([
                "Small marble fragment with partial inscription.",
                "Limestone fragment, abraded surface.",
                "Fragment of a funerary stele, upper corner.",
                "Right-side fragment, partial text preserved.",
                "Bronze fragment, letters partly legible.",
                "Fragment reused in later masonry.",
                "Anepigraphic fragment, decorative moulding.",
                "Fragment with traces of red paint in the letters.",
                "Lower part of a stele, few letters preserved.",
            ]),
            completeness_percentage=r.randint(10, 55),
            created_by=user, updated_by=user)
        ins("object_context", object_id=frag_id, context_id=ctx_ids[ctx],
            relation_role="findspot", certainty_id=cl["probable"])
        # ~30% dei frammenti sciolti sono anepigrafi
        # ~60% con testo parziale
        if r.random() < 0.60:
            # con testo
            dipl, norm, trad, ann_specs = r.choice(partial_formulas)
            doc_id = ins("text_document", object_id=frag_id,
                         siglum=f"CIL-FR-{i:04d}",
                         title=f"Fragment {i+1} — partial text",
                         surface="front", main_language="la", script="Latn",
                         description="Fragmentary text.")
            vs = make_versions(doc_id, [
                ("diplomatic_transcription", "la", "Latn", dipl, "Partial."),
                ("normalized", "la", "Latn", norm, "Partial."),
                ("translation", "en", "Latn", trad, "Partial."),
            ], user)
            for substring, atype, term_labels in ann_specs:
                annotate(vs[0]["id"], dipl, substring, atype, term_labels)
            ins("object_chronology", object_id=frag_id,
                absolute_from=dating[0], absolute_to=dating[1],
                certainty_id=cl["possible"], dating_method="palaeography",
                created_by=user)
        else:
            # anepigrafo
            ins("object_chronology", object_id=frag_id,
                absolute_from=dating[0], absolute_to=dating[1],
                certainty_id=cl["possible"], dating_method="typology",
                created_by=user)

    # ══════════════════════════════════════════════════════════════════════
    # WORKS — opere intellettuali astratte che raggruppano più testimoni
    # ══════════════════════════════════════════════════════════════════════
    # Scenario: nel corpus latino ci sono opere/testi ricorrenti di cui più
    # iscrizioni sono testimoni.
    #   1. Formula dedicatoria a Iuppiter O.M. — tutte le dediche a Iuppiter
    #      condividono la stessa opera "formulare" (breve e standardizzata)
    #   2. Formula funeraria standard DM+HSE — l'opera è la formula liturgica
    #      canonica, ogni funeraria ne è un testimone
    #   3. Dedica a Minerva Augusta — formula votiva ricorrente
    #   4. Editto imperiale sull'annona (fittizio) — attestato in ~3 tabulae
    #   5. Formula votiva a Mars con VSLM — molto standardizzata

    def create_work(title, work_type, canonical_dating,
                    comp_from, comp_to, description, author=None,
                    bibliography=None):
        return ins("work",
                   title=title, author=author, work_type=work_type,
                   canonical_dating=canonical_dating,
                   composition_from=comp_from, composition_to=comp_to,
                   language="la",
                   description=description,
                   bibliography=bibliography)

    def link_docs_to_work(work_id, doc_ids_and_siglums):
        """doc_ids_and_siglums = [(doc_id, 'A'), (doc_id, 'B'), ...]"""
        for did, sig in doc_ids_and_siglums:
            conn.execute(
                "UPDATE text_document SET work_id=?, witness_siglum=?, updated_at=? WHERE id=?",
                (work_id, sig, now_iso(), did))

    # WORK 1: Formula dedicatoria a Iuppiter O.M.
    work_iom = create_work(
        title="Formula dedicatoria a Iuppiter Optimo Maximo",
        work_type="formula",
        canonical_dating="I–III sec. d.C.",
        comp_from=-30, comp_to=300,
        description=("Formula votiva standard latina indirizzata a Iuppiter "
                     "Optimus Maximus, in genere seguita da nome del dedicante, "
                     "'aram posuit' e VSLM. Attestata in numerose dediche "
                     "coloniali e provinciali."),
        bibliography="Cf. CIL passim; ILS 3003 ss.")

    # Trovo tutti i document su altari votivi a Iuppiter (parola IOVI nel testo)
    iovi_docs = conn.execute("""
        SELECT DISTINCT td.id
          FROM text_document td
          JOIN text_version tv ON tv.text_document_id = td.id
         WHERE tv.content LIKE '%IOVI%'
           AND tv.version_type = 'diplomatic_transcription'
           AND td.work_id IS NULL
         ORDER BY td.id
    """).fetchall()
    letters_a = [chr(ord('A') + i) for i in range(26)]
    link_docs_to_work(work_iom,
                     [(d[0], letters_a[i]) for i, d in enumerate(iovi_docs)])

    # WORK 2: Formula funeraria standard DM+HSE
    work_dm = create_work(
        title="Formula funeraria standard: D(is) M(anibus) + H(ic) S(itus) E(st)",
        work_type="formula",
        canonical_dating="I–III sec. d.C.",
        comp_from=-1, comp_to=300,
        description=("Opera formulare funeraria composta dall'invocazione ai Mani "
                     "seguita dal nome del defunto, età (vixit annis) e formula "
                     "conclusiva HSE. Estremamente ricorrente in tutto l'Impero, "
                     "con lievi varianti locali."),
        bibliography="Cf. CIL VI passim; Cagnat, Cours d'épigraphie 1914")

    dm_docs = conn.execute("""
        SELECT DISTINCT td.id
          FROM text_document td
          JOIN text_version tv ON tv.text_document_id = td.id
         WHERE tv.content LIKE '%D · M%'
           AND tv.content LIKE '%H · S · E%'
           AND tv.version_type = 'diplomatic_transcription'
           AND td.work_id IS NULL
         ORDER BY td.id
         LIMIT 15
    """).fetchall()
    link_docs_to_work(work_dm,
                     [(d[0], letters_a[i]) for i, d in enumerate(dm_docs)])

    # WORK 3: Formula votiva a Minerva Augusta
    work_minerva = create_work(
        title="Dedica votiva a Minerva Augusta",
        work_type="formula",
        canonical_dating="II sec. d.C. (con precedenti dal I sec.)",
        comp_from=50, comp_to=250,
        description=("Formula dedicatoria a Minerva nella variante Augusta, "
                     "diffusa nei santuari urbani e coloniali. La stele "
                     "ricostruita CIL-DEMO-0500 è uno dei testimoni completi "
                     "ricomposti."),
        bibliography="Cf. Pailler, Bacchanalia 1988; ILS 3129 ss.")

    minerva_docs = conn.execute("""
        SELECT DISTINCT td.id
          FROM text_document td
          JOIN text_version tv ON tv.text_document_id = td.id
         WHERE tv.content LIKE '%MINERVAE%'
           AND tv.version_type = 'diplomatic_transcription'
           AND td.work_id IS NULL
         ORDER BY td.id
         LIMIT 10
    """).fetchall()
    link_docs_to_work(work_minerva,
                     [(d[0], letters_a[i]) for i, d in enumerate(minerva_docs)])

    # WORK 4: Editto fittizio sull'annona (attestato nelle tabulae)
    work_annona = create_work(
        title="Editto imperiale sulla contribuzione frumentaria (attestazioni locali)",
        work_type="edict",
        canonical_dating="II sec. d.C. (110–160)",
        comp_from=110, comp_to=160,
        description=("Testimoniato in una serie di tabulae bronzee locali che "
                     "riportano formule amministrative simili sull'assegnazione "
                     "di frumento pubblico. Le tabulae attestano l'applicazione "
                     "provinciale dell'editto originale (perduto)."),
        bibliography="Cf. Rickman, The Corn Supply of Ancient Rome 1980")

    tabulae_docs = conn.execute("""
        SELECT DISTINCT td.id
          FROM text_document td
          JOIN text_version tv ON tv.text_document_id = td.id
         WHERE tv.content LIKE '%FRVMENTVM%'
           AND tv.version_type = 'diplomatic_transcription'
           AND td.work_id IS NULL
         ORDER BY td.id
    """).fetchall()
    link_docs_to_work(work_annona,
                     [(d[0], letters_a[i]) for i, d in enumerate(tabulae_docs)])

    # WORK 5: Formula votiva a Marte con VSLM (comune tra i militari)
    work_marti = create_work(
        title="Formula votiva a Marte con VSLM",
        work_type="formula",
        canonical_dating="I–III sec. d.C.",
        comp_from=1, comp_to=280,
        description=("Formula dedicatoria standard a Marte con conclusione "
                     "V(otum) S(olvit) L(ibens) M(erito). Diffusa nei santuari "
                     "militari e nelle stationes provinciali."),
        bibliography="Cf. ILS 3149 ss.; Speidel, Roman Army Studies 1984")

    marti_docs = conn.execute("""
        SELECT DISTINCT td.id
          FROM text_document td
          JOIN text_version tv ON tv.text_document_id = td.id
         WHERE tv.content LIKE '%MARTI%'
           AND tv.version_type = 'diplomatic_transcription'
           AND td.work_id IS NULL
         ORDER BY td.id
         LIMIT 8
    """).fetchall()
    link_docs_to_work(work_marti,
                     [(d[0], letters_a[i]) for i, d in enumerate(marti_docs)])

    conn.commit()
