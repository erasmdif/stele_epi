# Stele — tools for digital epigraphy

**Stele** provides two complementary tools for annotating historical texts:

- 🌐 **[Try it online](https://erasmdif.github.io/stele_epi/web/)** — a browser-based stand-off annotator for exploring Stele without installing anything.
- 💻 **[Stele Desktop](https://github.com/erasmdif/stele_epi/releases/latest)** — a local-first epigraphic DBMS for archaeological contexts, objects, text witnesses, controlled vocabularies, relations, chronology, and analysis.

Your data remains under your control. The web edition stores its working session in browser `localStorage`; the desktop edition stores the project in a local `.gpkg` file.

## Repository layout

```text
stele_epi/
├── index.html          GitHub Pages landing page
├── assets/             Landing assets, release guide, PDF and PowerPoint presentation
├── web/                Static browser edition
├── desktop/            Flask + SQLite/GeoPackage desktop edition
├── .github/workflows/  CI, Pages, and release automation
└── README.md
```

## Web edition

The web edition is a dependency-free, stand-off text annotator written in vanilla JavaScript. It supports overlapping annotations, Linear B input, place annotations and maps, JSON round trips, and TEI-like XML import/export. GitHub Pages publishes it automatically from `main`.

The landing page also embeds the 19-slide presentation **Relational databases for epigraphy** as a browser-viewable PDF and offers both PDF and PowerPoint downloads.

## Desktop edition

Stele Desktop supports:

- line-aligned parallel text versions and immutable version history;
- controlled vocabularies and semantic relations;
- archaeological contexts, objects, fragments, works, and witnesses;
- multiple chronologies, FTS5 search, TEI export, and analytics;
- a local GeoPackage that can also be opened in QGIS.

The first launch creates a sample project from the bundled database. The Dashboard includes **Delete all sample data**, which creates a backup and replaces the demo project with a clean database while retaining the database structure and controlled vocabularies.

> **Sample-data disclaimer:** the bundled records are realistic-looking, fictional mock-ups generated with AI for software demonstration. They are not real archaeological, epigraphic, historical, bibliographic, or scholarly evidence.

## Local development

```bash
git clone https://github.com/erasmdif/stele_epi.git
cd stele_epi/desktop
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
python -m unittest discover -s tests -p 'test_*.py'
```

The static web edition can be opened directly from `web/index.html`.

## License

Free software for digital humanists. See `LICENSE`.
