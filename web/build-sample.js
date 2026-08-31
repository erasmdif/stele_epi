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
  'Cnosso, Festo, Amniso — tre centri dell\u2019isola.',    // 3  traduzione
  '',                                                       // 4
  eresija + '   3   ' + qere,                               // 5  Lineare B
  'e-re-si-ja   3   qe-re',                                 // 6  traslitterazione
  'Eresija; 3 (unit\u00e0); (parola incerta).'              // 7  traduzione
];
const text = lines.join('\n');
const at = (sub, from) => { const s = text.indexOf(sub, from || 0); if (s < 0) throw new Error('non trovato: ' + sub); return [s, s + sub.length]; };
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
d.meta.title = 'Esempio: toponimi e categorie';
d.meta.author = 'Stele';
d.meta.script = 'linear-b';
d.meta.description = 'Documento dimostrativo: toponimi micenei geolocalizzati, annotazioni per categoria (lessico, persona, luogo, cronologia, nota) e sovrapposizioni sulla stessa porzione. Le letture di r. 5–7 sono puramente illustrative.';

d.annotations = [
  // Luoghi (geolocalizzati) sulla traslitterazione
  mk(koNoSo, 'luogo', 'Centro palaziale principale; sede dell\u2019archivio in Lineare B.', { place: { name: 'Cnosso (Knossos)', lat: 35.2980, lon: 25.1630, source: 'manual', detail: 'sito archeologico' }, tags: ['toponimo'] }),
  mk(paiTo, 'luogo', 'Secondo centro dell\u2019isola, sulla piana della Messar\u00e0.', { place: { name: 'Festo (Phaistos)', lat: 35.0517, lon: 24.8144, source: 'manual', detail: 'sito archeologico' }, tags: ['toponimo'] }),
  mk(amiNiso, 'luogo', 'Porto di Cnosso.', { place: { name: 'Amniso (Amnisos)', lat: 35.3339, lon: 25.1897, source: 'manual', detail: 'porto' }, tags: ['toponimo', 'porto'] }),
  // Sovrapposizioni su ko-no-so: due sillabogrammi (lessico) dentro il toponimo (luogo)
  mk(koOnly, 'lessico', 'Sillabogramma ko (*70).', { tags: ['segno'] }),
  mk(soOnly, 'lessico', 'Sillabogramma so (*12).', { tags: ['segno'] }),
  // Persona e cronologia (riga 6) — illustrativi
  mk(eresijaT, 'persona', 'Antroponimo (lettura illustrativa).', { tags: ['nome'] }),
  mk(treSpan, 'cronologia', 'Quantit\u00e0 numerica: 3 unit\u00e0.', { tags: ['numero'] }),
  // Nota generale sull'intera riga 3 (traduzione)
  mk(at('Cnosso, Festo, Amniso'), 'nota', 'Sintesi in traduzione dei tre toponimi della prima riga.')
];

fs.writeFileSync('sample/example.json', JSON.stringify(TA.normalizeDoc(d), null, 2));
fs.writeFileSync('sample/example.tei.xml', TA.toTEI(TA.normalizeDoc(d)));
const s = TA.docStats(TA.normalizeDoc(d));
console.log('Scritto sample. Righe', s.righe, 'Token', s.token, 'Annotazioni', s.annotazioni, 'Note', s.note, 'Luoghi', s.luoghi);
