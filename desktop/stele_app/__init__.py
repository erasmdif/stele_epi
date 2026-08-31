"""Stele DBMS — applicazione Flask locale (local-first)."""
import os
from flask import Flask, g

from .db import project as project_lib
from .db.database import connect_sqlite


def get_db():
    from flask import current_app
    if "db" not in g:
        g.db = connect_sqlite(current_app.config["PROJECT_DB"])
    return g.db


def create_app(project_db=None):
    app = Flask(__name__)
    project_db = project_db or os.environ.get("STELE_PROJECT_DB") \
        or os.path.join(os.getcwd(), "MyEpigraphicProject", "database", "project.gpkg")
    app.config["PROJECT_DB"] = project_db

    # crea il progetto demo se non esiste
    if not os.path.exists(project_db):
        project_lib.create_project(project_db, with_demo=True, overwrite=False)

    @app.teardown_appcontext
    def close_db(exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    from .web.routes import bp as web_bp
    from .api.routes import bp as api_bp
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    return app
