"""Stele DBMS — local-first application."""
import os
from flask import Flask, g

from .db import project as project_lib
from .db.database import connect_sqlite

APP_VERSION = "1.0.2"


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

    # Create the canonical sample project on first run; migrate existing
    # projects non-destructively before the first request is served.
    if not os.path.exists(project_db):
        project_lib.create_project(project_db, with_demo=True, overwrite=False)
    else:
        migration_conn = project_lib.open_project(project_db)
        migration_conn.close()

    app.config["APP_VERSION"] = APP_VERSION
    sample_check_conn = connect_sqlite(project_db)
    try:
        app.config["SAMPLE_DATA_ACTIVE"] = project_lib.has_sample_data(sample_check_conn)
    finally:
        sample_check_conn.close()

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
