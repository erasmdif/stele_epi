# Stele — annotatore stand-off per testi storici

App **statica** (solo HTML/CSS/JS vanilla, nessun server, nessun build step) per la
metadatazione tipo **TEI** di testi storici, a partire dalle scritture rappresentabili
in **Lineare B** (Unicode). Pensata per essere pubblicata su **GitHub Pages**.

## Cosa fa

- **Marcatura stand-off**: le note fanno riferimento a porzioni di testo tramite
  offset `[start, end)`, non a tag inseriti nel corpo. Questo consente **note multiple
  e sovrapposte** sulla stessa porzione. Esempio: su `XYZ` puoi annotare `X`, `Z` e
  l'intera `XYZ` contemporaneamente; gli underline delle note corrono come corsie
  parallele.
- **Due interfacce**:
  - `editor.html` — **Annota**: inserisci il testo (a mano, incolla o drag&drop di
    `.txt`/`.json`/`.xml`), seleziona una porzione e attribuiscile una o più note.
  - `viewer.html` — **Visualizza**: apri in sola lettura un documento già prodotto,
    oppure la sessione di lavoro corrente.
- **Scrittura Lineare B**: palette del sillabario (con traslitterazione), griglia degli
  ideogrammi e inserimento per **code point** Unicode (`U+10000`–`U+100FF`). Font
  `Noto Sans Linear B` caricato dalla pagina.
- **Luoghi e mappa**: marca una porzione come *luogo* e geocodificala con
  **OpenStreetMap/Nominatim** o **GeoNames** (o coordinate manuali). I luoghi taggati
  compaiono su una **mappa Leaflet**, sia in editor sia nel viewer.
- **Categorie di annotazione** (vocabolario controllato con colore): `lessico`,
  `persona`, `luogo`, `cronologia`, `nota`. La categoria `luogo` è quella
  geolocalizzabile e viene esportata come `<placeName>`; le altre come
  `<term>`/`<persName>`/`<date>`/`<note>`. Il colore dell'underline deriva dalla categoria.
- **Testo a righe numerate** (in editor e viewer) con **riferimenti automatici**
  `r. N, col. A–B` per ogni annotazione (colonne contate in *code point*, così un
  segno Lineare B vale una colonna).
- **Filtro note** per categoria, **legenda annotazioni** e **barra statistiche**
  (righe, token, annotazioni, note, luoghi).
- **Persistenza senza database**: salvataggio automatico nel browser (localStorage) più
  **download** dei file. I documenti restano leggibili dopo la chiusura della sessione.
- **Status bar** con nome file corrente e stato di salvataggio.

## Formati

- **`.json`** — formato nativo, round-trip completo (è ciò che conviene archiviare).
- **`.tei.xml`** — export **TEI-like**: il testo esatto è in
  `<text><body><ab xml:space="preserve">`, le annotazioni sono in
  `<standOff><listAnnotation>` con `target="#char=START,END"` (offset in **unità
  UTF-16**, coerenti con `String.slice`). Re-importabile.

Entrambe le interfacce aprono sia `.json` sia `.tei.xml`.

## Uso rapido

1. Apri `editor.html`.
2. Scrivi/incolla il testo (o usa la palette Lineare B / l'inserimento per code point).
3. Seleziona una porzione → **Nota da selezione** oppure **Luogo da selezione**.
4. Ripeti liberamente, anche su porzioni che si sovrappongono.
5. **Salva .json** (per archiviare/riaprire) o **Esporta TEI .xml**.
6. **Visualizza →** apre il viewer sul lavoro corrente.

Per GeoNames: *Impostazioni* → inserisci il tuo username GeoNames (registrazione
gratuita su geonames.org, con i web service abilitati nel profilo). Nominatim funziona
senza registrazione.

## Pubblicazione su GitHub Pages

```bash
git init
git add .
git commit -m "Stele: annotatore stand-off"
git branch -M main
git remote add origin https://github.com/<utente>/<repo>.git
git push -u origin main
```

Poi su GitHub: **Settings → Pages → Build and deployment → Source: Deploy from a branch**,
ramo `main`, cartella `/ (root)`. Il sito sarà su
`https://<utente>.github.io/<repo>/`.

### Pubblicare un documento consultabile via link

Metti un `.json` (o `.tei.xml`) nel repo, ad es. `sample/example.json`, e linka:

```
viewer.html?doc=sample/example.json
```

Il viewer lo carica in sola lettura. (Funziona su Pages/HTTP; non su `file://` per via
delle restrizioni `fetch`.)

## Note tecniche

- **Offset & Lineare B**: i segni Lineare B sono caratteri astral (coppie surrogate),
  quindi ogni segno vale **2 unità UTF-16**. Selezioni e offset restano coerenti perché
  usiamo ovunque le stesse unità di `textarea.selectionStart/End` e `String.slice`.
- **Modifiche al testo dopo l'annotazione**: gli offset vengono **rimappati** in
  automatico (inserimenti/cancellazioni prima delle note le fanno slittare; una modifica
  *interna* a una nota la fa crescere). Se una modifica spezza il confine di una nota,
  quella nota viene rimossa con avviso.
- **Estensibilità lingue**: il registro `SCRIPTS` in `assets/js/core.js` è predisposto
  per greco antico, cinese tradizionale, ecc. (font e codice `ident` TEI). Per ora la
  palette dedicata esiste solo per il Lineare B; le altre scritture si scrivono con
  tastiera/IME di sistema e font adeguati.

## Struttura

```
index.html            Home
editor.html           Interfaccia di annotazione
viewer.html           Interfaccia di visualizzazione (sola lettura)
assets/css/app.css     Stile
assets/js/core.js      Modello dati, segmentazione, lane, TEI, remap, geocoding
assets/js/linearb.js   Palette Lineare B
assets/js/editor.js    Logica editor
assets/js/viewer.js    Logica viewer
sample/example.json    Documento di esempio (toponimi cnossî)
sample/example.tei.xml Stesso documento in TEI-like
```

## Dipendenze esterne (via CDN)

- [Leaflet](https://leafletjs.com/) per la mappa
- Google Fonts: `Spectral`, `Noto Sans Linear B`
- Geocoding: Nominatim (OpenStreetMap) e/o GeoNames

Nessun pacchetto da installare, nessuna build.

## Licenza

MIT — vedi `LICENSE`.
