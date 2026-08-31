/* ============================================================================
 * Stele — core.js
 * Modello dati e logica condivisa fra editor e viewer.
 *
 * Modello "stand-off": il testo è una stringa piatta; ogni annotazione fa
 * riferimento a una porzione tramite offset [start, end) in UNITÀ UTF-16
 * (le stesse di String.prototype.slice e di textarea.selectionStart/End).
 * Questo permette annotazioni SOVRAPPOSTE e MULTIPLE sulla stessa porzione.
 *
 * Funziona sia nel browser (window.TA) sia in Node (module.exports) per i test.
 * ==========================================================================*/
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.TA = api;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const SCHEMA_VERSION = '1.0';

  // Palette per gli underline delle annotazioni (colori distinti e leggibili).
  const PALETTE = [
    '#2a6f7a', '#b5561f', '#3b6db3', '#7a4fb0', '#2f8f4e',
    '#b0872a', '#c0447a', '#4a5bd0', '#6f8f1f', '#0e8a8a'
  ];
  function colorFor(i) { return PALETTE[((i % PALETTE.length) + PALETTE.length) % PALETTE.length]; }

  // Categorie di annotazione (vocabolario controllato, con colore e mappatura
  // TEI). 'luogo' è la categoria geolocalizzabile (equivale al tipo 'place').
  const CATEGORIES = {
    lessico:    { label: 'lessico',    color: '#2f7d5b', tei: 'term' },
    persona:    { label: 'persona',    color: '#7a4fb0', tei: 'persName' },
    luogo:      { label: 'luogo',      color: '#2a6f9a', tei: 'placeName', place: true },
    cronologia: { label: 'cronologia', color: '#c07b1f', tei: 'date' },
    nota:       { label: 'nota',       color: '#6b6559', tei: 'note' }
  };
  const CATEGORY_ORDER = ['lessico', 'persona', 'luogo', 'cronologia', 'nota'];
  function colorForCategory(c) { return (CATEGORIES[c] || {}).color || null; }
  function categoryOf(a) {
    if (a && a.category && CATEGORIES[a.category]) return a.category;
    return (a && a.type === 'place') ? 'luogo' : 'nota';
  }

  // Registro degli "script" storici. Per ora solo Lineare B è pienamente
  // supportato con palette dedicata; gli altri sono predisposti.
  const SCRIPTS = {
    'linear-b': { label: 'Lineare B (miceneo)', tei: 'gmy', font: '"Noto Sans Linear B", serif', palette: true },
    'greek-ancient': { label: 'Greco antico', tei: 'grc', font: '"Noto Serif", "GFS Neohellenic", serif', palette: false },
    'chinese-trad': { label: 'Cinese tradizionale', tei: 'lzh-Hant', font: '"Noto Serif TC", serif', palette: false },
    'latin': { label: 'Latino', tei: 'lat', font: 'inherit', palette: false },
    'other': { label: 'Altro / non specificato', tei: 'und', font: 'inherit', palette: false }
  };

  function uid() {
    return 'a' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function escapeXml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function newDoc(overrides) {
    const now = new Date().toISOString();
    return Object.assign({
      schema: SCHEMA_VERSION,
      meta: {
        title: '', author: '', script: 'linear-b',
        description: '', created: now, modified: now
      },
      text: '',
      annotations: [] // { id, start, end, type:'note'|'place', note, tags[], color, place? }
    }, overrides || {});
  }

  function clampOffset(o, len) {
    o = Math.round(Number(o) || 0);
    if (o < 0) return 0;
    if (o > len) return len;
    return o;
  }

  /* --- Segmentazione: dal modello stand-off a segmenti renderizzabili ------
   * Calcola tutti i punti di confine (start/end di ogni annotazione) e spezza
   * il testo in segmenti; ogni segmento riporta gli id delle annotazioni che
   * lo coprono. Gestisce nativamente sovrapposizioni parziali e totali. */
  function buildSegments(text, anns) {
    text = text || '';
    const len = text.length;
    const valid = (anns || []).filter(a => a && a.end > a.start);
    const points = new Set([0, len]);
    valid.forEach(a => {
      points.add(clampOffset(a.start, len));
      points.add(clampOffset(a.end, len));
    });
    const bounds = Array.from(points).sort((x, y) => x - y);
    const segs = [];
    for (let i = 0; i < bounds.length - 1; i++) {
      const s = bounds[i], e = bounds[i + 1];
      if (e <= s) continue;
      const covering = valid.filter(a => a.start <= s && a.end >= e);
      segs.push({ start: s, end: e, text: text.slice(s, e), anns: covering.map(a => a.id) });
    }
    return segs;
  }

  /* --- Assegnazione "lane": ogni annotazione ottiene una corsia stabile, così
   * gli underline delle annotazioni che si sovrappongono corrono paralleli
   * (packing greedy per intervalli). */
  function assignLanes(anns) {
    const sorted = (anns || []).filter(a => a.end > a.start)
      .slice().sort((a, b) => (a.start - b.start) || (b.end - a.end));
    const laneEnds = [];
    const lane = {};
    for (const a of sorted) {
      let placed = false;
      for (let i = 0; i < laneEnds.length; i++) {
        if (laneEnds[i] <= a.start) { lane[a.id] = i; laneEnds[i] = a.end; placed = true; break; }
      }
      if (!placed) { lane[a.id] = laneEnds.length; laneEnds.push(a.end); }
    }
    return lane;
  }

  function colorMapFor(doc) {
    const m = {};
    (doc.annotations || []).forEach((a, i) => {
      m[a.id] = a.color || colorForCategory(categoryOf(a)) || colorFor(i);
    });
    return m;
  }

  const LANE_STEP = 4; // px fra un underline e l'altro
  const BAR = 3;       // px spessore underline

  // <span> per un singolo pezzo di segmento (già spezzato sui newline).
  function segSpanHTML(piece, lanes, colorMap, typeMap) {
    const t = escapeHtml(piece.text);
    if (!piece.anns.length) {
      return `<span class="seg" data-start="${piece.start}" data-end="${piece.end}">${t}</span>`;
    }
    const bars = piece.anns
      .map(id => ({ lane: lanes[id], color: colorMap[id], place: typeMap[id] === 'place' }))
      .sort((a, b) => a.lane - b.lane);
    const img = bars.map(b => `linear-gradient(${b.color},${b.color})`).join(',');
    const size = bars.map(() => `100% ${BAR}px`).join(',');
    const pos = bars.map(b => `0 calc(100% - ${b.lane * LANE_STEP}px)`).join(',');
    const style = `background-image:${img};background-size:${size};background-position:${pos};background-repeat:no-repeat;`;
    const cls = 'seg ann' + (bars.some(b => b.place) ? ' has-place' : '');
    return `<span class="${cls}" data-start="${piece.start}" data-end="${piece.end}" data-anns="${piece.anns.join(' ')}" style="${style}">${t}</span>`;
  }

  /* --- Render del testo annotato in HTML, RAGGRUPPATO PER RIGHE -------------
   * Ogni riga logica del testo (separata da \n) diventa una riga con numero
   * nel margine; le annotazioni che attraversano un \n proseguono sulla riga
   * successiva. Restituisce { html, lanes, colorMap, maxLane }. */
  function renderAnnotatedHTML(doc) {
    const anns = doc.annotations || [];
    const lanes = assignLanes(anns);
    const colorMap = colorMapFor(doc);
    const typeMap = {}; anns.forEach(a => { typeMap[a.id] = a.type || 'note'; });
    const segs = buildSegments(doc.text || '', anns);
    let maxLane = 0; Object.values(lanes).forEach(l => { if (l > maxLane) maxLane = l; });

    // Spezza i segmenti sui newline in "pezzi" con offset propri.
    const pieces = [];
    for (const seg of segs) {
      const parts = seg.text.split('\n');
      let off = seg.start;
      for (let k = 0; k < parts.length; k++) {
        const pt = parts[k];
        pieces.push({ text: pt, start: off, end: off + pt.length, anns: seg.anns, br: k < parts.length - 1 });
        off += pt.length + (k < parts.length - 1 ? 1 : 0);
      }
    }
    // Raggruppa i pezzi in righe.
    const lines = []; let cur = [];
    for (const p of pieces) { cur.push(p); if (p.br) { lines.push(cur); cur = []; } }
    lines.push(cur);

    const rows = lines.map((ln, i) => {
      const content = ln.map(p => segSpanHTML(p, lanes, colorMap, typeMap)).join('');
      return `<div class="ln" data-line="${i + 1}"><span class="lno">${i + 1}</span>` +
        `<span class="lc">${content || '\u200b'}</span></div>`;
    }).join('');
    const html = `<div class="lines">${rows}</div>`;
    return { html, lanes, colorMap, maxLane };
  }

  /* --- Remapping degli offset dopo un'edit del testo -----------------------
   * Best-effort: confronta vecchio e nuovo testo tramite prefisso/suffisso
   * comune. Le annotazioni prima della modifica restano; quelle dopo slittano;
   * quelle che contengono l'intera regione modificata crescono/decrescono;
   * quelle che intersecano solo parzialmente il confine vengono marcate
   * "orphan" (verranno segnalate all'utente). */
  function remapAnnotations(anns, oldText, newText) {
    if (oldText === newText) return { annotations: anns.slice(), orphans: [] };
    const oldLen = oldText.length, newLen = newText.length;
    let p = 0;
    const maxP = Math.min(oldLen, newLen);
    while (p < maxP && oldText.charCodeAt(p) === newText.charCodeAt(p)) p++;
    let q = 0;
    while (q < (maxP - p) &&
      oldText.charCodeAt(oldLen - 1 - q) === newText.charCodeAt(newLen - 1 - q)) q++;
    const regionStart = p;
    const regionOldEnd = oldLen - q;   // fine regione modificata nel vecchio testo
    const delta = newLen - oldLen;

    const kept = [];
    const orphans = [];
    for (const a of anns) {
      const s = a.start, e = a.end;
      if (e <= regionStart) { kept.push(a); continue; }                 // tutto prima
      if (s >= regionOldEnd) { kept.push(shift(a, delta)); continue; }  // tutto dopo
      if (s <= regionStart && e >= regionOldEnd) {                      // contiene la regione
        kept.push(Object.assign({}, a, { end: e + delta })); continue;
      }
      orphans.push(a); // intersezione parziale del confine: da rivedere
    }
    return { annotations: kept, orphans };
  }
  function shift(a, d) { return Object.assign({}, a, { start: a.start + d, end: a.end + d }); }

  /* --- Validazione/normalizzazione di un documento caricato ----------------*/
  function normalizeDoc(raw) {
    if (!raw || typeof raw !== 'object') throw new Error('Documento non valido.');
    const d = newDoc();
    d.schema = raw.schema || SCHEMA_VERSION;
    d.text = typeof raw.text === 'string' ? raw.text : '';
    if (raw.meta && typeof raw.meta === 'object') {
      d.meta = Object.assign(d.meta, raw.meta);
      if (!SCRIPTS[d.meta.script]) d.meta.script = 'other';
    }
    const len = d.text.length;
    d.annotations = Array.isArray(raw.annotations) ? raw.annotations.map((a, i) => {
      const hasPlaceObj = a.place && typeof a.place === 'object';
      const isPlace = a.type === 'place' || a.category === 'luogo' || hasPlaceObj;
      const category = isPlace ? 'luogo'
        : (CATEGORIES[a.category] ? a.category : 'nota');
      return {
      id: a.id || uid(),
      start: clampOffset(a.start, len),
      end: clampOffset(a.end, len),
      type: isPlace ? 'place' : 'note',
      category: category,
      note: typeof a.note === 'string' ? a.note : '',
      tags: Array.isArray(a.tags) ? a.tags.filter(t => typeof t === 'string') : [],
      color: a.color || colorForCategory(category) || colorFor(i),
      place: hasPlaceObj ? {
        name: a.place.name || '',
        lat: (a.place.lat != null ? Number(a.place.lat) : null),
        lon: (a.place.lon != null ? Number(a.place.lon) : null),
        source: a.place.source || 'manual',
        detail: a.place.detail || ''
      } : null
      };
    }).filter(a => a.end > a.start) : [];
    return d;
  }

  /* --- Riferimenti riga/colonna (per etichette leggibili "r. N, col. A–B") --
   * Calcolati in code point (caratteri percepiti), non in unità UTF-16, così
   * un segno Lineare B conta 1 colonna e non 2. */
  function lineColOf(text, offset) {
    text = text || '';
    offset = Math.max(0, Math.min(Math.round(offset || 0), text.length));
    const before = text.slice(0, offset).split('\n');
    return { line: before.length, col: Array.from(before[before.length - 1]).length + 1 };
  }
  function refLabel(text, start, end) {
    const a = lineColOf(text, start);
    let b;
    if (end <= start) b = a;
    else {
      const e = lineColOf(text, end);           // posizione esclusiva
      if (e.col > 1) b = { line: e.line, col: e.col - 1 };
      else b = lineColOf(text, end - 1);        // end a inizio riga: usa il \n precedente
    }
    const R = a.line === b.line ? ('r. ' + a.line) : ('r. ' + a.line + '\u2013' + b.line);
    const C = a.col === b.col ? ('col. ' + a.col) : ('col. ' + a.col + '\u2013' + b.col);
    return R + ', ' + C;
  }
  function docStats(doc) {
    const text = (doc && doc.text) || '';
    const anns = (doc && doc.annotations) || [];
    const luoghi = anns.filter(a => a.type === 'place').length;
    return {
      righe: text.length ? text.split('\n').length : 0,
      token: (text.match(/\S+/g) || []).length,
      annotazioni: anns.length,
      note: anns.length - luoghi,
      luoghi: luoghi
    };
  }

  /* --- Export TEI-like -----------------------------------------------------
   * Il testo esatto è conservato in <ab xml:space="preserve"> così che gli
   * offset char= combacino byte-per-byte; le annotazioni vivono in <standOff>.
   * Compatibile con il re-import (fromTEI) per un round-trip fedele. */
  function toTEI(doc) {
    const m = doc.meta || {};
    const scr = SCRIPTS[m.script] || SCRIPTS.other;
    const anns = doc.annotations || [];
    const L = [];
    L.push('<?xml version="1.0" encoding="UTF-8"?>');
    L.push('<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:lang="' + escapeXml(scr.tei) + '">');
    L.push('  <teiHeader>');
    L.push('    <fileDesc>');
    L.push('      <titleStmt>');
    L.push('        <title>' + escapeXml(m.title || 'Testo annotato') + '</title>');
    if (m.author) L.push('        <author>' + escapeXml(m.author) + '</author>');
    L.push('      </titleStmt>');
    L.push('      <publicationStmt><p>Prodotto con Stele (annotatore stand-off per testi storici).</p></publicationStmt>');
    L.push('      <sourceDesc><p>' + escapeXml(m.description || 'Nato digitale.') + '</p></sourceDesc>');
    L.push('    </fileDesc>');
    L.push('    <profileDesc><langUsage>');
    L.push('      <language ident="' + escapeXml(scr.tei) + '">' + escapeXml(scr.label) + '</language>');
    L.push('    </langUsage></profileDesc>');
    L.push('  </teiHeader>');
    L.push('  <standOff>');
    L.push('    <listAnnotation>');
    for (const a of anns) {
      const sub = (doc.text || '').slice(a.start, a.end);
      const cat = categoryOf(a);
      L.push('      <annotation xml:id="' + escapeXml(a.id) + '" type="' + escapeXml(cat) + '" target="#char=' + a.start + ',' + a.end + '">');
      if (a.color) L.push('        <label type="color">' + escapeXml(a.color) + '</label>');
      L.push('        <quote>' + escapeXml(sub) + '</quote>');
      if (a.note) L.push('        <note>' + escapeXml(a.note) + '</note>');
      (a.tags || []).forEach(t => L.push('        <term>' + escapeXml(t) + '</term>'));
      if (a.type === 'place' && a.place) {
        L.push('        <placeName>');
        if (a.place.name) L.push('          <name>' + escapeXml(a.place.name) + '</name>');
        if (a.place.lat != null && a.place.lon != null)
          L.push('          <location><geo>' + a.place.lat + ' ' + a.place.lon + '</geo></location>');
        if (a.place.source) L.push('          <label type="source">' + escapeXml(a.place.source) + '</label>');
        L.push('        </placeName>');
      }
      L.push('      </annotation>');
    }
    L.push('    </listAnnotation>');
    L.push('  </standOff>');
    L.push('  <text><body>');
    L.push('    <ab xml:space="preserve" xml:id="txt">' + escapeXml(doc.text || '') + '</ab>');
    L.push('  </body></text>');
    L.push('</TEI>');
    return L.join('\n');
  }

  /* --- Import da TEI (prodotto da toTEI). DOMParserImpl opzionale per Node --*/
  function fromTEI(xml, DOMParserImpl) {
    const DP = DOMParserImpl || (typeof DOMParser !== 'undefined' ? DOMParser : null);
    if (!DP) throw new Error('DOMParser non disponibile.');
    const dom = new DP().parseFromString(xml, 'application/xml');
    const err = dom.getElementsByTagName('parsererror');
    if (err && err.length) throw new Error('XML malformato.');

    const first = (parent, tag) => {
      const els = parent.getElementsByTagName(tag);
      return els && els.length ? els[0] : null;
    };
    const txtEl = first(dom, 'ab');
    const text = txtEl ? (txtEl.textContent || '') : '';
    const d = newDoc();
    d.text = text;

    const titleEl = first(dom, 'title'); if (titleEl) d.meta.title = titleEl.textContent.trim();
    const authEl = first(dom, 'author'); if (authEl) d.meta.author = authEl.textContent.trim();
    const langEl = first(dom, 'language');
    if (langEl) {
      const ident = langEl.getAttribute('ident');
      for (const k in SCRIPTS) if (SCRIPTS[k].tei === ident) d.meta.script = k;
    }
    const srcEl = first(dom, 'sourceDesc'); if (srcEl) d.meta.description = srcEl.textContent.trim();

    const annEls = dom.getElementsByTagName('annotation');
    const out = [];
    for (let i = 0; i < annEls.length; i++) {
      const el = annEls[i];
      const target = el.getAttribute('target') || '';
      const mm = target.match(/#char=(\d+),(\d+)/);
      if (!mm) continue;
      const typeAttr = el.getAttribute('type') || '';
      const hasPlace = !!first(el, 'placeName');
      const isPlace = typeAttr === 'place' || typeAttr === 'luogo' || hasPlace;
      const type = isPlace ? 'place' : 'note';
      const category = isPlace ? 'luogo' : (CATEGORIES[typeAttr] ? typeAttr : 'nota');
      const noteEl = first(el, 'note');
      const labels = el.getElementsByTagName('label');
      let color = null, source = 'manual';
      for (let j = 0; j < labels.length; j++) {
        const lt = labels[j].getAttribute('type');
        if (lt === 'color') color = labels[j].textContent.trim();
        if (lt === 'source') source = labels[j].textContent.trim();
      }
      const terms = el.getElementsByTagName('term');
      const tags = [];
      for (let j = 0; j < terms.length; j++) tags.push(terms[j].textContent.trim());
      let place = null;
      if (type === 'place') {
        const pn = first(el, 'placeName');
        const nameEl = pn ? first(pn, 'name') : null;
        const geoEl = pn ? first(pn, 'geo') : null;
        let lat = null, lon = null;
        if (geoEl) {
          const parts = geoEl.textContent.trim().split(/\s+/);
          if (parts.length >= 2) { lat = Number(parts[0]); lon = Number(parts[1]); }
        }
        place = { name: nameEl ? nameEl.textContent.trim() : '', lat, lon, source, detail: '' };
      }
      out.push({
        id: el.getAttribute('xml:id') || uid(),
        start: Number(mm[1]), end: Number(mm[2]),
        type, category, note: noteEl ? noteEl.textContent : '',
        tags, color: color, place
      });
    }
    d.annotations = out;
    return normalizeDoc(d);
  }

  /* --- Geocoding (solo browser) -------------------------------------------*/
  async function geocodeNominatim(query) {
    const url = 'https://nominatim.openstreetmap.org/search?format=jsonv2&limit=6&accept-language=it&q=' +
      encodeURIComponent(query);
    const r = await fetch(url, { headers: { 'Accept': 'application/json' } });
    if (!r.ok) throw new Error('Nominatim: ' + r.status);
    const data = await r.json();
    return data.map(x => ({
      name: x.display_name, lat: Number(x.lat), lon: Number(x.lon),
      detail: x.type + (x.addresstype ? ' · ' + x.addresstype : ''), source: 'nominatim'
    }));
  }
  async function geocodeGeoNames(query, username) {
    if (!username) throw new Error('Serve un username GeoNames (impostazioni).');
    const url = 'https://secure.geonames.org/searchJSON?maxRows=6&lang=it&style=FULL&q=' +
      encodeURIComponent(query) + '&username=' + encodeURIComponent(username);
    const r = await fetch(url);
    if (!r.ok) throw new Error('GeoNames: ' + r.status);
    const data = await r.json();
    if (data.status) throw new Error('GeoNames: ' + data.status.message);
    return (data.geonames || []).map(x => ({
      name: [x.name, x.adminName1, x.countryName].filter(Boolean).join(', '),
      lat: Number(x.lat), lon: Number(x.lng),
      detail: [x.fcodeName, x.population ? ('pop. ' + x.population) : ''].filter(Boolean).join(' · '),
      source: 'geonames'
    }));
  }

  function download(filename, text, mime) {
    const blob = new Blob([text], { type: (mime || 'text/plain') + ';charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click();
    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 0);
  }

  function slugify(s) {
    return (s || 'documento').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'documento';
  }

  return {
    SCHEMA_VERSION, PALETTE, SCRIPTS, colorFor,
    CATEGORIES, CATEGORY_ORDER, colorForCategory, categoryOf,
    uid, escapeHtml, escapeXml,
    newDoc, normalizeDoc, clampOffset,
    buildSegments, assignLanes, colorMapFor, renderAnnotatedHTML,
    lineColOf, refLabel, docStats,
    remapAnnotations,
    toTEI, fromTEI,
    geocodeNominatim, geocodeGeoNames,
    download, slugify
  };
});
