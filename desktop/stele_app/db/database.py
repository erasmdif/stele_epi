"""
Astrazione di connessione al database.

Default: SQLite / GeoPackage (file .gpkg), zero servizi.
Opzionale: PostgreSQL / PostGIS se STELE_DB_URL punta a postgres:// e psycopg è
installato. Lo schema logico è identico; cambia solo il dialetto DDL.

L'app usa sempre questo modulo per ottenere connessioni, così le PRAGMA
richieste dalla specifica (foreign_keys, WAL) sono applicate in un solo punto.
"""
import os
import sqlite3

BACKEND_SQLITE = "sqlite"
BACKEND_POSTGRES = "postgres"


def backend_from_env():
    url = os.environ.get("STELE_DB_URL", "")
    if url.startswith("postgres://") or url.startswith("postgresql://"):
        return BACKEND_POSTGRES
    return BACKEND_SQLITE


def connect_sqlite(path):
    """Connessione SQLite/GeoPackage con le PRAGMA della specifica."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def connect_postgres(url=None):
    """Connessione PostgreSQL/PostGIS (richiede psycopg installato)."""
    try:
        import psycopg
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "Backend PostgreSQL richiesto ma 'psycopg' non è installato. "
            "Installa con: pip install psycopg[binary]") from e
    url = url or os.environ["STELE_DB_URL"]
    conn = psycopg.connect(url, autocommit=False)
    return conn


def connect(path=None):
    """Ritorna una connessione secondo il backend configurato."""
    if backend_from_env() == BACKEND_POSTGRES:
        return connect_postgres()
    if path is None:
        path = os.environ.get("STELE_PROJECT_DB")
        if not path:
            raise RuntimeError("Percorso del progetto non specificato (STELE_PROJECT_DB).")
    return connect_sqlite(path)


def rows_to_dicts(cursor_or_rows):
    """Normalizza sqlite3.Row / tuple in dict Python semplici."""
    out = []
    for r in cursor_or_rows:
        if isinstance(r, sqlite3.Row):
            out.append({k: r[k] for k in r.keys()})
        elif isinstance(r, dict):
            out.append(r)
        else:
            out.append(r)
    return out
