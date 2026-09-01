#!/usr/bin/env python3
"""
Avvio dell'applicazione Stele DBMS (versione locale).

Uso:
    python run.py                 # crea/apre ./MyEpigraphicProject e avvia il server
    STELE_PROJECT_DB=/percorso/project.gpkg python run.py
    STELE_DB_URL=postgresql://user:pw@localhost/stele python run.py   # backend PostgreSQL

Poi apri http://127.0.0.1:5000 nel browser.
"""
import os
from stele_app import create_app

if __name__ == "__main__":
    app = create_app()
    host = os.environ.get("STELE_HOST", "127.0.0.1")
    port = int(os.environ.get("STELE_PORT", "5000"))
    print(f"\n  Stele DBMS — progetto: {app.config['PROJECT_DB']}")
    print(f"  Apri:  http://{host}:{port}\n")
    app.run(host=host, port=port, debug=True)
