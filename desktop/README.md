# Stele Desktop

Stele Desktop is a local-first database application for digital epigraphy. See the [project landing page](https://erasmdif.github.io/stele_epi/) or [try the browser edition](https://erasmdif.github.io/stele_epi/web/).

## Quick start

Download the package for your operating system from [GitHub Releases](https://github.com/erasmdif/stele_epi/releases/latest), extract it, and start Stele Desktop. The application opens in your browser but runs only on `127.0.0.1` and stores the project outside the application folder, so application upgrades do not overwrite your data.

Default data locations:

- macOS: `~/Library/Application Support/Stele Desktop/`
- Windows: `%APPDATA%\Stele Desktop\`
- Linux: `~/.local/share/stele-desktop/`

On first launch, Stele copies the bundled sample database to the data directory. To start a real project, use **Delete all sample data** on the Dashboard. You must type `REMOVE SAMPLE DATA` to confirm. Stele automatically creates a timestamped backup before replacing the sample contents with a clean database.

> **Important:** all bundled sample records are realistic-looking, fictional mock-ups generated with AI to demonstrate the application. They are not real archaeological, epigraphic, historical, bibliographic, or scholarly evidence and must not be cited as such.

## Running from source

```bash
cd desktop
python launcher.py
python launcher.py --port 8080
python launcher.py --no-browser
python launcher.py --data-dir /tmp/stele-qa
python launcher.py --reset-demo
```

Traditional development setup:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

The default development project is `MyEpigraphicProject/database/project.gpkg`. To open another GeoPackage:

```bash
STELE_PROJECT_DB=/path/to/project.gpkg python run.py
```

## Main features

- SQLite/GeoPackage storage with foreign keys, WAL, FTS5, and QGIS-compatible feature tables.
- Stand-off, overlapping, and discontinuous annotations using NFC code-point offsets.
- Immutable text versions with automatic offset remapping.
- Parallel diplomatic transcription, transliteration, translation, and commentary witnesses.
- Hierarchical context, object, text, and chronology vocabularies.
- Archaeological contexts, objects, fragments, reconstructed objects, works, and witnesses.
- Semantic graph, chronological views, textual/spatial analytics, and TEI XML export.
- Application-level validation and an auditable `change_log`.

Existing project files are migrated automatically when opened by a newer version of the application.

## Tests

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

Some legacy scenario tests are directly executable with `python tests/<name>.py`.

## Optional PostgreSQL backend

The default and fully tested backend is SQLite/GeoPackage. A PostgreSQL/PostGIS schema and connection adapter are provided for future backend work:

```bash
pip install "psycopg[binary]"
STELE_DB_URL=postgresql://user:password@localhost/stele python run.py
```
