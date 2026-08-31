# Stele — strumenti per l'epigrafia digitale

**Stele** è un progetto che offre due strumenti complementari per l'annotazione di testi storici:

- 🌐 **[Prova online](https://erasmdif.github.io/stele_epi/web/)** — un annotatore stand-off che gira nel browser, per capire cosa fa Stele in cinque minuti;
- 💻 **[Stele Desktop](https://github.com/erasmdif/stele_epi/releases/latest)** — un DBMS completo per progetti epigrafici, che gestisce contesti archeologici, oggetti, versioni testuali parallele, vocabolari controllati con rete semantica, cronologie multiple.

I dati sono sempre e solo tuoi: la versione web lavora nel `localStorage` del browser, la versione desktop in un file `.gpkg` sul tuo disco.

---

## Struttura del repo

```
stele_epi/
├── index.html         ← landing page (GitHub Pages la serve qui)
├── assets/            ← css/js/img condivisi con la landing
├── web/               ← versione online (statica, JS puro)
│   ├── index.html
│   ├── editor.html    ← annotatore stand-off
│   ├── viewer.html    ← lettore TEI
│   └── assets/
├── desktop/           ← Stele Desktop (Flask + SQLite/GeoPackage)
│   ├── stele_app/     ← codice applicativo (models, api, web, static, templates)
│   ├── tests/         ← test suite (163 test)
│   ├── launcher.py    ← launcher unico cross-platform
│   ├── run.py         ← modo "avanzato" per sviluppatori
│   └── requirements.txt
├── .github/workflows/ ← CI, GitHub Pages, release automatiche
└── README.md          ← questo file
```

## Cosa fa cosa

### Versione web (`web/`)

Un annotatore stand-off tipo TEI in JavaScript puro. Serve per:
- capire il concetto stand-off senza installare niente;
- annotare un singolo testo, esportarlo in TEI-XML;
- dimostrare Stele a chi lo vede per la prima volta.

Pubblicata automaticamente su **GitHub Pages** a ogni push su `main`.

### Stele Desktop (`desktop/`)

Un DBMS completo per progetti epigrafici, con:
- versioni testuali parallele (`diplomatic_transcription`, `transliteration`, `translation`, …) **allineate riga↔riga**;
- vocabolari controllati (persone, luoghi, divinità, tipi archeologici, cronologie) con **rete semantica** ereditata via CTE ricorsive;
- contesti archeologici (`deposit_type`, `excavation_technique`, geometria, cronologia multipla, oggetti trovati);
- oggetti (`decoration`, `restoration`, composizione, misure, cronologia visuale);
- ricerca full-text FTS5, export TEI-XML;
- 163 test automatici.

Distribuita come **pacchetto scaricabile** per macOS / Windows / Linux nelle [Releases](https://github.com/erasmdif/stele_epi/releases). Doppio clic sull'icona, nessuna riga di comando.

## Sviluppo locale

Per lavorare al codice:

```bash
git clone https://github.com/erasmdif/stele_epi.git
cd stele_epi

# versione web: apri direttamente nel browser
open web/index.html   # macOS
xdg-open web/index.html   # Linux

# versione desktop
cd desktop
python launcher.py    # avvia con setup automatico
# oppure per sviluppatori:
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py         # avvio "sviluppo" (Flask debug ecc.)
python -m pytest tests/   # test
```

## Licenza

Software libero. Made for digital humanists.
