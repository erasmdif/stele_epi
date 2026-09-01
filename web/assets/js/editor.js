/* ============================================================================
 * Stele — editor.js
 * ==========================================================================*/
(function () {
  'use strict';
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const STORAGE_KEY = 'stele:current:v1';
  const SETTINGS_KEY = 'stele:settings:v1';

  let doc = TA.newDoc();
  let activeId = null, map = null, markerLayer = null;
  let geoEditId = null, geoResultsCache = [];
  let filter = null, currentName = '';
  let saveTimer = null, renderTimer = null;
  let settings = { geonamesUser: '' };

  /* --- util ---------------------------------------------------------------*/
  function toast(msg, kind) {
    const host = $('#toastHost');
    const el = document.createElement('div');
    el.className = 'toast' + (kind ? ' ' + kind : '');
    el.textContent = msg; host.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; }, 2400);
    setTimeout(() => el.remove(), 2800);
  }
  function scriptFont() { return (TA.SCRIPTS[doc.meta.script] || TA.SCRIPTS.other).font; }
  function catMeta(a) { const c = TA.categoryOf(a); return TA.CATEGORIES[c] || TA.CATEGORIES.nota; }
  function loadSettings() { try { const s = JSON.parse(localStorage.getItem(SETTINGS_KEY)); if (s) settings = Object.assign(settings, s); } catch (e) {} }
  function saveSettings() { try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings)); } catch (e) {} }

  function setStatus(txt, pending) {
    $('#stState').textContent = txt;
    $('#stDot').className = 'dot' + (pending ? ' pending' : '');
    $('#stFile').innerHTML = currentName ? ('File: <strong>' + TA.escapeHtml(currentName) + '</strong> <span class="sep">·</span> ') : '';
  }
  function autosave() {
    doc.meta.modified = new Date().toISOString();
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(doc)); } catch (e) {}
    const t = new Date().toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
    setStatus('Salvato ' + t, false);
  }
  function markPending() { setStatus('Modifiche non salvate…', true); }
  function scheduleSave() { markPending(); clearTimeout(saveTimer); saveTimer = setTimeout(autosave, 500); }

  /* --- scripts ------------------------------------------------------------*/
  function fillScripts() {
    $('#mScript').innerHTML = Object.keys(TA.SCRIPTS).map(k =>
      `<option value="${k}">${TA.escapeHtml(TA.SCRIPTS[k].label)}</option>`).join('');
    $('#mScript').value = doc.meta.script;
  }

  /* --- palette Lineare B --------------------------------------------------*/
  let paletteTab = 'syll';
  function renderPalette() {
    const q = $('#glyphSearch').value.trim();
    let items;
    if (paletteTab === 'ideo') items = LinearB.ideograms();
    else items = q ? LinearB.search(q) : LinearB.syllabary();
    if (paletteTab === 'ideo' && q) {
      const p = LinearB.parseCodePoint(q);
      items = items.filter(x => x.hex.toLowerCase().indexOf(q.toLowerCase().replace(/^u\+/i, '')) !== -1);
      if (p) items.unshift({ cp: p.cp, char: p.char, translit: '', label: 'U+' + p.hex, hex: p.hex });
    }
    $('#glyphGrid').innerHTML = items.slice(0, 240).map(x =>
      `<button class="glyph" data-char="${x.char}" title="U+${x.hex}${x.translit ? ' · ' + x.translit : ''}">
        <span class="g">${x.char}</span><span class="t">${x.translit || x.hex}</span></button>`).join('')
      || '<div class="hint" style="padding:8px">Nessun segno.</div>';
    $$('#glyphGrid .glyph').forEach(b => b.addEventListener('click', () => insertAtCursor(b.getAttribute('data-char'))));
  }
  function insertAtCursor(str) {
    const ta = $('#source');
    const s = ta.selectionStart, e = ta.selectionEnd;
    const before = ta.value.slice(0, s), after = ta.value.slice(e);
    applyTextChange(before + str + after);
    const pos = s + str.length;
    ta.focus(); ta.setSelectionRange(pos, pos);
    updateGutter();
  }

  /* --- gutter numeri di riga ----------------------------------------------*/
  function updateGutter() {
    const ta = $('#source');
    const n = ta.value.length ? ta.value.split('\n').length : 1;
    const g = $('#gnums');
    if (g.childElementCount !== n) {
      let html = '';
      for (let i = 1; i <= n; i++) html += '<div>' + i + '</div>';
      g.innerHTML = html;
    }
    g.style.transform = 'translateY(' + (-ta.scrollTop) + 'px)';
  }

  /* --- modifica del testo -------------------------------------------------*/
  function applyTextChange(newText) {
    const old = doc.text;
    if (newText === old) return;
    const res = TA.remapAnnotations(doc.annotations, old, newText);
    doc.text = newText;
    doc.annotations = res.annotations;
    if (res.orphans.length) {
      doc.annotations = doc.annotations.concat([]); // orphans scartate: segnalo
      toast(res.orphans.length + ' annotazione/i rimossa/e: la modifica ne attraversava il confine.', 'warn');
    }
    if ($('#source').value !== newText) $('#source').value = newText;
    scheduleRender(); scheduleSave();
  }
  function scheduleRender() { clearTimeout(renderTimer); renderTimer = setTimeout(renderAll, 90); }

  /* --- render -------------------------------------------------------------*/
  function renderAll() { renderReader(); renderStats(); renderNotes(); renderXml(); if (map) renderMap(); else renderMap(); }

  function renderStats() {
    const s = TA.docStats(doc);
    $('#statbar').innerHTML =
      `<span>Righe: <b>${s.righe}</b></span><span>Token: <b>${s.token}</b></span>` +
      `<span>Annotazioni: <b>${s.annotazioni}</b></span><span>Note: <b>${s.note}</b></span>` +
      `<span>Luoghi: <b>${s.luoghi}</b></span>`;
  }
  function renderReader() {
    const reader = $('#reader');
    reader.style.fontFamily = scriptFont();
    if (!doc.text) { reader.className = 'reader empty'; reader.innerHTML = ''; return; }
    reader.className = 'reader';
    const out = TA.renderAnnotatedHTML(doc);
    reader.style.setProperty('--maxlane', out.maxLane);
    reader.innerHTML = out.html;
    $$('#reader .seg.ann').forEach(seg => seg.addEventListener('click', () => {
      const ids = (seg.getAttribute('data-anns') || '').split(' ').filter(Boolean);
      if (ids.length) { setActive(ids[0]); }
      highlightAnns(ids);
    }));
  }
  function highlightAnns(ids) {
    $$('#reader .seg').forEach(s => s.classList.remove('hl'));
    if (!ids || !ids.length) return;
    $$('#reader .seg.ann').forEach(seg => {
      const segIds = (seg.getAttribute('data-anns') || '').split(' ');
      if (ids.some(id => segIds.indexOf(id) !== -1)) seg.classList.add('hl');
    });
  }
  function setActive(id) {
    activeId = id;
    $$('.ann-item').forEach(i => i.classList.toggle('active', i.getAttribute('data-id') === id));
    const it = document.querySelector('.ann-item[data-id="' + id + '"]');
    if (it) it.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    const a = doc.annotations.find(x => x.id === id);
    if (a) highlightAnns([id]);
  }

  function renderNotes() {
    const list = $('#annList');
    const all = doc.annotations.slice().sort((a, b) => a.start - b.start || a.end - b.end);
    const numOf = {}; all.forEach((a, i) => numOf[a.id] = i + 1);
    const shown = all.filter(a => !filter || filter.has(TA.categoryOf(a)));
    if (!all.length) { list.innerHTML = '<div class="empty-note">Nessuna annotazione. Seleziona una porzione di testo e usa i pulsanti qui a sinistra.</div>'; return; }
    if (!shown.length) { list.innerHTML = '<div class="empty-note">Nessuna nota per il filtro attivo.</div>'; return; }
    list.innerHTML = shown.map(a => {
      const meta = catMeta(a);
      const quote = TA.escapeHtml(doc.text.slice(a.start, a.end)) || '∅';
      const ref = TA.refLabel(doc.text, a.start, a.end);
      const isPlace = a.type === 'place';
      const opts = TA.CATEGORY_ORDER.map(c =>
        `<option value="${c}" ${TA.categoryOf(a) === c ? 'selected' : ''}>${TA.CATEGORIES[c].label}</option>`).join('');
      const place = isPlace ? `<div class="place-meta">${a.place && a.place.lat != null
        ? '◎ ' + TA.escapeHtml(a.place.name || 'luogo') + ' · ' + a.place.lat.toFixed(4) + ', ' + a.place.lon.toFixed(4)
        : '○ luogo senza coordinate'}</div>` : '';
      return `<div class="ann-item" data-id="${a.id}" style="border-left-color:${meta.color}">
        <div class="row1">
          <span class="cat-dot" style="background:${meta.color}"></span>
          <span class="cat-label">Tipo: <b>${meta.label}</b></span>
          <span class="num" style="margin-left:auto">#${numOf[a.id]}</span>
          <button class="kebab" data-act="del" title="Elimina">×</button>
        </div>
        <div class="row2">
          <span class="quote" style="font-family:${scriptFont()}">“${quote}”</span>
          <span class="ref">(${ref})</span>
        </div>
        <textarea data-note placeholder="Annotazione…">${TA.escapeHtml(a.note)}</textarea>
        <input type="text" data-tags class="search" style="margin-top:6px" placeholder="tag, separati, da, virgole" value="${TA.escapeHtml((a.tags || []).join(', '))}">
        <div class="row-bottom">
          <select class="cat-select" data-cat>${opts}</select>
          <button class="btn small" data-act="goto">Vai al testo</button>
          ${isPlace ? '<button class="btn small" data-act="geo">◎ Coordinate</button>' : ''}
        </div>
        ${place}
      </div>`;
    }).join('');
    wireNoteCards();
  }

  function wireNoteCards() {
    $$('.ann-item').forEach(item => {
      const id = item.getAttribute('data-id');
      const a = doc.annotations.find(x => x.id === id);
      if (!a) return;
      item.addEventListener('mouseenter', () => highlightAnns([id]));
      item.addEventListener('mouseleave', () => highlightAnns(activeId ? [activeId] : []));
      item.querySelector('[data-note]').addEventListener('input', e => { a.note = e.target.value; scheduleSave(); scheduleXml(); });
      item.querySelector('[data-tags]').addEventListener('change', e => {
        a.tags = e.target.value.split(',').map(t => t.trim()).filter(Boolean); scheduleSave(); scheduleXml();
      });
      item.querySelector('[data-cat]').addEventListener('change', e => {
        const cat = e.target.value;
        a.category = cat;
        if (cat === 'luogo') { a.type = 'place'; if (!a.place) a.place = { name: '', lat: null, lon: null, source: 'manual', detail: '' }; }
        else { a.type = 'note'; }
        a.color = TA.colorForCategory(cat);
        renderAll(); autosave();
      });
      item.querySelectorAll('[data-act]').forEach(btn => btn.addEventListener('click', () => {
        const act = btn.getAttribute('data-act');
        if (act === 'del') { doc.annotations = doc.annotations.filter(x => x.id !== id); if (activeId === id) activeId = null; renderAll(); autosave(); }
        else if (act === 'goto') { focusInSource(a); setActive(id); }
        else if (act === 'geo') openGeoModalForEdit(a);
      }));
    });
  }
  function scheduleXml() { clearTimeout(renderTimer); renderTimer = setTimeout(() => { renderXml(); renderStats(); }, 120); }

  function focusInSource(a) {
    const ta = $('#source');
    ta.focus(); ta.setSelectionRange(a.start, a.end);
    // porta in vista la riga
    const line = doc.text.slice(0, a.start).split('\n').length;
    ta.scrollTop = Math.max(0, (line - 3) * 32);
    updateGutter();
  }

  /* --- selezione & creazione ---------------------------------------------*/
  function getSelection() {
    const ta = $('#source');
    let s = ta.selectionStart, e = ta.selectionEnd;
    if (s === e) return null;
    if (s > e) { const t = s; s = e; e = t; }
    return { start: s, end: e };
  }
  function addNote(category) {
    const sel = getSelection();
    if (!sel) { toast('Seleziona prima una porzione di testo.', 'warn'); return null; }
    const cat = category || 'nota';
    const a = {
      id: TA.uid(), start: sel.start, end: sel.end,
      type: cat === 'luogo' ? 'place' : 'note', category: cat,
      note: '', tags: [], color: TA.colorForCategory(cat),
      place: cat === 'luogo' ? { name: '', lat: null, lon: null, source: 'manual', detail: '' } : null
    };
    doc.annotations.push(a);
    renderAll(); autosave(); setActive(a.id);
    return a;
  }
  function addPlace() {
    const a = addNote('luogo');
    if (a) openGeoModalForEdit(a);
  }

  /* --- geocoding ----------------------------------------------------------*/
  function openGeoModalForEdit(a) {
    geoEditId = a.id;
    const quote = doc.text.slice(a.start, a.end);
    $('#geoQuote').textContent = quote;
    $('#geoQuery').value = (a.place && a.place.name) || quote.replace(/-/g, '');
    $('#geoProvider').value = settings.geonamesUser ? 'nominatim' : 'nominatim';
    $('#geoResults').innerHTML = ''; $('#geoConfirm').disabled = true; geoResultsCache = [];
    if (a.place && a.place.lat != null) { $('#geoLat').value = a.place.lat; $('#geoLon').value = a.place.lon; $('#geoName').value = a.place.name || ''; }
    else { $('#geoLat').value = ''; $('#geoLon').value = ''; $('#geoName').value = ''; }
    updateProviderUI();
    $('#geoModal').classList.add('open');
  }
  function updateProviderUI() {
    const p = $('#geoProvider').value;
    $('#manualCoords').style.display = p === 'manual' ? 'block' : 'none';
    $('#geoSearchBtn').style.display = p === 'manual' ? 'none' : 'inline-flex';
    if (p === 'manual') validateManual();
  }
  function validateManual() {
    const lat = parseFloat($('#geoLat').value), lon = parseFloat($('#geoLon').value);
    $('#geoConfirm').disabled = !(isFinite(lat) && isFinite(lon));
  }
  async function doGeoSearch() {
    const p = $('#geoProvider').value, q = $('#geoQuery').value.trim();
    if (!q) { toast('Inserisci un testo da cercare.', 'warn'); return; }
    $('#geoResults').innerHTML = '<div class="hint">Ricerca in corso…</div>';
    try {
      const res = p === 'geonames' ? await TA.geocodeGeoNames(q, settings.geonamesUser) : await TA.geocodeNominatim(q);
      geoResultsCache = res;
      if (!res.length) { $('#geoResults').innerHTML = '<div class="hint">Nessun risultato.</div>'; return; }
      $('#geoResults').innerHTML = res.map((r, i) =>
        `<button class="btn geo-item" data-i="${i}"><span class="g-name">${TA.escapeHtml(r.name)}</span><br>
          <span class="g-meta">${r.lat.toFixed(4)}, ${r.lon.toFixed(4)}${r.detail ? ' · ' + TA.escapeHtml(r.detail) : ''}</span></button>`).join('');
      $$('#geoResults .geo-item').forEach(b => b.addEventListener('click', () => {
        $$('#geoResults .geo-item').forEach(x => x.classList.remove('primary'));
        b.classList.add('primary'); $('#geoConfirm').disabled = false;
        $('#geoConfirm').setAttribute('data-i', b.getAttribute('data-i'));
      }));
    } catch (err) { $('#geoResults').innerHTML = '<div class="hint" style="color:var(--danger)">' + TA.escapeHtml(err.message) + '</div>'; }
  }
  function confirmGeo() {
    const a = doc.annotations.find(x => x.id === geoEditId);
    if (!a) { $('#geoModal').classList.remove('open'); return; }
    const p = $('#geoProvider').value;
    let place;
    if (p === 'manual') {
      const lat = parseFloat($('#geoLat').value), lon = parseFloat($('#geoLon').value);
      if (!(isFinite(lat) && isFinite(lon))) { toast('Coordinate non valide.', 'err'); return; }
      place = { name: $('#geoName').value.trim() || doc.text.slice(a.start, a.end), lat, lon, source: 'manual', detail: '' };
    } else {
      const i = Number($('#geoConfirm').getAttribute('data-i'));
      const r = geoResultsCache[i]; if (!r) { toast('Scegli un risultato.', 'warn'); return; }
      place = { name: r.name, lat: r.lat, lon: r.lon, source: r.source, detail: r.detail || '' };
    }
    a.type = 'place'; a.category = 'luogo'; a.color = TA.colorForCategory('luogo'); a.place = place;
    $('#geoModal').classList.remove('open');
    renderAll(); autosave(); toast('Coordinate assegnate.', 'ok');
  }

  /* --- mappa --------------------------------------------------------------*/
  function ensureMap() {
    if (map || typeof L === 'undefined') return;
    map = L.map('map').setView([37.9, 23.7], 5);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(map);
    markerLayer = L.layerGroup().addTo(map);
  }
  function renderMap() {
    if (typeof L === 'undefined') return;
    ensureMap(); setTimeout(() => map && map.invalidateSize(), 0);
    markerLayer.clearLayers();
    const places = doc.annotations.filter(a => a.type === 'place' && a.place && a.place.lat != null && a.place.lon != null);
    $('#mapEmpty').hidden = places.length > 0;
    $('#map').style.display = places.length ? 'block' : 'none';
    const pts = [];
    places.forEach(a => {
      const m = L.marker([a.place.lat, a.place.lon]).addTo(markerLayer);
      const q = TA.escapeHtml(doc.text.slice(a.start, a.end));
      m.bindPopup(`<strong style="font-family:${scriptFont()}">${q}</strong><br>${TA.escapeHtml(a.place.name || '')}`);
      m.on('click', () => setActive(a.id));
      pts.push([a.place.lat, a.place.lon]);
    });
    if (pts.length === 1) map.setView(pts[0], 8);
    else if (pts.length > 1) map.fitBounds(pts, { padding: [24, 24] });
  }

  /* --- TEI preview --------------------------------------------------------*/
  function renderXml() { $('#xmlOut').textContent = TA.toTEI(doc); }

  /* --- filtro & legenda ---------------------------------------------------*/
  function categoriesPresent() {
    const seen = {}; doc.annotations.forEach(a => { const c = TA.categoryOf(a); seen[c] = (seen[c] || 0) + 1; });
    return TA.CATEGORY_ORDER.filter(c => seen[c]).map(c => ({ cat: c, count: seen[c] }));
  }
  function closeMenus() { $$('.filter-menu,.legend-menu').forEach(m => m.remove()); }
  function toggleFilter(btn) {
    if ($('.filter-menu')) { closeMenus(); return; } closeMenus();
    const present = categoriesPresent();
    const menu = document.createElement('div'); menu.className = 'filter-menu';
    menu.innerHTML = present.map(p => { const m = TA.CATEGORIES[p.cat]; const on = !filter || filter.has(p.cat);
      return `<label><input type="checkbox" data-cat="${p.cat}" ${on ? 'checked' : ''}>
        <span class="cat-dot" style="background:${m.color}"></span> ${m.label} <span class="num" style="margin-left:auto">${p.count}</span></label>`;
    }).join('') || '<div class="hint">Nessuna categoria.</div>';
    positionMenu(menu, btn);
    menu.addEventListener('change', () => {
      const checks = Array.from(menu.querySelectorAll('input[data-cat]'));
      const active = new Set(checks.filter(c => c.checked).map(c => c.getAttribute('data-cat')));
      filter = (active.size === present.length) ? null : active; renderNotes();
    });
  }
  function toggleLegend(btn) {
    if ($('.legend-menu')) { closeMenus(); return; } closeMenus();
    const present = categoriesPresent();
    const menu = document.createElement('div'); menu.className = 'legend-menu';
    menu.innerHTML = TA.CATEGORY_ORDER.map(c => { const m = TA.CATEGORIES[c]; const f = present.find(p => p.cat === c);
      return `<div class="legend-row"><span class="cat-dot" style="background:${m.color}"></span> ${m.label}<span class="cnt">${f ? f.count : 0}</span></div>`;
    }).join('') + '<div class="legend-note">Le annotazioni sovrapposte corrono come underline paralleli sotto al testo.</div>';
    positionMenu(menu, btn);
  }
  function positionMenu(menu, btn) {
    document.body.appendChild(menu);
    const r = btn.getBoundingClientRect();
    menu.style.top = (window.scrollY + r.bottom + 6) + 'px';
    menu.style.left = Math.max(8, window.scrollX + r.right - menu.offsetWidth) + 'px';
    setTimeout(() => document.addEventListener('click', function h(e) {
      if (!menu.contains(e.target) && e.target !== btn) { menu.remove(); document.removeEventListener('click', h); }
    }), 0);
  }

  /* --- file ---------------------------------------------------------------*/
  function loadDocIntoUI(d, name) {
    doc = d; activeId = null; filter = null; currentName = name || currentName;
    $('#mTitle').value = d.meta.title || '';
    $('#mAuthor').value = d.meta.author || '';
    fillScripts();
    $('#source').value = d.text || '';
    updateGutter(); renderAll(); autosave();
  }
  function openFile(file) {
    const r = new FileReader();
    r.onload = () => {
      const text = String(r.result || '');
      try {
        let d;
        if (/\.xml$/i.test(file.name) || /^\s*<\?xml/.test(text) || /<TEI/.test(text)) d = TA.fromTEI(text);
        else d = TA.normalizeDoc(JSON.parse(text));
        loadDocIntoUI(d, file.name); toast('Documento caricato.', 'ok');
      } catch (err) { toast('File non leggibile: ' + err.message, 'err'); }
    };
    r.readAsText(file);
  }
  function newDoc() {
    if (doc.text || doc.annotations.length) { if (!confirm('Creare un nuovo documento? Le modifiche non esportate andranno perse.')) return; }
    doc = TA.newDoc(); activeId = null; currentName = '';
    $('#mTitle').value = ''; $('#mAuthor').value = ''; $('#source').value = '';
    fillScripts(); updateGutter(); renderAll(); autosave(); setStatus('Nuovo documento');
  }
  function currentFilename(ext) {
    const base = TA.slugify(doc.meta.title || (currentName ? currentName.replace(/\.[^.]+$/, '') : 'documento'));
    return base + ext;
  }
  function saveJson() {
    doc.meta.title = $('#mTitle').value; doc.meta.author = $('#mAuthor').value;
    const name = currentFilename('.json');
    TA.download(name, JSON.stringify(doc, null, 2), 'application/json');
    currentName = name; setStatus('Esportato ' + name); autosave();
  }
  function exportTei() {
    doc.meta.title = $('#mTitle').value; doc.meta.author = $('#mAuthor').value;
    const name = currentFilename('.tei.xml');
    TA.download(name, TA.toTEI(doc), 'application/xml');
    toast('TEI esportato.', 'ok');
  }

  /* --- bind ---------------------------------------------------------------*/
  function bind() {
    // meta
    $('#mTitle').addEventListener('input', e => { doc.meta.title = e.target.value; scheduleSave(); scheduleXml(); });
    $('#mAuthor').addEventListener('input', e => { doc.meta.author = e.target.value; scheduleSave(); scheduleXml(); });
    $('#mScript').addEventListener('change', e => { doc.meta.script = e.target.value; renderReader(); renderNotes(); renderXml(); scheduleSave(); });

    // source
    const ta = $('#source');
    ta.addEventListener('input', () => { applyTextChange(ta.value); updateGutter(); });
    ta.addEventListener('scroll', updateGutter);
    ta.addEventListener('keydown', e => { if (e.key === 'Tab') { e.preventDefault(); insertAtCursor('\t'); } });

    // palette
    $$('#paletteTabs button').forEach(b => b.addEventListener('click', () => {
      paletteTab = b.getAttribute('data-ptab');
      $$('#paletteTabs button').forEach(x => x.classList.toggle('active', x === b));
      renderPalette();
    }));
    $('#glyphSearch').addEventListener('input', renderPalette);
    $('#cpInsert').addEventListener('click', () => {
      const p = LinearB.parseCodePoint($('#cpInput').value);
      if (!p) { toast('Code point non valido (usa U+10000–U+100FF).', 'warn'); return; }
      insertAtCursor(p.char); $('#cpInput').value = '';
    });

    // creazione
    $('#btnAddNote').addEventListener('click', () => addNote('nota'));
    $('#btnNewNote').addEventListener('click', () => addNote('nota'));
    $('#btnAddPlace').addEventListener('click', addPlace);

    // filtro / legenda
    $('#btnFilter').addEventListener('click', e => { e.stopPropagation(); toggleFilter(e.currentTarget); });
    $('#btnLegend').addEventListener('click', e => { e.stopPropagation(); toggleLegend(e.currentTarget); });

    // xml
    $('#btnCopyXml').addEventListener('click', () => {
      navigator.clipboard.writeText(TA.toTEI(doc)).then(() => toast('XML copiato.', 'ok'), () => toast('Copia non riuscita.', 'err'));
    });

    // file
    $('#fileOpen').addEventListener('change', e => { if (e.target.files[0]) openFile(e.target.files[0]); e.target.value = ''; });
    $('#btnNew').addEventListener('click', newDoc);
    $('#btnSaveJson').addEventListener('click', saveJson);
    $('#btnExportTei').addEventListener('click', exportTei);
    $('#btnView').addEventListener('click', () => autosave());

    // drag&drop
    ta.addEventListener('dragover', e => { e.preventDefault(); ta.classList.add('dragover'); });
    ta.addEventListener('dragleave', () => ta.classList.remove('dragover'));
    document.body.addEventListener('drop', e => { e.preventDefault(); ta.classList.remove('dragover'); const f = e.dataTransfer.files[0]; if (f) openFile(f); });
    document.body.addEventListener('dragover', e => e.preventDefault());

    // geocoding modal
    $('#geoProvider').addEventListener('change', updateProviderUI);
    $('#geoSearchBtn').addEventListener('click', doGeoSearch);
    $('#geoLat').addEventListener('input', validateManual);
    $('#geoLon').addEventListener('input', validateManual);
    $('#geoConfirm').addEventListener('click', confirmGeo);
    $('#geoClose').addEventListener('click', () => $('#geoModal').classList.remove('open'));
    $('#geoCancel').addEventListener('click', () => $('#geoModal').classList.remove('open'));

    // settings modal
    $('#btnSettings').addEventListener('click', () => { $('#geonamesUser').value = settings.geonamesUser || ''; $('#settingsModal').classList.add('open'); });
    $('#setClose').addEventListener('click', () => $('#settingsModal').classList.remove('open'));
    $('#setSave').addEventListener('click', () => { settings.geonamesUser = $('#geonamesUser').value.trim(); saveSettings(); $('#settingsModal').classList.remove('open'); toast('Impostazioni salvate.', 'ok'); });

    document.addEventListener('keydown', e => { if (e.key === 'Escape') $$('.modal-back.open').forEach(m => m.classList.remove('open')); });
  }

  function restore() {
    try { const raw = localStorage.getItem(STORAGE_KEY); if (raw) { const d = TA.normalizeDoc(JSON.parse(raw)); if (d.text || d.annotations.length) return d; } } catch (e) {}
    return null;
  }
  function start() {
    loadSettings(); fillScripts(); bind(); renderPalette();
    const restored = restore();
    if (restored) { loadDocIntoUI(restored, currentName); setStatus('Sessione ripristinata'); }
    else { updateGutter(); renderAll(); setStatus('Nuovo documento'); }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
