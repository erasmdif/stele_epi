/* ============================================================================
 * Stele — linearb.js
 * Dati della palette Lineare B (Unicode block U+10000–U+100FF).
 * Il glifo è generato con String.fromCodePoint(cp) per non incorporare
 * caratteri astrali nel sorgente. Serve un font con copertura Lineare B
 * (Noto Sans Linear B, caricato dalle pagine HTML).
 * ==========================================================================*/
(function (root) {
  'use strict';

  // Sillabario: code point -> traslitterazione standard (Ventris–Chadwick).
  // I code point non assegnati del blocco sono volutamente omessi.
  const SYLLABARY = [
    [0x10000, 'a'], [0x10001, 'e'], [0x10002, 'i'], [0x10003, 'o'], [0x10004, 'u'],
    [0x10005, 'da'], [0x10006, 'de'], [0x10007, 'di'], [0x10008, 'do'], [0x10009, 'du'],
    [0x1000A, 'ja'], [0x1000B, 'je'], [0x1000D, 'jo'], [0x1000E, 'ju'],
    [0x1000F, 'ka'], [0x10010, 'ke'], [0x10011, 'ki'], [0x10012, 'ko'], [0x10013, 'ku'],
    [0x10014, 'ma'], [0x10015, 'me'], [0x10016, 'mi'], [0x10017, 'mo'], [0x10018, 'mu'],
    [0x10019, 'na'], [0x1001A, 'ne'], [0x1001B, 'ni'], [0x1001C, 'no'], [0x1001D, 'nu'],
    [0x1001E, 'pa'], [0x1001F, 'pe'], [0x10020, 'pi'], [0x10021, 'po'], [0x10022, 'pu'],
    [0x10023, 'qa'], [0x10024, 'qe'], [0x10025, 'qi'], [0x10026, 'qo'],
    [0x10028, 'ra'], [0x10029, 're'], [0x1002A, 'ri'], [0x1002B, 'ro'], [0x1002C, 'ru'],
    [0x1002D, 'sa'], [0x1002E, 'se'], [0x1002F, 'si'], [0x10030, 'so'], [0x10031, 'su'],
    [0x10032, 'ta'], [0x10033, 'te'], [0x10034, 'ti'], [0x10035, 'to'], [0x10036, 'tu'],
    [0x10037, 'wa'], [0x10038, 'we'], [0x10039, 'wi'], [0x1003A, 'wo'],
    [0x1003C, 'za'], [0x1003D, 'ze'], [0x1003F, 'zo'],
    // segni speciali / opzionali
    [0x10040, 'a2'], [0x10041, 'a3'], [0x10042, 'au'],
    [0x10043, 'dwe'], [0x10044, 'dwo'], [0x10045, 'nwa']
  ];

  // Ideogrammi: intervallo assegnato del blocco (commodities, unità, ecc.).
  // Etichettati per code point; il glifo dipende dal font.
  const IDEO_START = 0x10080, IDEO_END = 0x100FA;

  function syllabary() {
    return SYLLABARY.map(([cp, tr]) => ({
      cp, char: String.fromCodePoint(cp), translit: tr, kind: 'syllable',
      label: tr, hex: cp.toString(16).toUpperCase()
    }));
  }
  function ideograms() {
    const out = [];
    for (let cp = IDEO_START; cp <= IDEO_END; cp++) {
      out.push({
        cp, char: String.fromCodePoint(cp), translit: '', kind: 'ideogram',
        label: 'U+' + cp.toString(16).toUpperCase(), hex: cp.toString(16).toUpperCase()
      });
    }
    return out;
  }

  // Parsing di un code point inserito a mano ("10012", "U+10012", "0x10012").
  function parseCodePoint(input) {
    if (!input) return null;
    const m = String(input).trim().replace(/^u\+/i, '').replace(/^0x/i, '');
    const cp = parseInt(m, 16);
    if (isNaN(cp) || cp < 0x10000 || cp > 0x100FF) return null;
    return { cp, char: String.fromCodePoint(cp), hex: cp.toString(16).toUpperCase() };
  }

  function search(term) {
    term = (term || '').trim().toLowerCase();
    const all = syllabary();
    if (!term) return all;
    return all.filter(s => s.translit.toLowerCase().indexOf(term) === 0 ||
      s.translit.toLowerCase().indexOf(term) !== -1 ||
      s.hex.toLowerCase().indexOf(term) !== -1);
  }

  root.LinearB = { syllabary, ideograms, parseCodePoint, search, IDEO_START, IDEO_END };
})(typeof self !== 'undefined' ? self : this);
