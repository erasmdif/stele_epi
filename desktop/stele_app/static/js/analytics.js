/* Stele Analytics Dashboard */
(function(){
"use strict";

const API = "/api";

/* ── Tabs ───────────────────────────────────────────────────────── */
document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("panel-" + btn.dataset.tab).classList.add("active");
  });
});

/* ── Helpers ────────────────────────────────────────────────────── */
async function api(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(r.statusText);
  return r.json();
}
function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}
function heatClass(v, max) {
  if (!v) return "heat-0";
  const r = v / (max || 1);
  if (r <= 0.1) return "heat-1";
  if (r <= 0.25) return "heat-2";
  if (r <= 0.5) return "heat-3";
  if (r <= 0.75) return "heat-4";
  return "heat-5";
}
function esc(s) { return (s||"").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

/* ══════════════════════════════════════════════════════════════════
   1. SEMANTIC SEARCH
   ══════════════════════════════════════════════════════════════════ */
(async function initSemantic(){
  const sel = document.getElementById("sem-term");
  const depSel = document.getElementById("sem-deposit");
  try {
    const terms = await api("/analytics/terms-for-search");
    terms.forEach(t => {
      const o = document.createElement("option");
      o.value = t.id; o.textContent = t.preferred_label;
      sel.appendChild(o);
    });
  } catch(e){ console.warn("terms load failed", e); }
  try {
    const enums = await api("/enums/archaeology");
    (enums.deposit_types||[]).forEach(dt => {
      const o = document.createElement("option");
      o.value = dt; o.textContent = dt;
      depSel.appendChild(o);
    });
  } catch(e){}
})();

document.getElementById("sem-go").addEventListener("click", async () => {
  const tid = document.getElementById("sem-term").value;
  const dep = document.getElementById("sem-deposit").value;
  const yf = document.getElementById("sem-from").value;
  const yt = document.getElementById("sem-to").value;
  const box = document.getElementById("sem-results");
  box.innerHTML = '<p class="placeholder">Searching…</p>';
  let url = `/analytics/semantic-search?term_id=${tid}`;
  if (dep) url += `&deposit_type=${encodeURIComponent(dep)}`;
  if (yf) url += `&year_from=${yf}`;
  if (yt) url += `&year_to=${yt}`;
  try {
    const rows = await api(url);
    if (!rows.length) { box.innerHTML = '<p class="placeholder">No results found.</p>'; return; }
    box.innerHTML = `<p class="result-count">${rows.length} annotation(s) found</p>`;
    // deduplica per annotation_id
    const seen = new Set();
    rows.forEach(r => {
      if (seen.has(r.annotation_id)) return;
      seen.add(r.annotation_id);
      const content = r.version_content || "";
      const pre = esc(content.substring(Math.max(0,r.start_position-20), r.start_position));
      const hit = esc(content.substring(r.start_position, r.end_position));
      const post = esc(content.substring(r.end_position, r.end_position+20));
      const card = el("div","result-card",`
        <div class="rc-head">
          <span class="rc-siglum">${esc(r.siglum||r.doc_id)}</span>
          <span class="rc-term">${esc(r.matched_term)}</span>
          ${r.context_name ? `<span class="rc-ctx">ctx: ${esc(r.context_name)}${r.deposit_type?' ('+esc(r.deposit_type)+')':''}</span>` : ''}
          ${r.object_label ? `<span class="rc-ctx">obj: ${esc(r.object_label)}</span>` : ''}
        </div>
        <div class="rc-excerpt">…${pre}<span class="rc-highlight">${hit}</span>${post}…</div>
      `);
      box.appendChild(card);
    });
  } catch(e){ box.innerHTML = `<p class="placeholder">Error: ${esc(e.message)}</p>`; }
});

/* ══════════════════════════════════════════════════════════════════
   2. CO-OCCURRENCE GRAPH (force-directed SVG)
   ══════════════════════════════════════════════════════════════════ */
document.getElementById("cooc-go").addEventListener("click", async () => {
  const scope = document.getElementById("cooc-scope").value;
  const minC = document.getElementById("cooc-min").value;
  try {
    const data = await api(`/analytics/cooccurrence?scope=${scope}&min_count=${minC}`);
    drawForceGraph(data);
  } catch(e){ console.error(e); }
});

function drawForceGraph(data) {
  const svg = document.getElementById("cooc-svg");
  const W = svg.parentElement.clientWidth || 800;
  const H = svg.parentElement.clientHeight || 500;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.innerHTML = "";

  if (!data.nodes.length) {
    const t = document.createElementNS("http://www.w3.org/2000/svg","text");
    t.setAttribute("x",W/2); t.setAttribute("y",H/2);
    t.setAttribute("text-anchor","middle"); t.setAttribute("fill","#999");
    t.textContent = "No co-occurrences found.";
    svg.appendChild(t); return;
  }

  const nodes = data.nodes.map((n,i) => ({...n, x:W/2+Math.cos(i)*100, y:H/2+Math.sin(i)*100, vx:0, vy:0}));
  const nodeMap = {}; nodes.forEach(n => nodeMap[n.id] = n);
  const edges = data.edges.filter(e => nodeMap[e.source] && nodeMap[e.target]);
  const maxW = Math.max(1, ...edges.map(e=>e.weight));
  const maxA = Math.max(1, ...nodes.map(n=>n.total_annotations));

  // SVG elements
  const edgeEls = edges.map(e => {
    const l = document.createElementNS("http://www.w3.org/2000/svg","line");
    l.setAttribute("stroke","#2a6f7a"); l.setAttribute("stroke-opacity","0.4");
    l.setAttribute("stroke-width", 1 + (e.weight/maxW)*4);
    svg.appendChild(l); return l;
  });
  const nodeEls = nodes.map(n => {
    const g = document.createElementNS("http://www.w3.org/2000/svg","g");
    const c = document.createElementNS("http://www.w3.org/2000/svg","circle");
    const r = 6 + (n.total_annotations/maxA)*14;
    c.setAttribute("r", r); c.setAttribute("fill","#2a6f7a"); c.setAttribute("fill-opacity","0.7");
    c.setAttribute("stroke","#1f545c"); c.setAttribute("stroke-width","1");
    const t = document.createElementNS("http://www.w3.org/2000/svg","text");
    t.setAttribute("dy","-10"); t.setAttribute("text-anchor","middle");
    t.setAttribute("font-size","11"); t.setAttribute("fill","#22201b");
    t.textContent = n.label;
    g.appendChild(c); g.appendChild(t); svg.appendChild(g);
    // drag
    let dragging = false;
    c.addEventListener("mousedown", e2 => { dragging=true; e2.preventDefault(); });
    window.addEventListener("mousemove", e2 => {
      if (!dragging) return;
      const rect = svg.getBoundingClientRect();
      n.x = (e2.clientX - rect.left) / rect.width * W;
      n.y = (e2.clientY - rect.top) / rect.height * H;
    });
    window.addEventListener("mouseup", () => { dragging=false; });
    return {g, c, r};
  });

  // Simple force simulation
  function tick() {
    // repulsion
    for (let i=0; i<nodes.length; i++) {
      for (let j=i+1; j<nodes.length; j++) {
        let dx = nodes[j].x - nodes[i].x, dy = nodes[j].y - nodes[i].y;
        let d = Math.sqrt(dx*dx+dy*dy) || 1;
        let f = 800/(d*d);
        nodes[i].vx -= dx/d*f; nodes[i].vy -= dy/d*f;
        nodes[j].vx += dx/d*f; nodes[j].vy += dy/d*f;
      }
    }
    // attraction (edges)
    edges.forEach(e => {
      const s=nodeMap[e.source], t=nodeMap[e.target];
      let dx=t.x-s.x, dy=t.y-s.y, d=Math.sqrt(dx*dx+dy*dy)||1;
      let f=(d-120)*0.01;
      s.vx += dx/d*f; s.vy += dy/d*f;
      t.vx -= dx/d*f; t.vy -= dy/d*f;
    });
    // center gravity
    nodes.forEach(n => {
      n.vx += (W/2-n.x)*0.002; n.vy += (H/2-n.y)*0.002;
      n.vx *= 0.9; n.vy *= 0.9;
      n.x += n.vx; n.y += n.vy;
      n.x = Math.max(30, Math.min(W-30, n.x));
      n.y = Math.max(30, Math.min(H-30, n.y));
    });
    // update SVG
    edgeEls.forEach((l,i) => {
      const s=nodeMap[edges[i].source], t=nodeMap[edges[i].target];
      l.setAttribute("x1",s.x); l.setAttribute("y1",s.y);
      l.setAttribute("x2",t.x); l.setAttribute("y2",t.y);
    });
    nodeEls.forEach((ne,i) => {
      ne.g.setAttribute("transform",`translate(${nodes[i].x},${nodes[i].y})`);
    });
  }
  let frame = 0;
  function anim() { tick(); frame++; if (frame < 300) requestAnimationFrame(anim); }
  anim();
}

/* ══════════════════════════════════════════════════════════════════
   3. TEXT × CONCEPTS MATRIX
   ══════════════════════════════════════════════════════════════════ */
document.getElementById("matrix-go").addEventListener("click", async () => {
  const box = document.getElementById("matrix-container");
  box.innerHTML = '<p class="placeholder">Loading…</p>';
  try {
    const data = await api("/analytics/text-concept-matrix");
    box.innerHTML = "";
    if (!data.rows.length) { box.innerHTML = '<p class="placeholder">No data.</p>'; return; }
    const maxVal = Math.max(1, ...data.rows.flatMap(r => data.columns.map(c => r.counts[c]||0)));
    let html = '<table><thead><tr><th></th>';
    data.columns.forEach(c => html += `<th>${esc(c)}</th>`);
    html += '</tr></thead><tbody>';
    data.rows.forEach(r => {
      html += `<tr><td class="row-label">${esc(r.siglum)}</td>`;
      data.columns.forEach(c => {
        const v = r.counts[c] || 0;
        html += `<td class="${heatClass(v,maxVal)}" title="${v}">${v||'—'}</td>`;
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    box.innerHTML = html;
  } catch(e) { box.innerHTML = `<p class="placeholder">Error: ${esc(e.message)}</p>`; }
});

/* ══════════════════════════════════════════════════════════════════
   4. TEXT × ARCHAEOLOGY CROSS-REFERENCE
   ══════════════════════════════════════════════════════════════════ */
document.getElementById("cross-go").addEventListener("click", async () => {
  const box = document.getElementById("cross-container");
  box.innerHTML = '<p class="placeholder">Loading…</p>';
  try {
    const data = await api("/analytics/text-archaeology-cross");
    box.innerHTML = "";
    if (!data.columns.length) { box.innerHTML = '<p class="placeholder">No contexts with deposit types found.</p>'; return; }
    const maxVal = Math.max(1, ...data.rows.flatMap(r => data.columns.map(c => r.counts[c]||0)));
    let html = '<table><thead><tr><th>Semantic branch</th>';
    data.columns.forEach(c => html += `<th>${esc(c)}</th>`);
    html += '</tr></thead><tbody>';
    data.rows.forEach(r => {
      html += `<tr><td class="row-label">${esc(r.category)}</td>`;
      data.columns.forEach(c => {
        const v = r.counts[c] || 0;
        html += `<td class="${heatClass(v,maxVal)}" title="${v}">${v||'—'}</td>`;
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    box.innerHTML = html;
  } catch(e) { box.innerHTML = `<p class="placeholder">Error: ${esc(e.message)}</p>`; }
});

/* ══════════════════════════════════════════════════════════════════
   6. SPATIOTEMPORAL MAP (Leaflet)
   ══════════════════════════════════════════════════════════════════ */
let sptMap = null;
let sptLayer = null;

(async function initSpt(){
  const sel = document.getElementById("spt-term");
  try {
    const terms = await api("/analytics/terms-for-search");
    terms.forEach(t => {
      const o = document.createElement("option");
      o.value = t.id; o.textContent = t.preferred_label;
      sel.appendChild(o);
    });
  } catch(e){ console.warn("spt terms load failed", e); }
})();

function ensureSptMap() {
  if (sptMap) return sptMap;
  sptMap = L.map("spt-map", { scrollWheelZoom: true }).setView([41.9, 12.5], 4);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors', maxZoom: 19
  }).addTo(sptMap);
  sptLayer = L.layerGroup().addTo(sptMap);
  return sptMap;
}
document.querySelector('[data-tab="spatiotemporal"]').addEventListener("click", () => {
  setTimeout(() => { ensureSptMap(); sptMap.invalidateSize(); }, 50);
});

document.getElementById("spt-go").addEventListener("click", async () => {
  ensureSptMap();
  sptLayer.clearLayers();
  const stats = document.getElementById("spt-stats");
  stats.innerHTML = 'Loading…';
  const params = new URLSearchParams();
  params.set("mode", document.getElementById("spt-mode").value);
  const tid = document.getElementById("spt-term").value;
  const yf = document.getElementById("spt-from").value;
  const yt = document.getElementById("spt-to").value;
  if (tid) params.set("term_id", tid);
  if (yf) params.set("year_from", yf);
  if (yt) params.set("year_to", yt);
  try {
    const points = await api("/analytics/spatiotemporal?" + params.toString());
    if (!points.length) { stats.innerHTML = 'No points found for these filters.'; return; }
    const grouped = {};
    points.forEach(p => {
      const key = `${p.lat.toFixed(4)}_${p.lon.toFixed(4)}`;
      if (!grouped[key]) grouped[key] = { lat:p.lat, lon:p.lon, items:[] };
      grouped[key].items.push(p);
    });
    const bounds = [];
    Object.values(grouped).forEach(g => {
      const m = L.circleMarker([g.lat, g.lon], {
        radius: Math.min(6 + Math.sqrt(g.items.length) * 2, 16),
        color: '#1f545c', fillColor: '#2a6f7a',
        fillOpacity: 0.65, weight: 1.5,
      });
      const html = `<div class="spt-marker-popup">
        <strong>${g.items.length} attestation(s)</strong><br>
        ${g.items.slice(0,8).map(p => `
          <div style="margin-top:5px">
            <span class="m-siglum">${esc(p.siglum||'')}</span>
            — ${esc(p.matched_term||'')}<br>
            ${p.object_label ? `<span class="m-year">${esc(p.object_label)}</span>` : ''}
            ${p.year_from ? `<span class="m-year"> · ${p.year_from}–${p.year_to}</span>` : ''}
          </div>`).join('')}
        ${g.items.length > 8 ? `<div><em>… +${g.items.length-8} more</em></div>` : ''}
      </div>`;
      m.bindPopup(html);
      m.addTo(sptLayer);
      bounds.push([g.lat, g.lon]);
    });
    if (bounds.length > 0) sptMap.fitBounds(bounds, { padding: [30, 30], maxZoom: 8 });
    stats.innerHTML = `<strong>${points.length}</strong> attestations at <strong>${Object.keys(grouped).length}</strong> distinct locations.`;
  } catch(e) {
    stats.innerHTML = `Error: ${esc(e.message)}`;
  }
});

/* ══════════════════════════════════════════════════════════════════
   7. FORMULAS & PARALLELS
   ══════════════════════════════════════════════════════════════════ */
document.getElementById("frm-go").addEventListener("click", async () => {
  const vtype = document.getElementById("frm-vtype").value;
  const ngram = document.getElementById("frm-ngram").value;
  const sim = document.getElementById("frm-sim").value;
  const ngramBox = document.getElementById("frm-ngram-list");
  const matchBox = document.getElementById("frm-matches");
  ngramBox.innerHTML = '<p class="placeholder">Loading…</p>';
  matchBox.innerHTML = '<p class="placeholder">Loading…</p>';
  try {
    const nd = await api(`/analytics/ngram-frequency?version_type=${vtype}&ngram=${ngram}&min_count=2&limit=25`);
    if (!nd.top_ngrams.length) {
      ngramBox.innerHTML = '<p class="placeholder">No recurring n-grams (try lower n or a different version type).</p>';
    } else {
      const maxCount = nd.top_ngrams[0].count;
      ngramBox.innerHTML = nd.top_ngrams.map(ng => `
        <div class="ngram-item">
          <span class="ng-text">${esc(ng.ngram)}</span>
          <span class="ng-bar"><span class="ng-bar-fill" style="width:${(ng.count/maxCount*100)}%"></span></span>
          <span class="ng-count">${ng.count}</span>
        </div>`).join('');
    }
    const md = await api(`/analytics/formula-search?version_type=${vtype}&ngram=${ngram}&min_similarity=${sim}`);
    if (!md.matches.length) {
      matchBox.innerHTML = `<p class="placeholder">No parallels found above ${sim} similarity.<br>${md.n_texts} texts compared.</p>`;
    } else {
      matchBox.innerHTML = `<p class="result-count">${md.matches.length} pair(s) found among ${md.n_texts} texts</p>` +
        md.matches.map(m => {
          const cls = m.similarity > 0.5 ? 'high' : m.similarity > 0.2 ? 'medium' : '';
          return `<div class="match-item">
            <div class="m-head">
              <span class="m-pair">${esc(m.a_siglum||'?')} ↔ ${esc(m.b_siglum||'?')}</span>
              <span class="m-sim ${cls}">${Math.round(m.similarity*100)}%</span>
            </div>
            <div class="m-shared">
              ${m.n_shared} shared: ${m.shared_ngrams.map(s => `<code>${esc(s)}</code>`).join('')}
            </div>
          </div>`;
        }).join('');
    }
  } catch(e) {
    ngramBox.innerHTML = matchBox.innerHTML = `<p class="placeholder">Error: ${esc(e.message)}</p>`;
  }
});

/* ══════════════════════════════════════════════════════════════════
   8. CONCEPT TIMELINE
   ══════════════════════════════════════════════════════════════════ */
document.getElementById("tim-go").addEventListener("click", async () => {
  const gran = document.getElementById("tim-gran").value;
  const chart = document.getElementById("tim-chart");
  const legend = document.getElementById("tim-legend");
  chart.innerHTML = '<p class="placeholder">Loading…</p>';
  legend.innerHTML = '';
  try {
    const data = await api(`/analytics/concept-timeline?granularity=${gran}`);
    if (!data.bins.length) {
      chart.innerHTML = '<p class="placeholder">No dated annotations to build a timeline.</p>';
      return;
    }
    drawTimeline(data, chart, legend);
  } catch(e) {
    chart.innerHTML = `<p class="placeholder">Error: ${esc(e.message)}</p>`;
  }
});

function drawTimeline(data, chartEl, legendEl) {
  const W = Math.max(chartEl.clientWidth - 32, 400);
  const H = 340;
  const M = { top: 20, right: 20, bottom: 60, left: 50 };
  const iw = W - M.left - M.right;
  const ih = H - M.top - M.bottom;
  const nBins = data.bins.length;
  const palette = ["#2a6f7a","#b5561f","#2f8f4e","#8e44ad","#e6960e",
                    "#c0392b","#16a085","#d35400","#7d3c98","#1a5490",
                    "#a89c00","#7f8c8d","#5d6d7e","#af7ac5","#48c9b0",
                    "#f39c12","#e74c3c","#3498db","#27ae60","#9b59b6"];
  data.series.forEach((s, i) => { s._color = palette[i % palette.length]; s._hidden = false; });

  function render() {
    const active = data.series.filter(s => !s._hidden);
    const maxVal = Math.max(1, ...data.bins.map((_, i) => active.reduce((sum, s) => sum + s.counts[i], 0)));
    let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">`;
    const nTicks = 5;
    for (let i = 0; i <= nTicks; i++) {
      const y = M.top + ih - (i / nTicks) * ih;
      const val = Math.round(maxVal * i / nTicks);
      svg += `<line x1="${M.left}" y1="${y}" x2="${M.left + iw}" y2="${y}" stroke="#d7d1c2" stroke-dasharray="2,3"/>`;
      svg += `<text x="${M.left - 6}" y="${y + 4}" text-anchor="end" font-size="10" fill="#55503f">${val}</text>`;
    }
    const binW = iw / nBins;
    for (let bi = 0; bi < nBins; bi++) {
      const xBin = M.left + bi * binW;
      let cumulative = 0;
      active.forEach(s => {
        const val = s.counts[bi];
        if (!val) return;
        const h = (val / maxVal) * ih;
        const y = M.top + ih - cumulative - h;
        svg += `<rect x="${xBin + 6}" y="${y}" width="${binW - 12}" height="${h}" fill="${s._color}" fill-opacity="0.85">`;
        svg += `<title>${s.label} — ${data.bins[bi]}: ${val}</title></rect>`;
        cumulative += h;
      });
      svg += `<text x="${xBin + binW/2}" y="${M.top + ih + 15}" text-anchor="middle" font-size="10" fill="#55503f">${data.bins[bi]}</text>`;
    }
    svg += `<line x1="${M.left}" y1="${M.top + ih}" x2="${M.left + iw}" y2="${M.top + ih}" stroke="#22201b"/>`;
    svg += `<line x1="${M.left}" y1="${M.top}" x2="${M.left}" y2="${M.top + ih}" stroke="#22201b"/>`;
    svg += `<text x="${M.left}" y="${M.top - 6}" font-size="11" fill="#55503f">annotations</text>`;
    svg += `</svg>`;
    chartEl.innerHTML = svg;
  }
  render();

  legendEl.innerHTML = data.series.map((s, i) => `
    <div class="leg-item ${s._hidden?'hidden':''}" data-idx="${i}">
      <span class="leg-swatch" style="background:${s._color}"></span>
      <span>${esc(s.label)}</span>
    </div>`).join('');
  legendEl.querySelectorAll('.leg-item').forEach(el => {
    el.addEventListener('click', () => {
      const idx = parseInt(el.dataset.idx);
      data.series[idx]._hidden = !data.series[idx]._hidden;
      el.classList.toggle('hidden');
      render();
    });
  });
}

/* ══════════════════════════════════════════════════════════════════
   9. WORK WITNESSES DIFF
   ══════════════════════════════════════════════════════════════════ */
(async function initWit(){
  const sel = document.getElementById("wit-work");
  try {
    const works = await api("/analytics/works-with-witnesses");
    if (!works.length) {
      sel.innerHTML = '<option value="">No works with ≥2 witnesses</option>';
      return;
    }
    works.forEach(w => {
      const o = document.createElement("option");
      o.value = w.id;
      o.textContent = `${w.title} (${w.n_witnesses} witnesses)`;
      sel.appendChild(o);
    });
  } catch(e) { console.warn("wit works load failed", e); }
})();

document.getElementById("wit-go").addEventListener("click", async () => {
  const workId = document.getElementById("wit-work").value;
  if (!workId) return;
  const vtype = document.getElementById("wit-vtype").value;
  const ngram = document.getElementById("wit-ngram").value;
  const statsBox = document.getElementById("wit-stats");
  const matrixBox = document.getElementById("wit-matrix");
  const appBox = document.getElementById("wit-apparatus");
  const pairBox = document.getElementById("wit-pair");
  statsBox.innerHTML = 'Loading…';
  matrixBox.innerHTML = ''; appBox.innerHTML = ''; pairBox.innerHTML = '';
  try {
    const data = await api(`/analytics/works/${workId}/witnesses-diff?version_type=${vtype}&ngram=${ngram}`);
    if (data.message) { statsBox.innerHTML = data.message; return; }
    const s = data.stats;
    statsBox.innerHTML = `
      <strong>${s.n_witnesses}</strong> witnesses <span class="sep">·</span>
      average similarity <strong>${Math.round(s.avg_similarity*100)}%</strong>
      (range ${Math.round(s.min_similarity*100)}%–${Math.round(s.max_similarity*100)}%)
      <span class="sep">·</span>
      <strong>${s.n_lines_with_variants}</strong> lines with variants (out of ${s.n_lines_total})
    `;
    renderWitMatrix(data, workId, vtype, matrixBox, pairBox);
    renderApparatus(data, appBox);
  } catch(e) { statsBox.innerHTML = `Error: ${esc(e.message)}`; }
});

function renderWitMatrix(data, workId, vtype, box, pairBox) {
  const w = data.witnesses; const m = data.matrix;
  let html = '<table><thead><tr><th></th>';
  w.forEach(wt => {
    html += `<th title="${esc(wt.siglum||'')}">${esc(wt.witness_siglum||'?')}</th>`;
  });
  html += '</tr></thead><tbody>';
  m.forEach((row, i) => {
    html += `<tr><th class="wit-label" title="${esc(w[i].object_label||'')}">${esc(w[i].witness_siglum||'?')} — ${esc(w[i].siglum||'')}</th>`;
    row.forEach((val, j) => {
      if (i === j) { html += `<td class="diag">—</td>`; }
      else {
        const pct = Math.round(val * 100);
        const hue = val * 120;
        const bg = `hsl(${hue}, 55%, 82%)`;
        html += `<td class="clickable" style="background:${bg}"
                     data-a="${w[i].doc_id}" data-b="${w[j].doc_id}"
                     title="Click to see pairwise diff">${pct}</td>`;
      }
    });
    html += '</tr>';
  });
  html += '</tbody></table>';
  box.innerHTML = html;
  box.querySelectorAll('td.clickable').forEach(td => {
    td.addEventListener('click', () => loadPairDiff(workId, vtype,
      td.dataset.a, td.dataset.b, pairBox));
  });
}

function renderApparatus(data, box) {
  if (!data.variants.length) {
    box.innerHTML = '<p class="placeholder">No line-level variants.</p>'; return;
  }
  box.innerHTML = data.variants.map(v => `
    <div class="var-line">
      <div class="var-line-head">Line ${v.line} — ${v.n_readings} readings</div>
      ${v.readings.map(rd => {
        const isOmit = rd.reading === "[omit.]";
        return `<div class="var-reading">
          <span class="var-text ${isOmit ? 'omit' : ''}">${esc(rd.reading)}</span>
          <span class="var-siglums">${rd.witnesses.map(s => `<code>${esc(s)}</code>`).join('')} <em>(${rd.count})</em></span>
        </div>`;
      }).join('')}
    </div>`).join('');
}

async function loadPairDiff(workId, vtype, aId, bId, box) {
  box.innerHTML = '<p class="placeholder">Loading pair diff…</p>';
  try {
    const p = await api(`/analytics/works/${workId}/pair-diff?a=${aId}&b=${bId}&version_type=${vtype}`);
    if (!p) { box.innerHTML = ''; return; }
    const a = p.a, b = p.b, s = p.summary;
    let html = `
      <div class="wit-pair-head">
        <strong>${esc(a.witness_siglum||'?')} (${esc(a.siglum||'')})</strong>
        vs
        <strong>${esc(b.witness_siglum||'?')} (${esc(b.siglum||'')})</strong>
        — global similarity: <strong>${Math.round(p.global_similarity*100)}%</strong>
      </div>
      <div class="wit-pair-summary">
        ${s.equal} equal · ${s.variant} variant · ${s.conflict} conflict ·
        ${s.only_a} only in A · ${s.only_b} only in B  (${s.total} total lines)
      </div>
      <table class="wit-pair-table">
        <thead><tr>
          <th class="status-cell">Status</th>
          <th>${esc(a.witness_siglum||'A')}</th>
          <th>${esc(b.witness_siglum||'B')}</th>
        </tr></thead><tbody>`;
    p.lines.forEach(ln => {
      const sim = ln.similarity < 1 ? ` (${Math.round(ln.similarity*100)}%)` : '';
      html += `<tr class="status-${ln.status}">
        <td class="status-cell">${ln.status}${sim}</td>
        <td class="${ln.a === null ? 'missing' : ''}">${ln.a === null ? '—' : esc(ln.a)}</td>
        <td class="${ln.b === null ? 'missing' : ''}">${ln.b === null ? '—' : esc(ln.b)}</td>
      </tr>`;
    });
    html += '</tbody></table>';
    box.innerHTML = html;
    box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch(e) { box.innerHTML = `<p class="placeholder">Error: ${esc(e.message)}</p>`; }
}

})();
