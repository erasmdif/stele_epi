/* Grafo delle relazioni — force-directed in SVG, vanilla JS. */
(function () {
  'use strict';
  const $ = s => document.querySelector(s);
  const svg = $('#graph');
  const NS = 'http://www.w3.org/2000/svg';
  const TYPE_COLOR = {
    person: '#7a4fb0', deity: '#7a4fb0', place: '#2a6f9a', formula: '#2f7d5b',
    concept: '#c07b1f', quantity: '#b0872a', object_concept: '#b5561f',
    editorial_feature: '#6b6559', ethnonym: '#2a6f9a', institution: '#2a6f9a'
  };
  const colorOf = t => TYPE_COLOR[t] || '#6b6559';
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  let FOCUS = window.STELE_FOCUS, DEPTH = 2, KINDS = { relation: true, cooccur: true };
  let nodes = [], edges = [], sim = null, selected = null, W = 800, H = 600;

  async function api(url) { const r = await fetch(url); return r.json(); }

  function size() { const r = svg.getBoundingClientRect(); W = r.width || 800; H = r.height || 600; }

  async function load() {
    if (!FOCUS) return;
    const kinds = Object.keys(KINDS).filter(k => KINDS[k]).join(',') || 'relation';
    const g = await api(`/api/graph?focus=${FOCUS}&depth=${DEPTH}&kinds=${kinds}`);
    size();
    const prev = {}; nodes.forEach(n => prev[n.id] = n);
    nodes = g.nodes.map(n => Object.assign({
      x: (prev[n.id] && prev[n.id].x) || W / 2 + (Math.random() - .5) * 200,
      y: (prev[n.id] && prev[n.id].y) || H / 2 + (Math.random() - .5) * 200,
      vx: 0, vy: 0
    }, n));
    const byId = {}; nodes.forEach(n => byId[n.id] = n);
    edges = g.edges.filter(e => byId[e.source] && byId[e.target])
      .map(e => Object.assign({}, e, { s: byId[e.source], t: byId[e.target] }));
    $('#graphInfo').textContent = `${nodes.length} nodi · ${edges.length} archi`;
    renderLegend();
    runSim();
  }

  function renderLegend() {
    const types = Array.from(new Set(nodes.map(n => n.type)));
    $('#legend').innerHTML = types.map(t =>
      `<div style="display:flex;align-items:center;gap:6px;padding:1px 0">
        <span style="width:10px;height:10px;border-radius:50%;background:${colorOf(t)};display:inline-block"></span>${t}</div>`).join('') +
      `<div style="margin-top:6px;color:var(--ink-soft)">— gerarchica &nbsp; ·&nbsp; <span style="color:#b0a99a">···</span> co-occorrenza</div>`;
  }

  /* --- simulazione force-directed --- */
  function runSim() {
    if (sim) cancelAnimationFrame(sim);
    let ticks = 0;
    const focusNode = nodes.find(n => n.is_focus);
    if (focusNode) { focusNode.x = W / 2; focusNode.y = H / 2; }
    function tick() {
      const k = 0.02, rep = 5200, spring = 0.035, L = 96;
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          let dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy || 0.01;
          let d = Math.sqrt(d2), f = rep / d2;
          const fx = (dx / d) * f, fy = (dy / d) * f;
          a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
        }
        a.vx += (W / 2 - a.x) * k * 0.15;
        a.vy += (H / 2 - a.y) * k * 0.15;
      }
      edges.forEach(e => {
        let dx = e.t.x - e.s.x, dy = e.t.y - e.s.y, d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const f = (d - L) * spring, fx = (dx / d) * f, fy = (dy / d) * f;
        e.s.vx += fx; e.s.vy += fy; e.t.vx -= fx; e.t.vy -= fy;
      });
      nodes.forEach(n => {
        if (n === dragging) return;
        n.x += Math.max(-14, Math.min(14, n.vx)); n.y += Math.max(-14, Math.min(14, n.vy));
        n.vx *= 0.82; n.vy *= 0.82;
        n.x = Math.max(24, Math.min(W - 24, n.x)); n.y = Math.max(24, Math.min(H - 24, n.y));
      });
      draw();
      if (++ticks < 260) sim = requestAnimationFrame(tick);
    }
    tick();
  }

  /* --- rendering SVG --- */
  function draw() {
    let s = '';
    edges.forEach(e => {
      const dash = e.kind === 'cooccur' ? 'stroke-dasharray="3,3"' : '';
      const col = e.kind === 'cooccur' ? '#c7bfa9' : (e.hierarchical ? '#8a8271' : '#b0a99a');
      const mx = (e.s.x + e.t.x) / 2, my = (e.s.y + e.t.y) / 2;
      s += `<line x1="${e.s.x}" y1="${e.s.y}" x2="${e.t.x}" y2="${e.t.y}" stroke="${col}" stroke-width="1.3" ${dash}/>`;
      s += `<text x="${mx}" y="${my - 2}" font-size="9" fill="#8a8271" text-anchor="middle">${esc(e.label)}</text>`;
    });
    nodes.forEach(n => {
      const r = n.is_focus ? 15 : (9 + Math.min(6, (n.degree || 0)));
      const stroke = (selected && selected.id === n.id) ? '#b5561f' : (n.is_focus ? '#1f545c' : '#fff');
      s += `<g class="gnode" data-id="${n.id}" style="cursor:pointer">
        <circle cx="${n.x}" cy="${n.y}" r="${r}" fill="${colorOf(n.type)}" stroke="${stroke}" stroke-width="${n.is_focus || (selected && selected.id === n.id) ? 3 : 1.5}"/>
        <text x="${n.x}" y="${n.y + r + 11}" font-size="11" text-anchor="middle" fill="#22201b">${esc(n.label)}</text>
      </g>`;
    });
    svg.innerHTML = s;
    svg.querySelectorAll('.gnode').forEach(g => {
      g.addEventListener('mousedown', startDrag);
      g.addEventListener('click', () => selectNode(+g.dataset.id));
    });
  }

  /* --- drag --- */
  let dragging = null, dragMoved = false;
  function startDrag(e) {
    const id = +e.currentTarget.dataset.id;
    dragging = nodes.find(n => n.id === id); dragMoved = false;
    const move = ev => {
      const pt = svgPoint(ev); dragging.x = pt.x; dragging.y = pt.y; dragMoved = true;
      if (!sim) draw();
    };
    const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); dragging = null; };
    document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
  }
  function svgPoint(ev) {
    const r = svg.getBoundingClientRect();
    return { x: ev.clientX - r.left, y: ev.clientY - r.top };
  }

  /* --- selezione nodo -> dettaglio + percorso dal focus --- */
  async function selectNode(id) {
    selected = nodes.find(n => n.id === id); draw();
    const d = await api(`/api/vocab/text_term/${id}/lineage`);
    const anc = (d.ancestors || []).map(a => a.preferred_label);
    const neigh = (d.neighbours || []);
    const path = shortestPath(FOCUS, id);
    $('#detail').innerHTML = `
      <div style="display:flex;align-items:center;gap:8px">
        <span style="width:12px;height:12px;border-radius:50%;background:${colorOf(selected.type)};display:inline-block"></span>
        <b style="font-size:16px">${esc(selected.label)}</b><span class="tag">${selected.type}</span></div>
      <div style="margin-top:6px"><button class="btn mini" id="setFocus">Metti a fuoco</button></div>
      ${anc.length ? `<p class="eyebrow" style="margin-top:12px">Gerarchia</p><div class="muted" style="font-size:13px">${esc(selected.label)} → ${anc.map(esc).join(' → ')}</div>` : ''}
      <p class="eyebrow" style="margin-top:12px">Relazioni dirette (${neigh.length})</p>
      <div style="font-size:13px">${neigh.map(n => `<div style="padding:2px 0">${n.dir === 'out' ? '' : '↩ '}<span class="muted">${esc(n.rel_label)}</span> → <a href="#" data-goto="${n.other_id}">${esc(n.other_label)}</a></div>`).join('') || '<span class="muted">nessuna</span>'}</div>
      <p class="eyebrow" style="margin-top:12px">Percorso dal focus</p>
      <div style="font-size:13px">${path ? path.map(esc).join(' → ') : '<span class="muted">nessun percorso nel grafo caricato</span>'}</div>`;
    const sf = $('#setFocus'); if (sf) sf.addEventListener('click', () => { FOCUS = id; load(); });
    $('#detail').querySelectorAll('[data-goto]').forEach(a => a.addEventListener('click', ev => { ev.preventDefault(); selectNode(+a.dataset.goto); }));
  }

  function shortestPath(from, to) {
    if (from === to) { const n = nodes.find(x => x.id === from); return n ? [n.label] : null; }
    const adj = {}; nodes.forEach(n => adj[n.id] = []);
    edges.forEach(e => { adj[e.source].push(e.target); adj[e.target].push(e.source); });
    const q = [[from]], seen = new Set([from]);
    while (q.length) {
      const p = q.shift(), last = p[p.length - 1];
      if (last === to) return p.map(id => (nodes.find(n => n.id === id) || {}).label);
      for (const nb of (adj[last] || [])) if (!seen.has(nb)) { seen.add(nb); q.push(p.concat(nb)); }
    }
    return null;
  }

  /* --- controlli --- */
  function bind() {
    $('#depth').addEventListener('input', e => { DEPTH = +e.target.value; $('#depthVal').textContent = DEPTH; });
    $('#depth').addEventListener('change', load);
    $('#kRelation').addEventListener('change', e => { KINDS.relation = e.target.checked; load(); });
    $('#kCooccur').addEventListener('change', e => { KINDS.cooccur = e.target.checked; load(); });
    const inp = $('#focusSearch'), res = $('#focusRes'); let t = null;
    inp.addEventListener('input', () => {
      clearTimeout(t); t = setTimeout(async () => {
        const d = await api('/api/text-terms?q=' + encodeURIComponent(inp.value.trim()));
        res.innerHTML = d.map(x => `<button data-id="${x.id}" style="display:block;width:100%;text-align:left;border:none;background:transparent;padding:5px 6px;border-radius:5px;cursor:pointer;font:inherit;font-size:13px">${esc(x.preferred_label)} <span class="tag">${x.term_type}</span></button>`).join('');
        res.querySelectorAll('button').forEach(b => b.addEventListener('click', () => { FOCUS = +b.dataset.id; res.innerHTML = ''; inp.value = ''; load(); }));
      }, 180);
    });
    window.addEventListener('resize', () => { size(); draw(); });
  }

  bind();
  if (FOCUS) load();
  else $('#detail').innerHTML = '<p class="muted">Nessun termine con relazioni. Aggiungine dalla vista di annotazione.</p>';
})();
