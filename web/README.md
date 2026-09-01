# Stele — stand-off annotation for historical texts

This is the static browser edition of Stele: vanilla HTML, CSS, and JavaScript with no server or build step. It is designed for GitHub Pages and provides a compact introduction to stand-off annotation.

## Features

- Overlapping stand-off annotations using `[start, end)` offsets.
- Separate editor and read-only viewer interfaces.
- Linear B syllabary and ideogram input with Unicode code-point support.
- Controlled annotation categories for lexical items, people, places, chronology, and notes.
- Place geocoding through Nominatim or GeoNames, plus Leaflet maps.
- Numbered text lines, automatic annotation references, filters, legend, and statistics.
- Automatic browser-session persistence and downloadable project files.

## Formats

- `.json` is the native, lossless round-trip format.
- `.tei.xml` stores the exact text in `<ab xml:space="preserve">` and stand-off annotations in `<listAnnotation>` with `target="#char=START,END"`.

Both the editor and viewer can reopen JSON and TEI-like XML files.

## Quick use

1. Open `editor.html`.
2. Type, paste, or load a text.
3. Select a range and add one or more annotations.
4. Save JSON for later editing or export TEI XML.
5. Open the current work in the Viewer.

The sample files in `sample/` can be loaded directly. A published document can also be opened with:

```text
viewer.html?doc=sample/example.json
```

> **Sample disclaimer:** the supplied example is a realistic-looking, fictional mock-up generated with AI solely to demonstrate the interface. It is not a scholarly edition or evidence source.

## Files

```text
index.html             Home
editor.html            Annotation interface
viewer.html            Read-only viewer
assets/css/app.css      Styling
assets/js/core.js       Data model, segmentation, TEI, remapping, geocoding
assets/js/linearb.js    Linear B palette
assets/js/editor.js     Editor logic
assets/js/viewer.js     Viewer logic
sample/example.json     Sample document
sample/example.tei.xml  Sample TEI-like document
```

External browser dependencies are loaded from CDNs: Leaflet, Spectral, and Noto Sans Linear B. No package installation is required for normal use.

## License

MIT — see `LICENSE`.
