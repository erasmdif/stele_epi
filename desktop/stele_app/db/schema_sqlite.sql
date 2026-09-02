-- ============================================================================
-- Stele DBMS — schema SQLite / GeoPackage
-- Modello: annotazione stand-off, vocabolari gerarchici N:M, GIS leggero.
-- Le tabelle applicative sono STRICT; le due feature table spaziali
-- (context, text_term_place) restano non-STRICT per compatibilità GeoPackage.
-- Le junction bibliografia/media ripetitive sono generate a runtime (project.py).
-- ============================================================================

-- ---------- SYSTEM / SHARED -------------------------------------------------
CREATE TABLE app_user (
  id           INTEGER PRIMARY KEY,
  uid          TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  orcid        TEXT,
  email        TEXT,
  affiliation  TEXT,
  is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1))
) STRICT;

CREATE TABLE certainty_level (
  id          INTEGER PRIMARY KEY,
  code        TEXT NOT NULL UNIQUE,
  label       TEXT NOT NULL,
  rank        INTEGER NOT NULL,
  description TEXT,
  is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1))
) STRICT;

CREATE TABLE reliability_level (
  id          INTEGER PRIMARY KEY,
  code        TEXT NOT NULL UNIQUE,
  label       TEXT NOT NULL,
  rank        INTEGER NOT NULL,
  description TEXT,
  is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1))
) STRICT;

CREATE TABLE relation_type (
  id              INTEGER PRIMARY KEY,
  code            TEXT NOT NULL UNIQUE,
  label           TEXT NOT NULL,
  inverse_label   TEXT,
  domain          TEXT NOT NULL,
  is_symmetric    INTEGER NOT NULL DEFAULT 0 CHECK (is_symmetric IN (0,1)),
  is_hierarchical INTEGER NOT NULL DEFAULT 0 CHECK (is_hierarchical IN (0,1)),
  description     TEXT,
  is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1))
) STRICT;

CREATE TABLE change_log (
  id           INTEGER PRIMARY KEY,
  entity_table TEXT NOT NULL,
  entity_id    INTEGER NOT NULL,
  action       TEXT NOT NULL,
  changed_by   INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
  changed_at   TEXT NOT NULL,
  before_json  TEXT,
  after_json   TEXT,
  note         TEXT
) STRICT;

-- ---------- CONTEXT (feature table, non-STRICT) -----------------------------
CREATE TABLE context (
  id                 INTEGER PRIMARY KEY,
  uid                TEXT NOT NULL UNIQUE,
  code               TEXT UNIQUE,
  name               TEXT,
  description        TEXT,
  geometry           BLOB,
  geometry_precision TEXT,
  geometry_note      TEXT,
  reliability_id     INTEGER REFERENCES reliability_level(id) ON DELETE SET NULL,
  source_reference   TEXT,
  -- iterazione 2: profondità archeologica
  deposit_type       TEXT CHECK (deposit_type IN
                       ('fill','floor','burial','cut','structure',
                        'midden','abandonment','surface','other') OR deposit_type IS NULL),
  excavation_technique TEXT CHECK (excavation_technique IN
                       ('stratigraphic','arbitrary','mixed','surface','test_pit','other')
                       OR excavation_technique IS NULL),
  excavation_method_note TEXT,
  preservation_note  TEXT,
  notes              TEXT,
  is_active          INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL,
  created_by         INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
  updated_by         INTEGER REFERENCES app_user(id) ON DELETE SET NULL
);

CREATE TABLE context_term (
  id              INTEGER PRIMARY KEY,
  uid             TEXT NOT NULL UNIQUE,
  term_type       TEXT NOT NULL,
  preferred_label TEXT NOT NULL,
  description     TEXT,
  notes           TEXT,
  is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1))
) STRICT;

CREATE TABLE context_term_label (
  id              INTEGER PRIMARY KEY,
  context_term_id INTEGER NOT NULL REFERENCES context_term(id) ON DELETE CASCADE,
  language        TEXT NOT NULL,
  label           TEXT NOT NULL,
  label_type      TEXT NOT NULL,
  is_preferred    INTEGER NOT NULL DEFAULT 0 CHECK (is_preferred IN (0,1))
) STRICT;

CREATE TABLE context_term_relation (
  id               INTEGER PRIMARY KEY,
  source_term_id   INTEGER NOT NULL REFERENCES context_term(id) ON DELETE CASCADE,
  target_term_id   INTEGER NOT NULL REFERENCES context_term(id) ON DELETE CASCADE,
  relation_type_id INTEGER NOT NULL REFERENCES relation_type(id) ON DELETE RESTRICT,
  certainty_id     INTEGER REFERENCES certainty_level(id) ON DELETE SET NULL,
  note             TEXT,
  created_by       INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
  CHECK (source_term_id <> target_term_id),
  UNIQUE (source_term_id, target_term_id, relation_type_id)
) STRICT;

CREATE TABLE context_term_assignment (
  id           INTEGER PRIMARY KEY,
  context_id   INTEGER NOT NULL REFERENCES context(id) ON DELETE CASCADE,
  term_id      INTEGER NOT NULL REFERENCES context_term(id) ON DELETE RESTRICT,
  certainty_id INTEGER REFERENCES certainty_level(id) ON DELETE SET NULL,
  note         TEXT,
  created_by   INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
  created_at   TEXT NOT NULL,
  UNIQUE (context_id, term_id)
) STRICT;

-- ---------- OBJECT ----------------------------------------------------------
CREATE TABLE object (
  id                      INTEGER PRIMARY KEY,
  uid                     TEXT NOT NULL UNIQUE,
  inventory_number        TEXT,
  label                   TEXT,
  record_kind             TEXT NOT NULL CHECK (record_kind IN ('physical_object','fragment','reconstructed_object')),
  description             TEXT,
  condition_note          TEXT,
  completeness_percentage REAL CHECK (completeness_percentage IS NULL OR (completeness_percentage >= 0 AND completeness_percentage <= 100)),
  -- iterazione 2: decorazione + storia di restauro
  decoration_present      INTEGER CHECK (decoration_present IN (0,1) OR decoration_present IS NULL),
  decoration_note         TEXT,
  restored                INTEGER CHECK (restored IN (0,1) OR restored IS NULL),
  restoration_date        TEXT,
  restoration_note        TEXT,
  notes                   TEXT,
  is_active               INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  created_at              TEXT NOT NULL,
  updated_at              TEXT NOT NULL,
  created_by              INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
  updated_by              INTEGER REFERENCES app_user(id) ON DELETE SET NULL
) STRICT;

CREATE TABLE object_context (
  id            INTEGER PRIMARY KEY,
  object_id     INTEGER NOT NULL REFERENCES object(id) ON DELETE CASCADE,
  context_id    INTEGER NOT NULL REFERENCES context(id) ON DELETE RESTRICT,
  relation_role TEXT NOT NULL,
  certainty_id  INTEGER REFERENCES certainty_level(id) ON DELETE SET NULL,
  note          TEXT,
  UNIQUE (object_id, context_id, relation_role)
) STRICT;

CREATE TABLE object_measurement (
  id               INTEGER PRIMARY KEY,
  object_id        INTEGER NOT NULL REFERENCES object(id) ON DELETE CASCADE,
  measurement_type TEXT NOT NULL,
  value            REAL NOT NULL,
  unit             TEXT NOT NULL,
  qualifier        TEXT,
  certainty_id     INTEGER REFERENCES certainty_level(id) ON DELETE SET NULL,
  note             TEXT
) STRICT;

CREATE TABLE object_composition (
  id                  INTEGER PRIMARY KEY,
  parent_object_id    INTEGER NOT NULL REFERENCES object(id) ON DELETE CASCADE,
  component_object_id INTEGER NOT NULL REFERENCES object(id) ON DELETE CASCADE,
  sequence            INTEGER,
  certainty_id        INTEGER REFERENCES certainty_level(id) ON DELETE SET NULL,
  note                TEXT,
  CHECK (parent_object_id <> component_object_id),
  UNIQUE (component_object_id)
) STRICT;

CREATE TABLE object_relation (
  id               INTEGER PRIMARY KEY,
  uid              TEXT NOT NULL UNIQUE,
  source_object_id INTEGER NOT NULL REFERENCES object(id) ON DELETE CASCADE,
  target_object_id INTEGER NOT NULL REFERENCES object(id) ON DELETE CASCADE,
  relation_type_id INTEGER NOT NULL REFERENCES relation_type(id) ON DELETE RESTRICT,
  certainty_id     INTEGER REFERENCES certainty_level(id) ON DELETE SET NULL,
  rationale        TEXT,
  asserted_by      INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
  status           TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('accepted','proposed','rejected','superseded')),
  notes            TEXT,
  sequence         INTEGER,
  created_at       TEXT NOT NULL,
  CHECK (source_object_id <> target_object_id)
) STRICT;

CREATE TABLE object_term (
  id              INTEGER PRIMARY KEY,
  uid             TEXT NOT NULL UNIQUE,
  term_type       TEXT NOT NULL,
  preferred_label TEXT NOT NULL,
  description     TEXT,
  notes           TEXT,
  is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1))
) STRICT;

CREATE TABLE object_term_label (
  id             INTEGER PRIMARY KEY,
  object_term_id INTEGER NOT NULL REFERENCES object_term(id) ON DELETE CASCADE,
  language       TEXT NOT NULL,
  label          TEXT NOT NULL,
  label_type     TEXT NOT NULL,
  is_preferred   INTEGER NOT NULL DEFAULT 0 CHECK (is_preferred IN (0,1))
) STRICT;

CREATE TABLE object_term_relation (
  id               INTEGER PRIMARY KEY,
  source_term_id   INTEGER NOT NULL REFERENCES object_term(id) ON DELETE CASCADE,
  target_term_id   INTEGER NOT NULL REFERENCES object_term(id) ON DELETE CASCADE,
  relation_type_id INTEGER NOT NULL REFERENCES relation_type(id) ON DELETE RESTRICT,
  certainty_id     INTEGER REFERENCES certainty_level(id) ON DELETE SET NULL,
  note             TEXT,
  created_by       INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
  CHECK (source_term_id <> target_term_id),
  UNIQUE (source_term_id, target_term_id, relation_type_id)
) STRICT;

CREATE TABLE object_term_assignment (
  id           INTEGER PRIMARY KEY,
  object_id    INTEGER NOT NULL REFERENCES object(id) ON DELETE CASCADE,
  term_id      INTEGER NOT NULL REFERENCES object_term(id) ON DELETE RESTRICT,
  certainty_id INTEGER REFERENCES certainty_level(id) ON DELETE SET NULL,
  note         TEXT,
  created_by   INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
  created_at   TEXT NOT NULL,
  UNIQUE (object_id, term_id)
) STRICT;

-- ---------- WORK (opera intellettuale astratta) ---------------------------
-- Un "work" (FRBR/CIDOC-CRM: F1 Work) è un'entità testuale astratta di cui più
-- text_document possono essere testimoni: es. un editto imperiale attestato su
-- più stele, un'opera letteraria in più manoscritti, un'iscrizione votiva
-- standard replicata in più copie. text_document.work_id è opzionale: la
-- maggior parte delle iscrizioni non ha un work astratto sopra.
CREATE TABLE work (
  id                 INTEGER PRIMARY KEY,
  uid                TEXT NOT NULL UNIQUE,
  title              TEXT NOT NULL,           -- titolo canonico dell'opera
  author             TEXT,                    -- autore/emittente (se noto)
  work_type          TEXT,                    -- 'edict', 'senatus_consultum',
                                              -- 'literary_work', 'formula',
                                              -- 'liturgical_text', ecc.
  canonical_dating   TEXT,                    -- datazione compositiva (testo libero)
  composition_from   INTEGER,                 -- range compositivo (anno)
  composition_to     INTEGER,
  language           TEXT,                    -- lingua dell'opera
  description        TEXT,
  bibliography       TEXT,                    -- riferimenti canonici
  notes              TEXT,
  is_active          INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL
) STRICT;

CREATE INDEX idx_work_title      ON work(title);
CREATE INDEX idx_work_type       ON work(work_type);

-- ---------- TEXT ------------------------------------------------------------
CREATE TABLE text_document (
  id                 INTEGER PRIMARY KEY,
  uid                TEXT NOT NULL UNIQUE,
  object_id          INTEGER REFERENCES object(id) ON DELETE SET NULL,
  work_id            INTEGER REFERENCES work(id) ON DELETE SET NULL,
  witness_siglum     TEXT,                    -- sigla di questo testimone
                                              -- (es. 'A', 'B', 'β' nella recensio)
  siglum             TEXT,
  title              TEXT,
  surface            TEXT,
  position_on_object TEXT,
  orientation        TEXT,
  main_language      TEXT,
  script             TEXT,
  description        TEXT,
  notes              TEXT,
  is_active          INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL
) STRICT;

CREATE INDEX idx_text_document_work ON text_document(work_id);

CREATE TABLE text_version (
  id                  INTEGER PRIMARY KEY,
  uid                 TEXT NOT NULL UNIQUE,
  text_document_id    INTEGER NOT NULL REFERENCES text_document(id) ON DELETE CASCADE,
  version_type        TEXT NOT NULL,
  language            TEXT,
  script              TEXT,
  content             TEXT NOT NULL,
  version_number      INTEGER NOT NULL,
  based_on_version_id INTEGER REFERENCES text_version(id) ON DELETE SET NULL,
  is_current          INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0,1)),
  created_by          INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
  created_at          TEXT NOT NULL,
  note                TEXT
) STRICT;

CREATE TABLE text_unit (
  id              INTEGER PRIMARY KEY,
  text_version_id INTEGER NOT NULL REFERENCES text_version(id) ON DELETE CASCADE,
  parent_unit_id  INTEGER REFERENCES text_unit(id) ON DELETE CASCADE,
  unit_type       TEXT NOT NULL,
  label           TEXT,
  sequence        INTEGER,
  start_position  INTEGER,
  end_position    INTEGER,
  note            TEXT
) STRICT;

CREATE TABLE text_unit_alignment (
  id             INTEGER PRIMARY KEY,
  group_id       INTEGER NOT NULL,
  text_unit_id   INTEGER NOT NULL REFERENCES text_unit(id) ON DELETE CASCADE,
  role           TEXT NOT NULL DEFAULT 'parallel' CHECK (role IN ('primary','parallel','note')),
  created_at     TEXT NOT NULL,
  UNIQUE (group_id, text_unit_id)
) STRICT;
CREATE INDEX idx_alignment_group ON text_unit_alignment(group_id);
CREATE INDEX idx_alignment_unit  ON text_unit_alignment(text_unit_id);

CREATE TABLE annotation (
  id              INTEGER PRIMARY KEY,
  uid             TEXT NOT NULL UNIQUE,
  text_version_id INTEGER NOT NULL REFERENCES text_version(id) ON DELETE CASCADE,
  annotation_type TEXT NOT NULL,
  certainty_id    INTEGER REFERENCES certainty_level(id) ON DELETE SET NULL,
  note            TEXT,
  status          TEXT NOT NULL DEFAULT 'accepted' CHECK (status IN ('accepted','proposed','rejected','superseded')),
  created_by      INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
) STRICT;

CREATE TABLE annotation_span (
  id             INTEGER PRIMARY KEY,
  annotation_id  INTEGER NOT NULL REFERENCES annotation(id) ON DELETE CASCADE,
  start_position INTEGER NOT NULL CHECK (start_position >= 0),
  end_position   INTEGER NOT NULL,
  sequence       INTEGER,
  CHECK (end_position > start_position)
) STRICT;

CREATE TABLE annotation_term (
  id            INTEGER PRIMARY KEY,
  annotation_id INTEGER NOT NULL REFERENCES annotation(id) ON DELETE CASCADE,
  term_id       INTEGER NOT NULL REFERENCES text_term(id) ON DELETE RESTRICT,
  role          TEXT NOT NULL DEFAULT 'primary',
  certainty_id  INTEGER REFERENCES certainty_level(id) ON DELETE SET NULL,
  note          TEXT,
  UNIQUE (annotation_id, term_id, role)
) STRICT;

-- ---------- TEXT VOCABULARY -------------------------------------------------
CREATE TABLE text_term (
  id              INTEGER PRIMARY KEY,
  uid             TEXT NOT NULL UNIQUE,
  term_type       TEXT NOT NULL,
  preferred_label TEXT NOT NULL,
  description     TEXT,
  properties      TEXT CHECK (properties IS NULL OR json_valid(properties)),
  notes           TEXT,
  is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1))
) STRICT;

CREATE TABLE text_term_label (
  id           INTEGER PRIMARY KEY,
  term_id      INTEGER NOT NULL REFERENCES text_term(id) ON DELETE CASCADE,
  language     TEXT,
  label        TEXT NOT NULL,
  label_type   TEXT NOT NULL,
  script       TEXT,
  is_preferred INTEGER NOT NULL DEFAULT 0 CHECK (is_preferred IN (0,1))
) STRICT;

CREATE TABLE text_term_relation (
  id               INTEGER PRIMARY KEY,
  source_term_id   INTEGER NOT NULL REFERENCES text_term(id) ON DELETE CASCADE,
  target_term_id   INTEGER NOT NULL REFERENCES text_term(id) ON DELETE CASCADE,
  relation_type_id INTEGER NOT NULL REFERENCES relation_type(id) ON DELETE RESTRICT,
  certainty_id     INTEGER REFERENCES certainty_level(id) ON DELETE SET NULL,
  note             TEXT,
  created_by       INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
  created_at       TEXT NOT NULL,
  CHECK (source_term_id <> target_term_id),
  UNIQUE (source_term_id, target_term_id, relation_type_id)
) STRICT;

CREATE TABLE text_term_place (
  id                 INTEGER PRIMARY KEY,
  term_id            INTEGER NOT NULL UNIQUE REFERENCES text_term(id) ON DELETE CASCADE,
  geometry           BLOB,
  geometry_precision TEXT,
  geometry_source    TEXT,
  note               TEXT
);

CREATE TABLE text_term_external_id (
  id         INTEGER PRIMARY KEY,
  term_id    INTEGER NOT NULL REFERENCES text_term(id) ON DELETE CASCADE,
  authority  TEXT NOT NULL,
  identifier TEXT NOT NULL,
  uri        TEXT,
  note       TEXT,
  UNIQUE (term_id, authority, identifier)
) STRICT;

-- ---------- CHRONOLOGY ------------------------------------------------------
CREATE TABLE chronology_term (
  id              INTEGER PRIMARY KEY,
  uid             TEXT NOT NULL UNIQUE,
  preferred_label TEXT NOT NULL,
  year_from       INTEGER,
  year_to         INTEGER,
  precision       TEXT,
  description     TEXT,
  notes           TEXT,
  is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  CHECK (year_from IS NULL OR year_to IS NULL OR year_from <= year_to)
) STRICT;

CREATE TABLE chronology_term_relation (
  id               INTEGER PRIMARY KEY,
  source_term_id   INTEGER NOT NULL REFERENCES chronology_term(id) ON DELETE CASCADE,
  target_term_id   INTEGER NOT NULL REFERENCES chronology_term(id) ON DELETE CASCADE,
  relation_type_id INTEGER NOT NULL REFERENCES relation_type(id) ON DELETE RESTRICT,
  certainty_id     INTEGER REFERENCES certainty_level(id) ON DELETE SET NULL,
  note             TEXT,
  created_by       INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
  created_at       TEXT,
  CHECK (source_term_id <> target_term_id),
  UNIQUE (source_term_id, target_term_id, relation_type_id)
) STRICT;

CREATE TABLE context_chronology (
  id                 INTEGER PRIMARY KEY,
  context_id         INTEGER NOT NULL REFERENCES context(id) ON DELETE CASCADE,
  chronology_term_id INTEGER REFERENCES chronology_term(id) ON DELETE SET NULL,
  absolute_from      INTEGER,
  absolute_to        INTEGER,
  certainty_id       INTEGER REFERENCES certainty_level(id) ON DELETE SET NULL,
  dating_method      TEXT,
  note               TEXT,
  created_by         INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
  CHECK (absolute_from IS NULL OR absolute_to IS NULL OR absolute_from <= absolute_to)
) STRICT;

CREATE TABLE object_chronology (
  id                 INTEGER PRIMARY KEY,
  object_id          INTEGER NOT NULL REFERENCES object(id) ON DELETE CASCADE,
  chronology_term_id INTEGER REFERENCES chronology_term(id) ON DELETE SET NULL,
  absolute_from      INTEGER,
  absolute_to        INTEGER,
  certainty_id       INTEGER REFERENCES certainty_level(id) ON DELETE SET NULL,
  dating_method      TEXT,
  note               TEXT,
  created_by         INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
  created_at         TEXT NOT NULL,
  CHECK (absolute_from IS NULL OR absolute_to IS NULL OR absolute_from <= absolute_to)
) STRICT;

CREATE TABLE text_chronology (
  id                 INTEGER PRIMARY KEY,
  text_document_id   INTEGER NOT NULL REFERENCES text_document(id) ON DELETE CASCADE,
  chronology_term_id INTEGER REFERENCES chronology_term(id) ON DELETE SET NULL,
  absolute_from      INTEGER,
  absolute_to        INTEGER,
  certainty_id       INTEGER REFERENCES certainty_level(id) ON DELETE SET NULL,
  dating_method      TEXT,
  note               TEXT,
  created_by         INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
  created_at         TEXT NOT NULL,
  CHECK (absolute_from IS NULL OR absolute_to IS NULL OR absolute_from <= absolute_to)
) STRICT;

-- ---------- CRITICAL APPARATUS ---------------------------------------------
CREATE TABLE apparatus_entry (
  id              INTEGER PRIMARY KEY,
  uid             TEXT NOT NULL UNIQUE,
  text_version_id INTEGER NOT NULL REFERENCES text_version(id) ON DELETE CASCADE,
  start_position  INTEGER,
  end_position    INTEGER,
  note            TEXT
) STRICT;

CREATE TABLE apparatus_reading (
  id                 INTEGER PRIMARY KEY,
  apparatus_entry_id INTEGER NOT NULL REFERENCES apparatus_entry(id) ON DELETE CASCADE,
  reading            TEXT NOT NULL,
  is_preferred       INTEGER NOT NULL DEFAULT 0 CHECK (is_preferred IN (0,1)),
  certainty_id       INTEGER REFERENCES certainty_level(id) ON DELETE SET NULL,
  responsible_person INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
  note               TEXT
) STRICT;

-- ---------- BIBLIOGRAPHY & MEDIA (base) ------------------------------------
CREATE TABLE bibliography (
  id                INTEGER PRIMARY KEY,
  uid               TEXT NOT NULL UNIQUE,
  citation_key      TEXT UNIQUE,
  entry_type        TEXT,
  authors           TEXT,
  editors           TEXT,
  year              INTEGER,
  title             TEXT,
  container_title   TEXT,
  volume            TEXT,
  issue             TEXT,
  pages             TEXT,
  publisher         TEXT,
  publication_place TEXT,
  doi               TEXT,
  url               TEXT,
  csl_json          TEXT CHECK (csl_json IS NULL OR json_valid(csl_json)),
  notes             TEXT
) STRICT;

CREATE TABLE media (
  id               INTEGER PRIMARY KEY,
  uid              TEXT NOT NULL UNIQUE,
  media_type       TEXT NOT NULL,
  file_path        TEXT,
  mime_type        TEXT,
  title            TEXT,
  description      TEXT,
  creator          TEXT,
  creation_date    TEXT,
  copyright_holder TEXT,
  license          TEXT,
  metadata         TEXT CHECK (metadata IS NULL OR json_valid(metadata)),
  notes            TEXT
) STRICT;

-- ---------- FULL-TEXT SEARCH ------------------------------------------------
CREATE VIRTUAL TABLE text_version_fts USING fts5(
  content,
  text_version_id UNINDEXED,
  tokenize = 'unicode61 remove_diacritics 2'
);

-- ---------- INDICI ----------------------------------------------------------
CREATE INDEX idx_object_context_object   ON object_context(object_id);
CREATE INDEX idx_object_context_context  ON object_context(context_id);
CREATE INDEX idx_ota_object              ON object_term_assignment(object_id);
CREATE INDEX idx_ota_term                ON object_term_assignment(term_id);
CREATE INDEX idx_cta_context             ON context_term_assignment(context_id);
CREATE INDEX idx_cta_term                ON context_term_assignment(term_id);
CREATE INDEX idx_annotation_tv           ON annotation(text_version_id);
CREATE INDEX idx_span_annotation         ON annotation_span(annotation_id);
CREATE INDEX idx_span_range              ON annotation_span(start_position, end_position);
CREATE INDEX idx_annterm_annotation      ON annotation_term(annotation_id);
CREATE INDEX idx_annterm_term            ON annotation_term(term_id);
CREATE INDEX idx_text_term_type          ON text_term(term_type);
CREATE INDEX idx_ttr_source              ON text_term_relation(source_term_id);
CREATE INDEX idx_ttr_target              ON text_term_relation(target_term_id);
CREATE INDEX idx_chron_years             ON chronology_term(year_from, year_to);
CREATE INDEX idx_ctx_chron_ctx           ON context_chronology(context_id);
CREATE INDEX idx_obj_chron_obj           ON object_chronology(object_id);
CREATE INDEX idx_txt_chron_doc           ON text_chronology(text_document_id);
CREATE INDEX idx_biblio_key              ON bibliography(citation_key);
CREATE INDEX idx_text_version_doc        ON text_version(text_document_id);
CREATE INDEX idx_text_document_object    ON text_document(object_id);
CREATE INDEX idx_object_relation_source  ON object_relation(source_object_id);
CREATE INDEX idx_object_relation_target  ON object_relation(target_object_id);
