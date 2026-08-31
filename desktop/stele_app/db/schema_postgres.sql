-- ============================================================================
-- Stele DBMS — schema PostgreSQL / PostGIS (backend opzionale)
-- Stesso modello logico dello schema SQLite; le geometrie usano tipi PostGIS.
-- Richiede: CREATE EXTENSION postgis;  (eseguito qui sotto se permesso)
-- Nota: il layer dati applicativo è al momento ottimizzato per SQLite; questo
-- file fornisce lo schema per chi preferisce PostgreSQL/PostGIS.
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE app_user (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  uid TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
  orcid TEXT, email TEXT, affiliation TEXT,
  is_active SMALLINT NOT NULL DEFAULT 1 CHECK (is_active IN (0,1))
);
CREATE TABLE certainty_level (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code TEXT NOT NULL UNIQUE, label TEXT NOT NULL, rank INTEGER NOT NULL,
  description TEXT, is_active SMALLINT NOT NULL DEFAULT 1
);
CREATE TABLE reliability_level (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code TEXT NOT NULL UNIQUE, label TEXT NOT NULL, rank INTEGER NOT NULL, description TEXT
);
CREATE TABLE relation_type (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code TEXT NOT NULL UNIQUE, label TEXT NOT NULL, inverse_label TEXT,
  domain TEXT NOT NULL, is_symmetric SMALLINT NOT NULL DEFAULT 0,
  is_hierarchical SMALLINT NOT NULL DEFAULT 0, description TEXT,
  is_active SMALLINT NOT NULL DEFAULT 1
);
CREATE TABLE context (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  uid TEXT NOT NULL UNIQUE, code TEXT UNIQUE, name TEXT, description TEXT,
  geometry geometry(Geometry,4326), geometry_precision TEXT, geometry_note TEXT,
  reliability_id BIGINT REFERENCES reliability_level(id) ON DELETE SET NULL,
  source_reference TEXT, notes TEXT,
  is_active SMALLINT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by BIGINT REFERENCES app_user(id) ON DELETE SET NULL,
  updated_by BIGINT REFERENCES app_user(id) ON DELETE SET NULL
);
CREATE INDEX idx_context_geom ON context USING GIST (geometry);

CREATE TABLE object (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  uid TEXT NOT NULL UNIQUE, inventory_number TEXT, label TEXT,
  record_kind TEXT NOT NULL CHECK (record_kind IN ('physical_object','fragment','reconstructed_object')),
  description TEXT, condition_note TEXT,
  completeness_percentage REAL CHECK (completeness_percentage IS NULL OR (completeness_percentage BETWEEN 0 AND 100)),
  notes TEXT, is_active SMALLINT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by BIGINT REFERENCES app_user(id) ON DELETE SET NULL,
  updated_by BIGINT REFERENCES app_user(id) ON DELETE SET NULL
);

CREATE TABLE text_term (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  uid TEXT NOT NULL UNIQUE, term_type TEXT NOT NULL, preferred_label TEXT NOT NULL,
  description TEXT, properties JSONB, notes TEXT, is_active SMALLINT NOT NULL DEFAULT 1
);
CREATE TABLE text_term_place (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  term_id BIGINT NOT NULL UNIQUE REFERENCES text_term(id) ON DELETE CASCADE,
  geometry geometry(Point,4326), geometry_precision TEXT, geometry_source TEXT, note TEXT
);
CREATE INDEX idx_place_geom ON text_term_place USING GIST (geometry);

-- NB: le restanti tabelle (text_document, text_version, annotation, annotation_span,
-- annotation_term, i quattro *_term/_relation/_assignment, chronology_*, apparatus_*,
-- bibliography/media e junction) replicano 1:1 lo schema SQLite sostituendo:
--   INTEGER PRIMARY KEY  ->  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
--   TEXT ISO datetime    ->  TIMESTAMPTZ
--   BLOB geometry        ->  geometry(...) PostGIS
--   json_valid()         ->  tipo JSONB nativo
-- La ricerca full-text usa tsvector/tsquery al posto di FTS5.
-- Questo file è fornito come base; il layer dati applicativo verrà parametrizzato
-- (placeholder %s, RETURNING id) per il backend PostgreSQL nella prossima iterazione.
