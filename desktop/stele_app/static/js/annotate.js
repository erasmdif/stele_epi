/* Workbench di annotazione — stand-off, offset in CODE POINT, editing completo,
   con picker unificato "cerca-o-crea" e ricerca globale del dizionario. */
(function () {
  'use strict';
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));

  const CAT_COLOR = {
    semantic: '#2f7d5b', linguistic: '#2f7d5b', named_entity: '#7a4fb0',
    editorial: '#c07b1f', palaeographic: '#b5561f', formulaic: '#2a6f9a',
    critical: '#b23434', other: '#6b6559'
  };
  const TYPE_COLOR = { person: '#7a4fb0', deity: '#7a4fb0', place: '#2a6f9a',
    formula: '#2f7d5b', concept: '#c07b1f' };
  const ANN_TYPES = ['semantic', 'linguistic', 'named_entity', 'editorial', 'palaeographic', 'formulaic', 'critical', 'other'];
  const STATUSES = ['accepted', 'proposed', 'rejected', 'superseded'];
  const CERTS = [['', '—'], ['certain', 'Certain'], ['probable', 'Probable'], ['possible', 'Possible'], ['uncertain', 'Uncertain'], ['unknown', 'Unknown']];
  const TERM_TYPES = ['person', 'deity', 'place', 'institution', 'ethnonym', 'formula', 'abbreviation', 'concept', 'quantity', 'event', 'title', 'office', 'object_concept', 'other'];
  const REL_LABELS = { IS_A: 'is a type of', PART_OF: 'is part of', ASSOCIATED_WITH: 'is associated with',
    EQUIVALENT_TO: 'is equivalent to', DERIVED_FROM: 'is derived from', RELATED_TO: 'is related to' };
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  let CP = [], ANNS = [], VERSION = null, RELTYPES = [], activeAi = null, teiTimer = null;

  /* ---------- util ---------- */
  function toast(msg, kind) {
    let host = $('#toastHost');
    if (!host) { host = document.createElement('div'); host.id = 'toastHost'; host.className = 'toast-host'; document.body.appendChild(host); }
    const el = document.createElement('div');
    el.className = 'toast' + (kind ? ' ' + kind : ''); el.textContent = msg; host.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; }, 2200);
    setTimeout(() => el.remove(), 2600);
  }
  async function api(method, url, body) {
    const opt = { method, headers: {} };
    if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    const r = await fetch(url, opt);
    let data = null; try { data = await r.json(); } catch (e) {}
    if (!r.ok) throw new Error((data && data.error) || ('HTTP ' + r.status));
    return data;
  }
  function colorOf(a) {
    const t = (a.terms || [])[0];
    if (t && TYPE_COLOR[t.term_type]) return TYPE_COLOR[t.term_type];
    return CAT_COLOR[a.annotation_type] || '#6b6559';
  }
  function lineCol(idx) {
    let line = 1, col = 1;
    for (let i = 0; i < idx && i < CP.length; i++) { if (CP[i] === '\n') { line++; col = 1; } else col++; }
    return { line, col };
  }
  function refLabel(s, e) {
    const a = lineCol(s), b = lineCol(Math.max(s, e - 1));
    const R = a.line === b.line ? 'r. ' + a.line : 'r. ' + a.line + '–' + b.line;
    const C = a.col === b.col ? 'col. ' + a.col : 'col. ' + a.col + '–' + b.col;
    return R + ', ' + C;
  }
  const quoteOf = (s, e) => CP.slice(s, e).join('');

  /* ============================================================================
     TermPicker — componente unificato "cerca o crea"
     Uso: TermPicker.open(hostEl, {onPick(termObj), placeholder, defaultType, excludeId})
     Se l'utente scrive un'etichetta che NON esiste, mostra sempre in cima
     "Crea «X» come [tipo]" — la creazione è primo cittadino, non nascosta.
     ============================================================================ */
  const TermPicker = {
    open(host, opts) {
      this.close();
      const menu = document.createElement('div'); menu.className = 'term-menu';
      menu.style.position = 'absolute'; menu.style.top = 'calc(100% + 4px)'; menu.style.left = '0';
      menu.innerHTML = `<input placeholder="${esc(opts.placeholder || 'search or type to create…')}">
        <div class="res"></div>`;
      host.style.position = 'relative';
      host.appendChild(menu);
      const input = menu.querySelector('input'), res = menu.querySelector('.res');
      input.focus();
      let t = null;
      const defaultType = opts.defaultType || 'other';
      const excludeId = opts.excludeId || null;

      async function search() {
        const val = input.value.trim();
        let list = [];
        try { list = await api('GET', '/api/text-terms?q=' + encodeURIComponent(val)); } catch (e) {}
        if (excludeId) list = list.filter(x => x.id !== excludeId);
        let html = '';
        if (val) {
          const exact = list.some(x => x.preferred_label.toLowerCase() === val.toLowerCase());
          if (!exact) {
            html += `<div class="primary-create" data-role="create">
              <span class="plus">＋</span>
              <span>Create <b>“${esc(val)}”</b> as</span>
              <select>${TERM_TYPES.map(t => `<option ${t === defaultType ? 'selected' : ''}>${t}</option>`).join('')}</select>
            </div>`;
          }
        }
        html += list.slice(0, 40).map(x =>
          `<button data-id="${x.id}" data-type="${x.term_type}" data-label="${esc(x.preferred_label)}">
             ${esc(x.preferred_label)} <span class="tag">${x.term_type}</span>
           </button>`).join('');
        if (!list.length && !val) html += '<div class="muted" style="font-size:12px;padding:4px">Type to search or create.</div>';
        res.innerHTML = html;

        const createEl = res.querySelector('[data-role="create"]');
        if (createEl) createEl.addEventListener('click', async ev => {
          if (ev.target.tagName === 'SELECT') return;
          try {
            const type = createEl.querySelector('select').value;
            const created = await api('POST', '/api/text-terms',
              { term_type: type, preferred_label: val });
            await opts.onPick({ id: created.id, preferred_label: created.preferred_label,
              term_type: created.term_type, created: true });
            TermPicker.close();
          } catch (e) { toast(e.message, 'err'); }
        });
        res.querySelectorAll('button[data-id]').forEach(b => b.addEventListener('click', async () => {
          try {
            await opts.onPick({ id: +b.dataset.id, preferred_label: b.dataset.label,
              term_type: b.dataset.type, created: false });
            TermPicker.close();
          } catch (e) { toast(e.message, 'err'); }
        }));
      }
      input.addEventListener('input', () => { clearTimeout(t); t = setTimeout(search, 160); });
      search();
      setTimeout(() => document.addEventListener('click', TermPicker._outside), 0);
      TermPicker._menu = menu; TermPicker._host = host;
    },
    close() {
      $$('.term-menu').forEach(m => m.remove());
      document.removeEventListener('click', TermPicker._outside);
      TermPicker._menu = null; TermPicker._host = null;
    },
    _outside(e) {
      if (TermPicker._menu && !TermPicker._menu.contains(e.target)) TermPicker.close();
    }
  };

  /* ---------- render testo ---------- */
  function assignLanes(items) {
    const sorted = items.slice().sort((x, y) => x.start - y.start || y.end - x.end);
    const laneEnds = [], lane = {};
    for (const a of sorted) {
      let placed = false;
      for (let i = 0; i < laneEnds.length; i++) if (laneEnds[i] <= a.start) { lane[a.key] = i; laneEnds[i] = a.end; placed = true; break; }
      if (!placed) { lane[a.key] = laneEnds.length; laneEnds.push(a.end); }
    }
    return lane;
  }
  let PARALLEL = null;    // vista parallela caricata da /api/documents/<id>/parallel-view
  let ACTIVE_TYPES = null; // set di version_type attivi (tab attivate)

  function render() {
    if (!PARALLEL) return;
    const primVid = PARALLEL.primary.id;
    // annotazioni "flat" per la primary (unica versione annotabile)
    const flat = [];
    ANNS.forEach((a, ai) => (a.spans || []).forEach((s, si) => flat.push({
      key: ai + '_' + si, ai, start: s.start_position, end: s.end_position, color: colorOf(a)
    })));
    const lane = assignLanes(flat);
    let maxLane = 0; Object.values(lane).forEach(l => { if (l > maxLane) maxLane = l; });

    // bounds della primary per riga (per capire quali span cadono in questa riga)
    const primContent = PARALLEL.rows.map(r => (r.cells.find(c => c.is_primary_version) || {}).text || '').join('\n');
    const primCP = Array.from(primContent);
    // ricalcolo CP globale (serve al selezione→offset)
    CP = primCP;

    const container = $('#parallelReader');
    // strip di tab
    renderTabs();
    // costruisco per-riga cell HTML
    let lineStartCP = 0;
    const rowsHtml = PARALLEL.rows.map((row, ri) => {
      const primCell = row.cells.find(c => c.is_primary_version);
      const primText = primCell ? primCell.text : '';
      const primLineLen = Array.from(primText).length;
      const lineEndCP = lineStartCP + primLineLen;
      // segmenti dentro questa riga
      const inRow = flat.filter(f => f.start < lineEndCP && f.end > lineStartCP);
      const primCellHtml = renderPrimaryCell(primCell, lineStartCP, lineEndCP, primText, inRow, lane, maxLane);
      // celle parallele
      const parallelCellsHtml = row.cells.filter(c => !c.is_primary_version && ACTIVE_TYPES.has(c.version_type))
        .map(c => `
          <div class="p-cell parallel ${c.ann_count > 0 ? 'has-ann' : ''}">
            <div class="p-label"><span class="lang">${esc(c.language || '')}</span> ${esc(c.version_type)}</div>
            <div class="p-text">${esc(c.text || '')}</div>
            ${c.ann_count > 0 ? `<span class="p-marker" title="${c.ann_count} annotation(s) on the corresponding line of the primary version">${c.ann_count}</span>` : ''}
          </div>`).join('');
      const n = 1 + row.cells.filter(c => !c.is_primary_version && ACTIVE_TYPES.has(c.version_type)).length;
      const html = `<div class="p-row" data-row="${ri}">
        <div class="p-lno">${ri + 1}</div>
        <div class="p-cells n${Math.min(n, 4)}">${primCellHtml}${parallelCellsHtml}</div>
      </div>`;
      lineStartCP = lineEndCP + 1; // +1 per il '\n' (che non è nella riga singola ma nel content globale)
      return html;
    }).join('');
    container.innerHTML = rowsHtml;

    // click su segmenti annotati -> seleziona la card
    $$('.p-cell.primary .seg.ann').forEach(seg => seg.addEventListener('click', ev => {
      if (window.getSelection && String(window.getSelection()).length) return;
      const ais = (seg.dataset.ais || '').split(' ').filter(Boolean);
      if (ais.length) selectCard(+ais[0]);
    }));
    renderStats(flat.length);
  }

  function renderPrimaryCell(cell, lineStart, lineEnd, text, coveringInRow, lane, maxLane) {
    // converto le annotazioni globali in coordinate locali della riga
    const local = coveringInRow.map(f => ({
      key: f.key, ai: f.ai, color: f.color,
      start: Math.max(lineStart, f.start) - lineStart,
      end: Math.min(lineEnd, f.end) - lineStart,
      globalStart: f.start
    }));
    const cp = Array.from(text);
    if (!local.length) {
      return `<div class="p-cell primary" data-vid="${cell ? cell.version_id : ''}" data-cpstart="${lineStart}">
        <div class="p-label"><span class="lang">${esc(cell ? cell.language || '' : '')}</span> ${esc(cell ? cell.version_type : '')} <span class="tag" style="font-size:9px">primary — annotatable</span></div>
        <div class="p-text" data-cpstart="${lineStart}" style="--maxlane:${maxLane}">${esc(text) || '\u200b'}</div>
      </div>`;
    }
    // boundaries locali
    const bs = new Set([0, cp.length]);
    local.forEach(f => { bs.add(f.start); bs.add(f.end); });
    const bounds = Array.from(bs).sort((a, b) => a - b);
    const pieces = [];
    for (let i = 0; i < bounds.length - 1; i++) {
      const s = bounds[i], e = bounds[i + 1]; if (e <= s) continue;
      const covering = local.filter(f => f.start <= s && f.end >= e);
      const t = esc(cp.slice(s, e).join(''));
      if (!covering.length) { pieces.push(`<span class="seg" data-cpstart="${lineStart + s}">${t}</span>`); continue; }
      const bars = covering.map(c => ({ lane: lane[c.key], color: c.color })).sort((a, b) => a.lane - b.lane);
      const img = bars.map(b => `linear-gradient(${b.color},${b.color})`).join(',');
      const size = bars.map(() => '100% 3px').join(',');
      const pos = bars.map(b => `0 calc(100% - ${b.lane * 4}px)`).join(',');
      const ais = Array.from(new Set(covering.map(c => c.ai))).join(' ');
      pieces.push(`<span class="seg ann" data-cpstart="${lineStart + s}" data-ais="${ais}" style="background-image:${img};background-size:${size};background-position:${pos};background-repeat:no-repeat">${t}</span>`);
    }
    return `<div class="p-cell primary" data-vid="${cell.version_id}" data-cpstart="${lineStart}">
      <div class="p-label"><span class="lang">${esc(cell.language || '')}</span> ${esc(cell.version_type)} <span class="tag" style="font-size:9px;background:#eef4f4;color:var(--accent-ink)">primary — annotatable</span></div>
      <div class="p-text" data-cpstart="${lineStart}" style="--maxlane:${maxLane}">${pieces.join('') || '\u200b'}</div>
    </div>`;
  }

  function renderTabs() {
    const tabs = $('#versionTabs');
    if (!PARALLEL) { tabs.innerHTML = ''; return; }
    const primT = PARALLEL.primary.version_type;
    tabs.innerHTML = PARALLEL.versions.map(v => {
      const isPrim = v.version_type === primT;
      const isActive = ACTIVE_TYPES.has(v.version_type);
      const cls = 'tab' + (isPrim ? ' primary' : '') + (isActive ? ' active' : '');
      const check = isActive ? '✓' : '○';
      return `<span class="${cls}" data-vtype="${v.version_type}" title="v${v.version_number}${v.is_current ? ' · current' : ''}${isPrim ? ' · primary (annotatable)' : ''}">
        ${isPrim ? '' : `<span>${check}</span>`} ${esc(v.version_type)}${v.language ? ` <span class="lang">(${esc(v.language)})</span>` : ''}
      </span>`;
    }).join('') + `<span class="hint">annotate the primary version; others are parallel views</span>`;
    tabs.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {
      const vt = t.dataset.vtype;
      if (vt === PARALLEL.primary.version_type) return; // la primaria è sempre attiva
      if (ACTIVE_TYPES.has(vt)) ACTIVE_TYPES.delete(vt); else ACTIVE_TYPES.add(vt);
      render();
    }));
  }
  function renderStats(nSpans) {
    const righe = CP.length ? CP.join('').split('\n').length : 0;
    const token = (CP.join('').match(/\S+/g) || []).length;
    $('#statbar').textContent = `Lines: ${righe} · Tokens: ${token} · Annotations: ${ANNS.length} · Spans: ${nSpans}`;
  }

  /* ---------- selezione -> offset ---------- */
  function offsetOf(node, off) {
    if (!node) return null;
    if (node.nodeType === 3) {
      const seg = node.parentElement && node.parentElement.closest('.seg,.p-text');
      if (!seg) return null;
      return (+seg.dataset.cpstart || 0) + Array.from(node.textContent.slice(0, off)).length;
    }
    const el = node.closest ? node.closest('.seg,.p-text') : null;
    if (el) return (+el.dataset.cpstart || 0) + (off > 0 ? Array.from(el.textContent).length : 0);
    return null;
  }
  function onMouseUp() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) { hideSelPop(); return; }
    const r = sel.getRangeAt(0);
    // consenti selezione solo dentro le celle primary
    const primCell = r.commonAncestorContainer.nodeType === 3
      ? r.commonAncestorContainer.parentElement.closest('.p-cell.primary')
      : (r.commonAncestorContainer.closest ? r.commonAncestorContainer.closest('.p-cell.primary') : null);
    if (!primCell) return;
    let a = offsetOf(sel.anchorNode, sel.anchorOffset);
    let b = offsetOf(sel.focusNode, sel.focusOffset);
    if (a == null || b == null) return;
    let start = Math.max(0, Math.min(a, b)), end = Math.min(CP.length, Math.max(a, b));
    if (end <= start) { hideSelPop(); return; }
    showSelPop(start, end, r.getBoundingClientRect());
  }
  let selPop = null;
  function hideSelPop() { if (selPop) { selPop.remove(); selPop = null; } }
  function showSelPop(start, end, rect) {
    hideSelPop();
    selPop = document.createElement('div');
    selPop.className = 'sel-pop';
    selPop.innerHTML = `
      <span class="mono" style="font-size:11px;color:var(--ink-soft)">${esc(quoteOf(start, end).slice(0,20))} · ${refLabel(start, end)}</span>
      <select title="annotation type">${ANN_TYPES.map(t => `<option value="${t}">${t}</option>`).join('')}</select>
      <button class="btn primary mini" data-act="annot">＋ Annotate</button>
      <button class="btn mini" data-act="annotWithTerm">＋ Annotate &amp; link term…</button>`;
    document.body.appendChild(selPop);
    selPop.style.top = (window.scrollY + rect.bottom + 6) + 'px';
    selPop.style.left = (window.scrollX + rect.left) + 'px';
    async function createBare() {
      const type = selPop.querySelector('select').value;
      const created = await api('POST', `/api/text-versions/${VERSION}/annotations`,
        { annotation_type: type, spans: [{ start, end }] });
      hideSelPop(); window.getSelection().removeAllRanges();
      await reload(); if (created && created.id) selectCard(indexById(created.id));
      return created.id;
    }
    selPop.querySelector('[data-act="annot"]').addEventListener('click', async () => {
      try { await createBare(); toast('Annotation created.', 'ok'); }
      catch (e) { toast(e.message, 'err'); }
    });
    selPop.querySelector('[data-act="annotWithTerm"]').addEventListener('click', async () => {
      try {
        const type = selPop.querySelector('select').value;
        const aid = await createBare();
        // apri il picker direttamente sulla nuova card
        setTimeout(() => {
          const card = document.querySelector(`.ann-item[data-id="${aid}"]`);
          if (card) {
            const btn = card.querySelector('[data-act="addterm"]');
            if (btn) btn.click();
          }
        }, 60);
      } catch (e) { toast(e.message, 'err'); }
    });
  }

  /* ---------- lista annotazioni (editabile) ---------- */
  function indexById(id) { return ANNS.findIndex(a => a.id === id); }
  function selectCard(ai) {
    activeAi = ai;
    $$('.ann-item').forEach(i => i.classList.toggle('active', +i.dataset.ai === ai));
    const el = document.querySelector(`.ann-item[data-ai="${ai}"]`);
    if (el) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    highlight([String(ai)]);
  }
  function highlight(ais) {
    $$('.p-cell.primary .seg').forEach(s => s.classList.remove('hl'));
    if (!ais || !ais.length) return;
    $$('.p-cell.primary .seg.ann').forEach(seg => {
      const segAis = (seg.dataset.ais || '').split(' ');
      if (ais.some(a => segAis.indexOf(a) !== -1)) seg.classList.add('hl');
    });
  }

  function renderList() {
    $('#annCount').textContent = ANNS.length;
    const list = $('#annList');
    if (!ANNS.length) {
      list.innerHTML = `<div class="muted" style="font-size:13px;padding:20px;text-align:center;border:1px dashed var(--line);border-radius:6px">
        <div style="font-size:22px">✎</div>
        Select a text span to create the first annotation.</div>`; return;
    }
    list.innerHTML = ANNS.map((a, ai) => {
      const sp = (a.spans || [])[0] || { start_position: 0, end_position: 0 };
      const quote = esc(quoteOf(sp.start_position, sp.end_position));
      const spanInfo = (a.spans || []).map(s => refLabel(s.start_position, s.end_position)).join(' · ');
      const terms = (a.terms || []).map(t => `
        <span class="term-chip" data-term="${t.id}" data-type="${t.term_type}" style="border-color:${TYPE_COLOR[t.term_type]||'var(--line-strong)'}">
          <a href="/vocabularies/${t.id}" style="color:inherit;text-decoration:none" title="Open dictionary record">${esc(t.preferred_label)}</a>
          <span class="tag">${t.term_type}</span>
          <button class="rm" title="Unlink">×</button>
          <span class="lineage"></span>
        </span>`).join('');
      return `<div class="ann-item" data-ai="${ai}" data-id="${a.id}" style="border-left-color:${colorOf(a)}">
        <div style="display:flex;align-items:center;gap:8px">
          <span class="q" style="font-family:var(--lb);font-size:16px">“${quote}”</span>
          <span class="spacer" style="flex:1"></span>
          <span class="ref">${spanInfo}</span>
          <button class="kebab" data-act="del" title="Delete">×</button>
        </div>
        <div class="terms" style="margin-top:8px">${terms}
          <span class="termbox"><button class="btn mini primary" data-act="addterm">＋ term</button></span>
        </div>
        <textarea data-f="note" placeholder="Textual note (optional)…" style="margin-top:8px">${esc(a.note || '')}</textarea>
        <details class="card-details">
          <summary>Technical details (type, status, certainty and spans)</summary>
          <div class="ed-row" style="margin-top:6px">
            <label style="font-size:11px;color:var(--ink-soft)">Type
              <select data-f="annotation_type">${ANN_TYPES.map(t => `<option ${t === a.annotation_type ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
            <label style="font-size:11px;color:var(--ink-soft)">Status
              <select data-f="status">${STATUSES.map(s => `<option ${s === a.status ? 'selected' : ''}>${s}</option>`).join('')}</select></label>
            <label style="font-size:11px;color:var(--ink-soft)">Certainty
              <select data-f="certainty_code">${CERTS.map(c => `<option value="${c[0]}" ${a.certainty === c[1] ? 'selected' : ''}>${c[1]}</option>`).join('')}</select></label>
            <button class="link-btn" data-act="addspan" title="Add the selection as another span for a discontinuous annotation">＋ span</button>
          </div>
        </details>
      </div>`;
    }).join('');
    wireCards();
  }

  function wireCards() {
    $$('.ann-item').forEach(item => {
      const ai = +item.dataset.ai, id = +item.dataset.id, a = ANNS[ai];
      item.addEventListener('mouseenter', () => highlight([String(ai)]));
      item.addEventListener('mouseleave', () => highlight(activeAi != null ? [String(activeAi)] : []));
      item.querySelectorAll('[data-f]').forEach(el => {
        el.addEventListener('change', async () => {
          try { await api('PATCH', `/api/annotations/${id}`, { [el.dataset.f]: el.value }); refreshTei(); toast('Saved.', 'ok'); }
          catch (e) { toast(e.message, 'err'); }
        });
      });
      item.querySelector('[data-act="del"]').addEventListener('click', async () => {
        if (!confirm('Delete this annotation? Linked dictionary records will not be deleted.')) return;
        try { await api('DELETE', `/api/annotations/${id}`); await reload(); toast('Deleted.', 'ok'); }
        catch (e) { toast(e.message, 'err'); }
      });
      const addSpanBtn = item.querySelector('[data-act="addspan"]');
      if (addSpanBtn) addSpanBtn.addEventListener('click', async () => {
        const sel = pendingSelection();
        if (!sel) { toast('Select a text span first.', 'warn'); return; }
        const spans = (a.spans || []).map(s => ({ start: s.start_position, end: s.end_position }));
        spans.push(sel);
        try { await api('PUT', `/api/annotations/${id}/spans`, { spans }); await reload(); toast('Span added.', 'ok'); }
        catch (e) { toast(e.message, 'err'); }
      });
      // ＋ termine: apre il TermPicker unificato
      item.querySelector('[data-act="addterm"]').addEventListener('click', e => {
        e.stopPropagation();
        const box = e.currentTarget.parentElement;
        TermPicker.open(box, {
          placeholder: 'search or create a term to link…',
          defaultType: guessTypeFromAnnotation(a),
          onPick: async term => {
            await api('POST', `/api/annotations/${id}/terms`, { term_id: term.id, role: 'primary' });
            await reload();
            toast(term.created ? `Record "${term.preferred_label}" created and linked.` : 'Term linked.', 'ok');
          }
        });
      });
      // termini: rimuovi / lineage
      item.querySelectorAll('.term-chip').forEach(chip => {
        const tid = +chip.dataset.term;
        chip.querySelector('.rm').addEventListener('click', async ev => {
          ev.stopPropagation(); ev.preventDefault();
          try { await api('DELETE', `/api/annotations/${id}/terms/${tid}`); await reload(); }
          catch (e) { toast(e.message, 'err'); }
        });
        chip.addEventListener('click', async ev => {
          if (ev.target.closest('.rm,a')) return;
          const box = chip.querySelector('.lineage');
          if (box.textContent) { box.textContent = ''; return; }
          try {
            const d = await api('GET', `/api/vocab/text_term/${tid}/lineage`);
            const anc = (d.ancestors || []).map(x => '→ ' + x.preferred_label).join(' ');
            const neighOut = (d.neighbours || []).filter(n => n.dir === 'out' && n.rel !== 'IS_A' && n.rel !== 'PART_OF')
              .map(n => `${REL_LABELS[n.rel] || n.rel} ${n.other_label}`).join(' · ');
            box.innerHTML = (anc ? esc(anc) : '<i>no hierarchy — open the record to build one</i>') +
              (neighOut ? `<br>${esc(neighOut)}` : '');
          } catch (e) { toast(e.message, 'err'); }
        });
      });
    });
  }
  function guessTypeFromAnnotation(a) {
    // ereditarietà del tipo: nuovi record ereditano il tipo del termine principale
    // già collegato all'annotazione, se c'è; altrimenti inferisce da annotation_type
    if ((a.terms || []).length) return a.terms[0].term_type;
    if (a.annotation_type === 'named_entity') return 'person';
    if (a.annotation_type === 'editorial') return 'editorial_feature';
    if (a.annotation_type === 'formulaic') return 'formula';
    return 'other';
  }

  function pendingSelection() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return null;
    const r = sel.getRangeAt(0);
    const primCell = r.commonAncestorContainer.nodeType === 3
      ? r.commonAncestorContainer.parentElement.closest('.p-cell.primary')
      : (r.commonAncestorContainer.closest ? r.commonAncestorContainer.closest('.p-cell.primary') : null);
    if (!primCell) return null;
    let a = offsetOf(sel.anchorNode, sel.anchorOffset), b = offsetOf(sel.focusNode, sel.focusOffset);
    if (a == null || b == null) return null;
    const start = Math.max(0, Math.min(a, b)), end = Math.min(CP.length, Math.max(a, b));
    return end > start ? { start, end } : null;
  }

  /* ---------- TEI + mappa ---------- */
  function refreshTei() { clearTimeout(teiTimer); teiTimer = setTimeout(loadTei, 250); }
  async function loadTei() {
    try { const r = await fetch(`/api/text-versions/${VERSION}/tei`); $('#xmlOut').textContent = await r.text(); } catch (e) {}
  }
  let map = null, markers = null;
  function renderMap(places) {
    if (typeof L === 'undefined') return;
    if (!places.length) { $('#mapEmpty').hidden = false; $('#map').style.display = 'none'; if (map) { map.remove(); map = null; } return; }
    $('#mapEmpty').hidden = true; $('#map').style.display = 'block';
    if (!map) {
      map = L.map('map').setView([places[0].lat, places[0].lon], 6);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap' }).addTo(map);
      markers = L.layerGroup().addTo(map);
    }
    markers.clearLayers();
    const pts = [];
    places.forEach(p => { L.marker([p.lat, p.lon]).addTo(markers).bindPopup('<b>' + esc(p.label) + '</b>'); pts.push([p.lat, p.lon]); });
    if (pts.length === 1) map.setView(pts[0], 7);
    else if (pts.length > 1) map.fitBounds(pts, { padding: [25, 25] });
    setTimeout(() => map.invalidateSize(), 0);
  }

  /* ---------- ricerca globale del dizionario (Cmd/Ctrl+K) ---------- */
  function wireSearchBar() {
    const bar = $('#dictSearch');
    if (!bar) return;
    const inp = bar.querySelector('input'), res = bar.querySelector('.res');
    let t = null, items = [], idx = -1;
    async function run() {
      const q = inp.value.trim();
      if (!q) { bar.classList.remove('open'); res.innerHTML = ''; return; }
      items = await api('GET', '/api/text-terms?q=' + encodeURIComponent(q));
      idx = -1;
      res.innerHTML = items.slice(0, 20).map((x, i) =>
        `<button data-i="${i}"><b>${esc(x.preferred_label)}</b> <span class="tag">${x.term_type}</span></button>`).join('')
        || '<div class="muted" style="padding:8px 12px;font-size:13px">no results — create a term from an annotation card</div>';
      bar.classList.add('open');
      res.querySelectorAll('button').forEach(b => b.addEventListener('click', () => location.href = '/vocabularies/' + items[+b.dataset.i].id));
    }
    inp.addEventListener('input', () => { clearTimeout(t); t = setTimeout(run, 160); });
    inp.addEventListener('focus', () => { if (inp.value.trim()) bar.classList.add('open'); });
    inp.addEventListener('blur', () => setTimeout(() => bar.classList.remove('open'), 200));
    inp.addEventListener('keydown', e => {
      const btns = res.querySelectorAll('button');
      if (e.key === 'ArrowDown') { e.preventDefault(); idx = Math.min(idx + 1, btns.length - 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); idx = Math.max(idx - 1, 0); }
      else if (e.key === 'Enter' && idx >= 0) { e.preventDefault(); btns[idx].click(); return; }
      else return;
      btns.forEach((b, i) => b.classList.toggle('hl', i === idx));
    });
    document.addEventListener('keydown', e => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); inp.focus(); inp.select(); }
    });
  }

  /* ---------- caricamento ---------- */
  async function reload() {
    // carica vista parallela del documento
    const view = await api('GET', `/api/documents/${window.STELE_DOC_ID}/parallel-view`);
    PARALLEL = view;
    if (!ACTIVE_TYPES) {
      ACTIVE_TYPES = new Set(view.active);
    } else {
      // mantiene le scelte utente ma include sempre la primary
      ACTIVE_TYPES.add(view.primary.version_type);
    }
    VERSION = view.primary.id;
    // annotazioni della versione primaria
    const d = await api('GET', `/api/text-versions/${VERSION}/annotations`);
    ANNS = d.annotations || [];
    render(); renderList(); renderMap(d.places || []); refreshTei();
    if (activeAi != null && activeAi < ANNS.length) selectCard(activeAi);
  }
  async function start() {
    try { RELTYPES = await api('GET', '/api/relation-types'); } catch (e) { RELTYPES = []; }
    await reload();
    const reader = $('#parallelReader');
    reader.addEventListener('mouseup', onMouseUp);
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') { hideSelPop(); TermPicker.close(); const m = $('#editModal'); if (m) m.classList.remove('open'); const m2 = $('#newParallelModal'); if (m2) m2.classList.remove('open'); }
    });
    wireSearchBar();
    wireVersioning();
    wireNewParallel();
  }

  /* ---------- versioni e modifica del testo ---------- */
  function wireVersioning() {
    const btn = $('#btnEditText');
    if (btn) btn.addEventListener('click', () => {
      $('#editText').value = CP.join('');
      $('#editNote').value = ''; $('#editMigrate').checked = true;
      $('#editModal').classList.add('open');
    });
    const close = () => $('#editModal').classList.remove('open');
    if ($('#editClose')) $('#editClose').addEventListener('click', close);
    if ($('#editCancel')) $('#editCancel').addEventListener('click', close);
    if ($('#editSave')) $('#editSave').addEventListener('click', async () => {
      const content = $('#editText').value;
      try {
        const rep = await api('POST', `/api/text-versions/${VERSION}/revise`, {
          content, note: $('#editNote').value || null, migrate: $('#editMigrate').checked
        });
        const msg = `New version created. Migrated annotations: ${rep.migrated}` +
          (rep.skipped ? `, not migrated: ${rep.skipped}` : '');
        toast(msg, rep.skipped ? 'warn' : 'ok');
        setTimeout(() => { window.location = `/annotate/${window.STELE_DOC_ID}`; }, 700);
      } catch (e) { toast(e.message, 'err'); }
    });
  }

  function wireNewParallel() {
    const btn = $('#btnNewParallel');
    if (!btn) return;
    btn.addEventListener('click', () => {
      const modal = $('#newParallelModal');
      if (modal) modal.classList.add('open');
    });
    if ($('#npClose')) $('#npClose').addEventListener('click', () => $('#newParallelModal').classList.remove('open'));
    if ($('#npCancel')) $('#npCancel').addEventListener('click', () => $('#newParallelModal').classList.remove('open'));
    if ($('#npSave')) $('#npSave').addEventListener('click', async () => {
      const body = {
        version_type: $('#npType').value,
        language: $('#npLang').value.trim() || null,
        content: $('#npContent').value,
        based_on_version_id: PARALLEL ? PARALLEL.primary.id : null,
        note: $('#npNote').value || null,
        auto_align: $('#npAlign').checked,
      };
      try {
        await api('POST', `/api/documents/${window.STELE_DOC_ID}/parallel-versions`, body);
        toast('Parallel version created and aligned.', 'ok');
        $('#newParallelModal').classList.remove('open');
        // resetta i campi
        ['#npContent', '#npNote', '#npLang'].forEach(s => { const el = $(s); if (el) el.value = ''; });
        await reload();
      } catch (e) { toast(e.message, 'err'); }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
