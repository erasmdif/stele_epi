/* ============================================================================
 * Stele — viewer.js (sola lettura)
 * ==========================================================================*/
(function () {
  'use strict';
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const STORAGE_KEY = 'stele:current:v1';
  let doc = null, map = null, markerLayer = null, currentName = '';
  let filter = null; // Set di categorie attive, null = tutte

  function toast(msg, kind) {
    const host = $('#toastHost');
    const el = document.createElement('div');
    el.className = 'toast' + (kind ? ' ' + kind : '');
    el.textContent = msg; host.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; }, 2200);
    setTimeout(() => el.remove(), 2600);
  }
  function scriptFont() { return (TA.SCRIPTS[doc.meta.script] || TA.SCRIPTS.other).font; }
  function catMeta(a) { const c = TA.categoryOf(a); return TA.CATEGORIES[c] || TA.CATEGORIES.nota; }

  function setStatus(txt, pending) {
    $('#stState').textContent = txt;
    $('#stDot').className = 'dot' + (pending ? ' pending' : '');
    $('#stFile').innerHTML = currentName ? ('File: <strong>' + TA.escapeHtml(currentName) + '</strong> <span class="sep">·</span> ') : '';
  }

  function show(d, name) {
    doc = d; currentName = name || currentName || (TA.slugify(d.meta.title) + '.json');
    $('#empty').hidden = true; $('#grid').hidden = false;
    const scr = TA.SCRIPTS[doc.meta.script] || TA.SCRIPTS.other;
    $('#docHeader').hidden = false;
    $('#vScript').textContent = scr.label;
    $('#vTitle').textContent = doc.meta.title || 'Untitled document';
    $('#vAuthor').textContent = doc.meta.author || '—';
    $('#vDesc').textContent = doc.meta.description || '—';
    filter = null;
    renderReader(); renderNotes(); renderStats();
    setStatus('Document loaded');
  }

  function renderStats() {
    const s = TA.docStats(doc);
    $('#statbar').innerHTML =
      `<span>Lines: <b>${s.righe}</b></span><span>Tokens: <b>${s.token}</b></span>` +
      `<span>Annotations: <b>${s.annotazioni}</b></span><span>Notes: <b>${s.note}</b></span>` +
      `<span>Places: <b>${s.luoghi}</b></span>`;
  }

  function renderReader() {
    const reader = $('#reader');
    reader.style.fontFamily = scriptFont();
    if (!doc.text) { reader.className = 'reader empty'; reader.innerHTML = ''; return; }
    reader.className = 'reader';
    const out = TA.renderAnnotatedHTML(doc);
    reader.style.setProperty('--maxlane', out.maxLane);
    reader.innerHTML = out.html;
    $$('#reader .seg.ann').forEach(seg => {
      seg.addEventListener('click', () => {
        const ids = (seg.getAttribute('data-anns') || '').split(' ').filter(Boolean);
        highlight(ids);
        if (ids.length) { const it = document.querySelector('.ann-item[data-id="' + ids[0] + '"]'); if (it) it.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
      });
    });
  }
  function highlight(ids) {
    $$('#reader .seg').forEach(s => s.classList.remove('hl'));
    $$('.ann-item').forEach(i => i.classList.remove('active'));
    if (!ids || !ids.length) return;
    $$('#reader .seg.ann').forEach(seg => {
      const segIds = (seg.getAttribute('data-anns') || '').split(' ');
      if (ids.some(id => segIds.indexOf(id) !== -1)) seg.classList.add('hl');
    });
    ids.forEach(id => { const it = document.querySelector('.ann-item[data-id="' + id + '"]'); if (it) it.classList.add('active'); });
  }

  function renderNotes() {
    const list = $('#annList');
    const all = doc.annotations.slice().sort((a, b) => a.start - b.start || a.end - b.end);
    const shown = all.filter(a => !filter || filter.has(TA.categoryOf(a)));
    if (!all.length) { list.innerHTML = '<div class="empty-note">This document has no notes.</div>'; return; }
    if (!shown.length) { list.innerHTML = '<div class="empty-note">No notes match the active filter.</div>'; return; }
    const numOf = {}; all.forEach((a, i) => numOf[a.id] = i + 1);
    list.innerHTML = shown.map(a => {
      const meta = catMeta(a);
      const quote = TA.escapeHtml(doc.text.slice(a.start, a.end)) || '∅';
      const ref = TA.refLabel(doc.text, a.start, a.end);
      const isPlace = a.type === 'place';
      const place = isPlace && a.place ? `<div class="place-meta">◎ ${TA.escapeHtml(a.place.name || 'place')}` +
        (a.place.lat != null ? ` · ${a.place.lat.toFixed(4)}, ${a.place.lon.toFixed(4)}` : ' · no coordinates') + `</div>` : '';
      return `<div class="ann-item" data-id="${a.id}" style="border-left-color:${meta.color}">
        <div class="row1">
          <span class="cat-dot" style="background:${meta.color}"></span>
          <span class="cat-label">Tipo: <b>${meta.label}</b></span>
          <span class="spacer" style="flex:1"></span>
          <span class="num">#${numOf[a.id]}</span>
        </div>
        <div class="row2">
          <span class="quote" style="font-family:${scriptFont()}">“${quote}”</span>
          <span class="ref">(${ref})</span>
        </div>
        ${a.note ? `<div class="note-view">${TA.escapeHtml(a.note)}</div>` : '<div class="empty-note" style="padding:2px 0">— no text —</div>'}
        <div class="row-bottom">
          <span class="pill" style="color:${meta.color};border-color:${meta.color}33;background:${meta.color}14">${meta.label}</span>
          ${(a.tags || []).map(t => '<span class="tag">' + TA.escapeHtml(t) + '</span>').join('')}
        </div>
        ${place}
      </div>`;
    }).join('');
    $$('.ann-item').forEach(item => {
      const id = item.getAttribute('data-id');
      item.addEventListener('mouseenter', () => highlight([id]));
      item.addEventListener('mouseleave', () => highlight([]));
    });
  }

  /* --- filtro e legenda ---------------------------------------------------*/
  function categoriesPresent() {
    const seen = {};
    doc.annotations.forEach(a => { const c = TA.categoryOf(a); seen[c] = (seen[c] || 0) + 1; });
    return TA.CATEGORY_ORDER.filter(c => seen[c]).map(c => ({ cat: c, count: seen[c] }));
  }
  function closeMenus() { $$('.filter-menu,.legend-menu').forEach(m => m.remove()); }
  function toggleFilter(btn) {
    if ($('.filter-menu')) { closeMenus(); return; }
    closeMenus();
    const present = categoriesPresent();
    const menu = document.createElement('div');
    menu.className = 'filter-menu';
    menu.innerHTML = present.map(p => {
      const m = TA.CATEGORIES[p.cat];
      const on = !filter || filter.has(p.cat);
      return `<label><input type="checkbox" data-cat="${p.cat}" ${on ? 'checked' : ''}>
        <span class="cat-dot" style="background:${m.color}"></span> ${m.label} <span class="num" style="margin-left:auto">${p.count}</span></label>`;
    }).join('') || '<div class="hint">No categories.</div>';
    positionMenu(menu, btn);
    menu.addEventListener('change', () => {
      const checks = Array.from(menu.querySelectorAll('input[data-cat]'));
      const active = new Set(checks.filter(c => c.checked).map(c => c.getAttribute('data-cat')));
      filter = (active.size === present.length) ? null : active;
      renderNotes();
    });
  }
  function toggleLegend(btn) {
    if ($('.legend-menu')) { closeMenus(); return; }
    closeMenus();
    const present = categoriesPresent();
    const menu = document.createElement('div');
    menu.className = 'legend-menu';
    menu.innerHTML = present.map(p => {
      const m = TA.CATEGORIES[p.cat];
      return `<div class="legend-row"><span class="cat-dot" style="background:${m.color}"></span> ${m.label}<span class="cnt">${p.count}</span></div>`;
    }).join('') +
      '<div class="legend-note">Overlapping annotations are shown as parallel underlines beneath the text.</div>';
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

  /* --- mappa --------------------------------------------------------------*/
  function ensureMap() {
    if (map || typeof L === 'undefined') return;
    map = L.map('map').setView([37.9, 23.7], 5);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(map);
    markerLayer = L.layerGroup().addTo(map);
  }
  function renderMap() {
    if (typeof L === 'undefined') { $('#map').innerHTML = '<div class="map-empty">Leaflet could not be loaded (network unavailable).</div>'; return; }
    ensureMap(); setTimeout(() => map && map.invalidateSize(), 0);
    markerLayer.clearLayers();
    const places = doc.annotations.filter(a => a.type === 'place' && a.place && a.place.lat != null && a.place.lon != null);
    $('#mapEmpty').hidden = places.length > 0;
    const pts = [];
    places.forEach(a => {
      const m = L.marker([a.place.lat, a.place.lon]).addTo(markerLayer);
      const q = TA.escapeHtml(doc.text.slice(a.start, a.end));
      m.bindPopup(`<strong style="font-family:${scriptFont()}">${q}</strong><br>${TA.escapeHtml(a.place.name || '')}` + (a.note ? '<br><em>' + TA.escapeHtml(a.note) + '</em>' : ''));
      pts.push([a.place.lat, a.place.lon]);
    });
    if (pts.length === 1) map.setView(pts[0], 8);
    else if (pts.length > 1) map.fitBounds(pts, { padding: [30, 30] });
  }
  function switchView(v) {
    $$('#viewTabs button').forEach(b => b.classList.toggle('active', b.getAttribute('data-vtab') === v));
    $('#view-notes').hidden = v !== 'notes';
    $('#view-map').hidden = v !== 'map';
    if (v === 'map') renderMap();
  }

  /* --- caricamento ---------------------------------------------------------*/
  function openFile(file) {
    const r = new FileReader();
    r.onload = () => {
      const text = String(r.result || '');
      try {
        let d;
        if (/\.xml$/i.test(file.name) || /^\s*<\?xml/.test(text) || /<TEI/.test(text)) d = TA.fromTEI(text);
        else d = TA.normalizeDoc(JSON.parse(text));
        show(d, file.name); toast('Document loaded.', 'ok');
      } catch (err) { toast('Could not read the file: ' + err.message, 'err'); }
    };
    r.readAsText(file);
  }
  function loadSession() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) { toast('No saved session.', 'warn'); return; }
      const d = TA.normalizeDoc(JSON.parse(raw));
      if (!d.text && !d.annotations.length) { toast('The session is empty.', 'warn'); return; }
      show(d, 'current session');
    } catch (e) { toast('Could not read the current session.', 'err'); }
  }
  async function loadFromUrl(url) {
    try {
      const r = await fetch(url); if (!r.ok) throw new Error(r.status);
      const text = await r.text();
      let d;
      if (/\.xml($|\?)/i.test(url) || /<TEI/.test(text)) d = TA.fromTEI(text);
      else d = TA.normalizeDoc(JSON.parse(text));
      show(d, url.split('/').pop());
    } catch (e) { toast('Could not load ' + url + ' (' + e.message + ')', 'err'); }
  }

  function bind() {
    $('#fileOpen').addEventListener('change', e => { if (e.target.files[0]) openFile(e.target.files[0]); e.target.value = ''; });
    $('#btnSession').addEventListener('click', loadSession);
    $('#btnFilter').addEventListener('click', e => { e.stopPropagation(); toggleFilter(e.currentTarget); });
    $('#btnLegend').addEventListener('click', e => { e.stopPropagation(); toggleLegend(e.currentTarget); });
    $$('#viewTabs button').forEach(b => b.addEventListener('click', () => switchView(b.getAttribute('data-vtab'))));
    const dz = $('#dropzone') || document.body;
    ['dragover'].forEach(ev => document.body.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('dragover'); }));
    ['dragleave', 'drop'].forEach(ev => document.body.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('dragover'); }));
    document.body.addEventListener('drop', e => { const f = e.dataTransfer.files[0]; if (f) openFile(f); });
  }
  function start() {
    bind(); setStatus('Waiting for a document');
    const params = new URLSearchParams(location.search);
    if (params.get('from') === 'session' || params.get('session') === '1') { loadSession(); return; }
    const docUrl = params.get('doc');
    if (docUrl) { loadFromUrl(docUrl); return; }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
