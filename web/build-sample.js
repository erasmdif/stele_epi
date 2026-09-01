const fs = require('fs');
const TA = require('./assets/js/core.js');
const cp = h => String.fromCodePoint(parseInt(h, 16));

// Segni Lineare B usati (code point reali)
const S = {
  ko: cp('10012'), no: cp('1001C'), so: cp('10030'),
  pa: cp('1001E'), i: cp('10002'), to: cp('10035'),
  a: cp('10000'), mi: cp('10016'), ni: cp('1001B'),
  e: cp('10001'), re: cp('10029'), si: cp('1002F'), ja: cp('1000B'),
  qe: cp('10025')
};
const konoso = S.ko + S.no + S.so;      // Cnosso
const paito  = S.pa + S.i + S.to;       // Festo
const aminiso = S.a + S.mi + S.ni + S.so; // Amniso
const eresija = S.e + S.re + S.si + S.ja; // e-re-si-ja
const qere = S.qe + S.re;               // qe-re

// Testo multi-registro: Lineare B / traslitterazione / traduzione, su più righe.
const lines = [
  konoso + '   ' + paito + '   ' + aminiso,                 // 1  Lineare B
  'ko-no-so   pa-i-to   a-mi-ni-so',                        // 2  traslitterazione
  'Knossos, Phaistos, Amnisos — three centres on the island.', // 3 translation
  '',                                                       // 4
  eresija + '   3   ' + qere,                               // 5  Lineare B
  'e-re-si-ja   3   qe-re',                                 // 6  traslitterazione
  'Eresija; 3 units; uncertain word.'                       // 7 translation
];
const text = lines.join('\n');
const at = (sub, from) => { const s = text.indexOf(sub, from || 0); if (s < 0) throw new Error('not found: ' + sub); return [s, s + sub.length]; };
const mk = (span, cat, note, extra) => Object.assign({ id: TA.uid(), start: span[0], end: span[1], category: cat, note: note || '', tags: [] }, extra || {});

// Traslitterazioni (riga 2)
const koNoSo = at('ko-no-so');
const paiTo  = at('pa-i-to');
const amiNiso = at('a-mi-ni-so');
const koOnly = [koNoSo[0], koNoSo[0] + 2];        // "ko"
const soOnly = [koNoSo[1] - 2, koNoSo[1]];        // "so"
// Riga 6
const eresijaT = at('e-re-si-ja');
const tre = at(' 3 '); const treSpan = [tre[0] + 1, tre[1] - 1]; // "3" senza spazi

const d = TA.newDoc();
d.text = text;
d.meta.title = 'Example: place names and categories';
d.meta.author = 'Stele';
d.meta.script = 'linear-b';
d.meta.description = 'Fictional, AI-generated mock-up created solely to demonstrate Stele. It is not a scholarly edition or evidence source. Place names, annotations and readings are illustrative only.';

d.annotations = [
  // Luoghi (geolocalizzati) sulla traslitterazione
  mk(koNoSo, 'luogo', 'Main palatial centre and home of the Linear B archive.', { place: { name: 'Knossos', lat: 35.2980, lon: 25.1630, source: 'manual', detail: 'archaeological site' }, tags: ['place name'] }),
  mk(paiTo, 'luogo', 'Second centre on the island, in the Mesara plain.', { place: { name: 'Phaistos', lat: 35.0517, lon: 24.8144, source: 'manual', detail: 'archaeological site' }, tags: ['place name'] }),
  mk(amiNiso, 'luogo', 'Port of Knossos.', { place: { name: 'Amnisos', lat: 35.3339, lon: 25.1897, source: 'manual', detail: 'port' }, tags: ['place name', 'port'] }),
  // Sovrapposizioni su ko-no-so: due sillabogrammi (lessico) dentro il toponimo (luogo)
  mk(koOnly, 'lessico', 'Syllabogram ko (*70).', { tags: ['sign'] }),
  mk(soOnly, 'lessico', 'Syllabogram so (*12).', { tags: ['sign'] }),
  // Persona e cronologia (riga 6) — illustrativi
  mk(eresijaT, 'persona', 'Personal name; illustrative reading.', { tags: ['name'] }),
  mk(treSpan, 'cronologia', 'Numeric quantity: 3 units.', { tags: ['number'] }),
  // Nota generale sull'intera riga 3 (traduzione)
  mk(at('Knossos, Phaistos, Amnisos'), 'nota', 'Translation summary of the three place names on the first line.')
];

fs.writeFileSync('sample/example.json', JSON.stringify(TA.normalizeDoc(d), null, 2));
fs.writeFileSync('sample/example.tei.xml', TA.toTEI(TA.normalizeDoc(d)));
const s = TA.docStats(TA.normalizeDoc(d));
console.log('Sample written. Lines', s.righe, 'Tokens', s.token, 'Annotations', s.annotazioni, 'Notes', s.note, 'Places', s.luoghi);
