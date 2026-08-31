# Stele Desktop

Un DBMS completo per progetti di epigrafia digitale. Vedi la [landing del progetto](https://erasmdif.github.io/stele_epi/) e la [versione online](https://erasmdif.github.io/stele_epi/web/) per una vetrina.

## Avvio rapido (per utenti)

Scarica il pacchetto per il tuo sistema dalle [Releases](https://github.com/erasmdif/stele_epi/releases/latest), scompatta, doppio clic sull'icona. Al primo avvio il launcher prepara l'ambiente Python locale (~1 minuto) e apre il browser sull'applicazione.

I tuoi dati stanno in una cartella standard del tuo sistema (fuori dall'app, sopravvive agli aggiornamenti):

- macOS: `~/Library/Application Support/Stele Desktop/`
- Windows: `%APPDATA%\Stele Desktop\`
- Linux: `~/.local/share/stele-desktop/`

## Avvio da sorgente (per sviluppatori)

```bash
cd desktop
python launcher.py                          # tutto automatico
python launcher.py --port 8080              # forza porta
python launcher.py --no-browser             # solo server
python launcher.py --data-dir /tmp/test     # cartella dati custom (utile per QA)
python launcher.py --reset-demo             # ricrea il progetto demo
```

Oppure il modo "sviluppo tradizionale":

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                # avvia Flask direttamente
python -m pytest tests/      # esegue i test
```

---

# Stele DBMS — versione locale (local-first)

Estensione **desktop/locale** di *Stele* da annotatore stand-off a **DBMS
epigrafico**: struttura i dati e dà profondità informativa a contesto e supporto,
con vocabolari gerarchici e una rete semantica N:M fra le entità.

Affianca la versione online/GitHub Pages (che resta invariata): questa gira in
locale con **Python/Flask** e un **database su file**.

## Caratteristiche

- **Backend Python/Flask**, servito su `http://127.0.0.1:5000`.
- **Doppio backend database dietro un'astrazione**:
  - **default: SQLite / GeoPackage** (`project.gpkg`) — zero installazioni,
    apribile direttamente in QGIS;
  - **opzionale: PostgreSQL / PostGIS** (variabile `STELE_DB_URL`).
- **Annotazione stand-off** come da specifica: `annotation → annotation_span →
  annotation_term`, offset in **code point NFC** `[start, end)`, versioni testuali
  **immutabili**, annotazioni **sovrapposte e discontinue**.
- **Quattro vocabolari gerarchici** (context / object / text / chronology) con
  relazioni **N:M auto-referenziali**: la profondità informativa (es.
  *Minerva → Roman deity → Classical pantheon*, oppure la tipologia inferita di un
  oggetto) è calcolata con **CTE ricorsive**.
- **GIS leggero reale**: `context` e `text_term_place` sono feature table
  GeoPackage registrate; geometrie POINT come GPKG WKB.
- **Ricerca full-text** (FTS5) e **export TEI-XML** come vista del modello.
- **Editing del testo con versioning**: le versioni annotate sono immutabili (§9),
  quindi modificare il testo **crea una nuova `text_version`**; gli offset delle
  annotazioni vengono **remappati** (prefisso/suffisso comune) e migrati
  automaticamente, mentre quelle che attraversano il punto di modifica restano
  sulla versione precedente e sono segnalate. Selettore di versione nella vista testo.
- **Grafo delle relazioni** interattivo (force-directed, SVG vanilla JS): ego-network
  di un termine con relazioni semantiche **tipizzate** e **co-occorrenze** nel testo,
  profondità regolabile, filtri per tipo di arco, pannello di dettaglio con gerarchia,
  relazioni dirette e **percorso dal focus**.
- **Workbench con annotazione editabile**: navigazione a sidebar (Dashboard, Contesti,
  Oggetti, Testi, Vocabolari, Relazioni, Cronologia, Ricerca); scheda oggetto con
  composizione, tipi inferiti e relazioni scientifiche; **vista di annotazione
  scrivibile** — selezione del testo → crea annotazione, modifica
  tipo/nota/certezza/stato, span multipli (annotazioni discontinue), assegnazione e
  **creazione di termini**, **geocoding** dei luoghi (coordinate manuali o ricerca
  OpenStreetMap), costruzione della **rete semantica** fra termini (relazioni
  gerarchiche con anti-ciclo), anteprima TEI live e mappa dei luoghi. Ogni scrittura
  passa per validazioni applicative (§23) ed è tracciata in `change_log`.

## Avvio

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Al primo avvio viene creato un progetto dimostrativo in
`./MyEpigraphicProject/database/project.gpkg` (esempio della specifica + tavoletta
in Lineare B). Poi apri **http://127.0.0.1:5000**.

Per usare un progetto specifico:

```bash
STELE_PROJECT_DB=/percorso/mio/project.gpkg python run.py
```

Per il backend PostgreSQL/PostGIS (schema fornito in `stele_app/db/schema_postgres.sql`):

```bash
pip install "psycopg[binary]"
STELE_DB_URL=postgresql://utente:password@localhost/stele python run.py
```

> Stato: il percorso **SQLite/GeoPackage è completo e testato**; il percorso
> PostgreSQL fornisce lo schema e la connessione, e il layer dati verrà
> parametrizzato per Postgres nell'iterazione successiva.

## Struttura

```
stele_software/
├── run.py                     # entrypoint
├── requirements.txt
├── stele_app/
│   ├── __init__.py            # create_app() + gestione progetto
│   ├── db/
│   │   ├── database.py        # connessione + PRAGMA (foreign_keys, WAL) + switch backend
│   │   ├── geopackage.py      # GeoPackage valido + geometrie POINT (GPKG WKB)
│   │   ├── schema_sqlite.sql  # schema completo (STRICT, CHECK, FK, FTS5, indici)
│   │   ├── schema_postgres.sql# schema PostGIS (backend opzionale)
│   │   ├── seeds.sql          # vocabolari trasversali
│   │   └── project.py         # crea/apri progetto, junction, seed vocabolari, dati demo
│   ├── models.py              # repository + CTE ricorsive (gerarchie, grafo)
│   ├── mutations.py           # scritture + validazioni applicative (§23) + audit
│   ├── tei.py                 # export TEI stand-off
│   ├── api/routes.py          # API JSON (lettura + scrittura)
│   ├── web/routes.py          # pagine del workbench
│   ├── templates/             # shell + dashboard + oggetti + annota + …
│   └── static/                # CSS + workbench annotazione + grafo relazioni (vanilla JS)
└── tests/
    ├── test_db.py             # checklist §31 della specifica
    ├── test_editing.py        # flusso di editing dell'annotazione via API
    └── test_versioning_graph.py  # remap/versioning del testo + grafo relazioni
```

## Test

```bash
python tests/test_db.py               # fondazione DBMS (checklist §31)
python tests/test_editing.py          # editing dell'annotazione via API
python tests/test_versioning_graph.py # versioning/remap del testo + grafo relazioni
```

`test_db.py` copre: `foreign_keys ON`, GeoPackage valido e feature table registrate,
geometria point, CTE ricorsive sui vocabolari, annotazioni sovrapposte e discontinue,
Unicode multi-script (latino/greco/CJK/Lineare B) in NFC, immutabilità e vincoli,
validazioni applicative, round-trip TEI, ricerca FTS5.
`test_editing.py` copre: creazione da selezione, validazioni degli offset,
assegnazione/creazione termini, span discontinui, geocoding, rete semantica con
anti-ciclo, patch, audit e cancellazione a cascata.

## Modello dati

Lo schema segue la specifica allegata (32 sezioni, ~50 tabelle): quattro domini
controllati distinti, annotazione stand-off, cronologie in numerazione astronomica
(1 a.C. = 0), apparato critico, bibliografia e media con junction a vera FK,
audit e cancellazione logica. L'export TEI è un livello di trasformazione separato.
