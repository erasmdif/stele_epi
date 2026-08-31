"""
Inizializzazione GeoPackage e codifica/decodifica geometrie.

Un GeoPackage è un file SQLite con alcune tabelle di sistema (gpkg_*),
un application_id dedicato e le geometrie salvate come "GeoPackage Binary"
(header GPKG + WKB standard). Qui gestiamo pienamente il tipo POINT
(il caso d'uso di context e text_term_place); poligoni e multipoligoni
possono essere aggiunti in seguito con lo stesso schema di blob.
"""
import struct

GPKG_APPLICATION_ID = 0x47504B47  # 'GPKG'
GPKG_USER_VERSION = 10300         # GeoPackage 1.3
DEFAULT_SRID = 4326               # WGS84

# --- tabelle di sistema GeoPackage -----------------------------------------
GPKG_SYSTEM_SQL = """
CREATE TABLE IF NOT EXISTS gpkg_spatial_ref_sys (
  srs_name                 TEXT NOT NULL,
  srs_id                   INTEGER NOT NULL PRIMARY KEY,
  organization             TEXT NOT NULL,
  organization_coordsys_id INTEGER NOT NULL,
  definition               TEXT NOT NULL,
  description              TEXT
);
CREATE TABLE IF NOT EXISTS gpkg_contents (
  table_name  TEXT NOT NULL PRIMARY KEY,
  data_type   TEXT NOT NULL,
  identifier  TEXT UNIQUE,
  description TEXT DEFAULT '',
  last_change TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
  srs_id INTEGER,
  CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
);
CREATE TABLE IF NOT EXISTS gpkg_geometry_columns (
  table_name         TEXT NOT NULL,
  column_name        TEXT NOT NULL,
  geometry_type_name TEXT NOT NULL,
  srs_id             INTEGER NOT NULL,
  z TINYINT NOT NULL,
  m TINYINT NOT NULL,
  CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),
  CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),
  CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
);
"""

# SRS obbligatorie richieste dallo standard, più WGS84.
GPKG_SRS_ROWS = [
    ("Undefined cartesian SRS", -1, "NONE", -1, "undefined", None),
    ("Undefined geographic SRS", 0, "NONE", 0, "undefined", None),
    ("WGS 84 geodetic", 4326, "EPSG", 4326,
     'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,'
     'AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,'
     'AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,'
     'AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]',
     "longitude/latitude coordinates in decimal degrees on the WGS 84 spheroid"),
]


def init_geopackage(conn):
    """Trasforma una connessione SQLite in un GeoPackage valido (idempotente)."""
    conn.execute("PRAGMA application_id = %d;" % GPKG_APPLICATION_ID)
    conn.execute("PRAGMA user_version = %d;" % GPKG_USER_VERSION)
    conn.executescript(GPKG_SYSTEM_SQL)
    for row in GPKG_SRS_ROWS:
        conn.execute(
            "INSERT OR IGNORE INTO gpkg_spatial_ref_sys "
            "(srs_name, srs_id, organization, organization_coordsys_id, definition, description) "
            "VALUES (?,?,?,?,?,?)", row)


def register_feature_table(conn, table_name, geometry_type="POINT",
                           srid=DEFAULT_SRID, identifier=None, description=""):
    """Registra una tabella come feature spaziale in gpkg_contents + geometry_columns."""
    conn.execute(
        "INSERT OR IGNORE INTO gpkg_contents "
        "(table_name, data_type, identifier, description, srs_id) VALUES (?,?,?,?,?)",
        (table_name, "features", identifier or table_name, description, srid))
    conn.execute(
        "INSERT OR IGNORE INTO gpkg_geometry_columns "
        "(table_name, column_name, geometry_type_name, srs_id, z, m) VALUES (?,?,?,?,0,0)",
        (table_name, "geometry", geometry_type, srid))


# --- geometrie: GeoPackage Binary (header GPKG + WKB) ----------------------
def encode_point(lon, lat, srid=DEFAULT_SRID):
    """Codifica un POINT come blob GeoPackage Binary (little-endian, senza envelope)."""
    if lon is None or lat is None:
        return None
    # header: magic 'GP', version 0, flags, srs_id(int32)
    # flags: bit0 byteorder(1=LE), bits1-3 envelope(0=nessuno) -> 0x01
    header = b"GP" + bytes([0x00, 0x01]) + struct.pack("<i", int(srid))
    # WKB: byteorder(1=LE) + type(1=Point,uint32) + x(double) + y(double)
    wkb = struct.pack("<BIdd", 1, 1, float(lon), float(lat))
    return header + wkb


def decode_point(blob):
    """Restituisce (lon, lat) da un blob GeoPackage Binary POINT, o None."""
    if not blob or len(blob) < 8 or blob[0:2] != b"GP":
        return None
    flags = blob[3]
    little = flags & 0x01
    env = (flags >> 1) & 0x07
    env_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    offset = 8 + env_sizes.get(env, 0)
    bo = "<" if little else ">"
    try:
        _byteorder, gtype = struct.unpack(bo + "BI", blob[offset:offset + 5])
        if gtype != 1:
            return None
        x, y = struct.unpack(bo + "dd", blob[offset + 5:offset + 21])
        return (x, y)
    except struct.error:
        return None
