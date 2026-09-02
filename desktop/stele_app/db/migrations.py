"""
Migrazioni non-distruttive per progetti esistenti.
Eseguite al boot di open_project() se il progetto è più vecchio dello schema.
Aggiungono colonne/tabelle mancanti; non alterano i dati.
"""
from .project import now_iso


def _has_table(conn, name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def _has_column(conn, table, col):
    return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})"))


def _add_column_if_missing(conn, table, coldef):
    """coldef è tipo 'nome TIPO [DEFAULT ...] [CHECK(...)]'."""
    colname = coldef.split()[0]
    if _has_column(conn, table, colname):
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")
    return True


def apply_migrations(conn):
    """Applica in sequenza tutte le migrazioni idempotenti. Ritorna una lista
    delle modifiche effettuate (utile per log/diagnostica)."""
    changed = []

    # --- text_unit_alignment (versioni parallele allineate) -----------------
    if not _has_table(conn, "text_unit_alignment"):
        conn.execute("""
          CREATE TABLE text_unit_alignment (
            id INTEGER PRIMARY KEY,
            group_id INTEGER NOT NULL,
            text_unit_id INTEGER NOT NULL REFERENCES text_unit(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'parallel' CHECK (role IN ('primary','parallel','note')),
            created_at TEXT NOT NULL,
            UNIQUE (group_id, text_unit_id)
          ) STRICT;""")
        conn.execute("CREATE INDEX idx_alignment_group ON text_unit_alignment(group_id)")
        conn.execute("CREATE INDEX idx_alignment_unit ON text_unit_alignment(text_unit_id)")
        changed.append("+text_unit_alignment")

    # --- iterazione 2: nuove colonne archeologiche su context / object ------
    # SQLite ALTER TABLE ADD COLUMN non supporta i CHECK expression complessi
    # in tutti i casi, ma un CHECK "semplice" (IN list) è supportato.
    for coldef in [
        "deposit_type TEXT CHECK (deposit_type IN "
        "('fill','floor','burial','cut','structure','midden','abandonment','surface','other') "
        "OR deposit_type IS NULL)",
        "excavation_technique TEXT CHECK (excavation_technique IN "
        "('stratigraphic','arbitrary','mixed','surface','test_pit','other') "
        "OR excavation_technique IS NULL)",
        "excavation_method_note TEXT",
        "preservation_note TEXT",
    ]:
        if _add_column_if_missing(conn, "context", coldef):
            changed.append(f"context.+{coldef.split()[0]}")

    for coldef in [
        "decoration_present INTEGER CHECK (decoration_present IN (0,1) OR decoration_present IS NULL)",
        "decoration_note TEXT",
        "restored INTEGER CHECK (restored IN (0,1) OR restored IS NULL)",
        "restoration_date TEXT",
        "restoration_note TEXT",
    ]:
        if _add_column_if_missing(conn, "object", coldef):
            changed.append(f"object.+{coldef.split()[0]}")

    # --- sequence su object_relation (per ordinamento frammenti) -------------
    if _add_column_if_missing(conn, "object_relation", "sequence INTEGER"):
        changed.append("object_relation.+sequence")

    # --- relation_type FRAGMENT_OF (se mancante) ----------------------------
    if not conn.execute(
        "SELECT 1 FROM relation_type WHERE code='FRAGMENT_OF'"
    ).fetchone():
        conn.execute("""
            INSERT INTO relation_type (code,label,inverse_label,domain,is_symmetric,is_hierarchical)
            VALUES ('FRAGMENT_OF','fragment of','composed of','object',0,1)
        """)
        changed.append("+relation_type.FRAGMENT_OF")

    # --- work (opera intellettuale astratta) + text_document.work_id --------
    if not _has_table(conn, "work"):
        conn.execute("""
          CREATE TABLE work (
            id                 INTEGER PRIMARY KEY,
            uid                TEXT NOT NULL UNIQUE,
            title              TEXT NOT NULL,
            author             TEXT,
            work_type          TEXT,
            canonical_dating   TEXT,
            composition_from   INTEGER,
            composition_to     INTEGER,
            language           TEXT,
            description        TEXT,
            bibliography       TEXT,
            notes              TEXT,
            is_active          INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
            created_at         TEXT NOT NULL,
            updated_at         TEXT NOT NULL
          ) STRICT;""")
        conn.execute("CREATE INDEX idx_work_title ON work(title)")
        conn.execute("CREATE INDEX idx_work_type  ON work(work_type)")
        changed.append("+work")

    if _add_column_if_missing(conn, "text_document",
                              "work_id INTEGER REFERENCES work(id) ON DELETE SET NULL"):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_text_document_work "
                     "ON text_document(work_id)")
        changed.append("text_document.+work_id")

    if _add_column_if_missing(conn, "text_document", "witness_siglum TEXT"):
        changed.append("text_document.+witness_siglum")

    conn.commit()
    return changed
