const TA = require('./assets/js/core.js');
const { DOMParser } = require('@xmldom/xmldom');
let pass = 0, fail = 0;
function ok(name, cond) { (cond ? pass++ : fail++); console.log((cond ? 'PASS ' : 'FAIL ') + name); }
function eq(name, a, b) { ok(name + ' (' + JSON.stringify(a) + ' == ' + JSON.stringify(b) + ')', JSON.stringify(a) === JSON.stringify(b)); }

// --- 1. Sovrapposizione X / Z / XYZ -----------------------------------------
const doc = TA.newDoc();
doc.text = 'XYZ';
doc.annotations = [
  { id: 'x', start: 0, end: 1, type: 'note', note: 'nota su X', tags: [], color: TA.colorFor(0) },
  { id: 'z', start: 2, end: 3, type: 'note', note: 'nota su Z', tags: [], color: TA.colorFor(1) },
  { id: 'xyz', start: 0, end: 3, type: 'note', note: 'nota su XYZ', tags: [], color: TA.colorFor(2) }
];
const segs = TA.buildSegments(doc.text, doc.annotations);
eq('segmenti XYZ: 3 segmenti', segs.length, 3);
eq('seg0 = X coperto da x+xyz', segs[0].anns.sort(), ['x', 'xyz']);
eq('seg1 = Y coperto solo da xyz', segs[1].anns.sort(), ['xyz']);
eq('seg2 = Z coperto da xyz+z', segs[2].anns.sort(), ['xyz', 'z']);

const lanes = TA.assignLanes(doc.annotations);
ok('lane: XYZ e X su corsie diverse', lanes.xyz !== lanes.x);
ok('lane: X e Z (non sovrapposti) possono condividere corsia', lanes.x === lanes.z);

const r = TA.renderAnnotatedHTML(doc);
ok('render produce html', r.html.indexOf('data-anns="x xyz"') !== -1 || r.html.indexOf('data-anns="x xyz"') !== -1);
ok('render: nessun tag non chiuso banale', (r.html.match(/<span/g) || []).length === (r.html.match(/<\/span>/g) || []).length);

// --- 2. Offset UTF-16 con caratteri Lineare B (surrogate pairs) --------------
const ko = String.fromCodePoint(0x10012), no = String.fromCodePoint(0x1001C), so = String.fromCodePoint(0x10030);
const konoso = ko + no + so;          // 3 segni = 6 unità UTF-16
eq('un segno Lineare B = 2 unità UTF-16', ko.length, 2);
eq('ko-no-so = 6 unità', konoso.length, 6);
const doc2 = TA.newDoc();
doc2.text = konoso + ' ' + 'X';
doc2.annotations = [{ id: 'p', start: 0, end: 6, type: 'place', note: '', tags: [], color: '#2a6f7a', place: { name: 'Cnosso', lat: 35.2980, lon: 25.1630, source: 'manual', detail: '' } }];
eq('slice offset place = ko-no-so', doc2.text.slice(0, 6), konoso);

// --- 3. TEI round-trip -------------------------------------------------------
const xml = TA.toTEI(doc2);
ok('TEI ben formato (parse)', (function () { try { const d = new DOMParser().parseFromString(xml, 'application/xml'); return d.getElementsByTagName('parsererror').length === 0; } catch (e) { return false; } })());
const back = TA.fromTEI(xml, DOMParser);
eq('round-trip: testo preservato', back.text, doc2.text);
eq('round-trip: 1 annotazione', back.annotations.length, 1);
eq('round-trip: offset', [back.annotations[0].start, back.annotations[0].end], [0, 6]);
eq('round-trip: tipo place', back.annotations[0].type, 'place');
eq('round-trip: coordinate', [back.annotations[0].place.lat, back.annotations[0].place.lon], [35.298, 25.163]);
eq('round-trip: nome luogo', back.annotations[0].place.name, 'Cnosso');

// TEI del caso XYZ
const back2 = TA.fromTEI(TA.toTEI(doc), DOMParser);
eq('round-trip XYZ: 3 annotazioni', back2.annotations.length, 3);
eq('round-trip XYZ: note conservate', back2.annotations.map(a => a.note).sort(), ['nota su X', 'nota su XYZ', 'nota su Z']);

// --- 4. Remap dopo edit del testo -------------------------------------------
// Inserimento PRIMA delle annotazioni: devono slittare.
let res = TA.remapAnnotations(doc.annotations, 'XYZ', 'ppXYZ');
eq('remap insert-before: X slitta a [2,3]', [res.annotations.find(a => a.id === 'x').start, res.annotations.find(a => a.id === 'x').end], [2, 3]);
eq('remap insert-before: nessun orfano', res.orphans.length, 0);
// Inserimento DENTRO l'annotazione xyz (fra Y e Z): xyz cresce, X invariata.
res = TA.remapAnnotations(doc.annotations, 'XYZ', 'XYQQZ');
eq('remap insert-inside: xyz cresce a [0,5]', [res.annotations.find(a => a.id === 'xyz').start, res.annotations.find(a => a.id === 'xyz').end], [0, 5]);
eq('remap insert-inside: X invariata [0,1]', [res.annotations.find(a => a.id === 'x').start, res.annotations.find(a => a.id === 'x').end], [0, 1]);
// Append in fondo: tutte invariate.
res = TA.remapAnnotations(doc.annotations, 'XYZ', 'XYZ...');
eq('remap append: tutte invariate', res.annotations.map(a => [a.start, a.end]), [[0, 1], [2, 3], [0, 3]]);

// --- 5. normalizeDoc scarta annotazioni fuori range / vuote -----------------
const bad = TA.normalizeDoc({ text: 'abc', annotations: [{ start: 1, end: 1 }, { start: 0, end: 99 }] });
eq('normalize: scarta vuote, clampa oltre-lunghezza', bad.annotations.map(a => [a.start, a.end]), [[0, 3]]);

// --- 6. Categorie ------------------------------------------------------------
const docCat = TA.normalizeDoc({
  text: 'ab cd', annotations: [
    { start: 0, end: 2, category: 'persona', note: 'n' },
    { start: 3, end: 5, category: 'luogo', note: 'l' }
  ]
});
eq('categoria persona conservata', docCat.annotations[0].category, 'persona');
eq('categoria luogo -> tipo place', docCat.annotations[1].type, 'place');
eq('colore da categoria persona', docCat.annotations[0].color, TA.CATEGORIES.persona.color);
// round-trip categoria via TEI
const rtCat = TA.fromTEI(TA.toTEI(docCat), DOMParser);
eq('round-trip categoria persona', rtCat.annotations.find(a => a.note === 'n').category, 'persona');
eq('round-trip categoria luogo', rtCat.annotations.find(a => a.note === 'l').category, 'luogo');

// --- 7. Riferimenti riga/colonna e statistiche ------------------------------
const multi = 'riga uno\nriga due\nterza';
eq('lineCol offset 0 = r1 c1', TA.lineColOf(multi, 0), { line: 1, col: 1 });
eq('lineCol dopo primo \\n', TA.lineColOf(multi, 9).line, 2);
eq('refLabel su riga 2', TA.refLabel(multi, 9, 13), 'r. 2, col. 1\u20134');
const konoso2 = String.fromCodePoint(0x10012) + String.fromCodePoint(0x1001C) + String.fromCodePoint(0x10030);
eq('refLabel: colonne in code point non in UTF-16', TA.refLabel(konoso2, 0, 6), 'r. 1, col. 1\u20133');
const stats = TA.docStats(docCat);
eq('docStats righe', stats.righe, 1);
eq('docStats luoghi', stats.luoghi, 1);
eq('docStats note (non-luogo)', stats.note, 1);

// --- 8. Rendering a righe numerate ------------------------------------------
const docLines = TA.newDoc(); docLines.text = 'AB\nCD';
docLines.annotations = [{ id: 'm', start: 0, end: 5, category: 'nota', note: 'tutto' }];
const rl = TA.renderAnnotatedHTML(docLines);
eq('render: due righe numerate', (rl.html.match(/class="ln"/g) || []).length, 2);
eq('render: annotazione multi-riga presente su entrambe le righe', (rl.html.match(/data-anns="m"/g) || []).length, 2);
ok('render: gutter con numeri di riga', rl.html.indexOf('class="lno">1<') !== -1 && rl.html.indexOf('class="lno">2<') !== -1);
ok('render: span bilanciati', (rl.html.match(/<span/g) || []).length === (rl.html.match(/<\/span>/g) || []).length);

console.log('\n' + pass + ' pass, ' + fail + ' fail');
process.exit(fail ? 1 : 0);
