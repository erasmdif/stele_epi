const fs = require('fs');
const { JSDOM, VirtualConsole } = require('jsdom');

let pass = 0, fail = 0;
const ok = (n, c) => { (c ? pass++ : fail++); console.log((c ? 'PASS ' : 'FAIL ') + n); };

let html = fs.readFileSync('editor.html', 'utf8');
html = html.replace(/<link[^>]*>/g, '');
html = html.replace(/<script src="https?:[^"]*"><\/script>/g, '');
const core = fs.readFileSync('assets/js/core.js', 'utf8');
const lb = fs.readFileSync('assets/js/linearb.js', 'utf8');
const ed = fs.readFileSync('assets/js/editor.js', 'utf8');
html = html.replace('<script src="assets/js/core.js"></script>', () => '<script>' + core + '</script>');
html = html.replace('<script src="assets/js/linearb.js"></script>', () => '<script>' + lb + '</script>');
html = html.replace('<script src="assets/js/editor.js"></script>', () => '<script>' + ed + '</script>');

const vc = new VirtualConsole();
const errors = [];
vc.on('jsdomError', e => errors.push(e.message + (e.detail ? ' :: ' + e.detail : '')));

const dom = new JSDOM(html, {
  url: 'https://example.org/editor.html',
  runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc
});
const { window } = dom;
const document = window.document;
window.L = undefined;
window.HTMLElement.prototype.scrollIntoView = function () {};

const fire = (el, type) => el.dispatchEvent(new window.Event(type, { bubbles: true }));
const click = el => el.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));

window.addEventListener('load', () => setTimeout(runTests, 60));

function runTests() {
  ok('editor avviato: select scritture popolata', document.querySelector('#mScript').options.length >= 3);
  ok('editor avviato: palette sillabario renderizzata (>30 glifi)', document.querySelectorAll('#glyphGrid .glyph').length > 30);

  const ta = document.querySelector('#source');
  ta.value = 'XYZ'; fire(ta, 'input');

  function addNoteSel(s, e) { ta.selectionStart = s; ta.selectionEnd = e; click(document.querySelector('#btnAddNote')); }
  addNoteSel(0, 1); addNoteSel(2, 3); addNoteSel(0, 3);
  ok('tre note create', document.querySelectorAll('#annList .ann-item').length === 3);

  setTimeout(() => {
    const reader = document.querySelector('#reader');
    ok('reader: segmenti generati', reader.querySelectorAll('.seg').length >= 3);
    const cover = Array.from(reader.querySelectorAll('.seg.ann')).map(s => (s.getAttribute('data-anns') || '').split(' ').length);
    ok('reader: segmento con 2 note (sovrapposizione X/XYZ)', cover.some(n => n === 2));
    ok('reader: segmento con 1 nota (Y solo XYZ)', cover.some(n => n === 1));

    ta.selectionStart = ta.value.length; ta.selectionEnd = ta.value.length;
    const g = document.querySelector('#glyphGrid .glyph');
    ok('palette: glifo cliccabile presente', !!g);
    if (g) { click(g); ok('palette: glifo inserito nel testo', ta.value.length > 3); }

    let saved = null; try { saved = window.localStorage.getItem('stele:current:v1'); } catch (e) {}
    ok('autosave in localStorage', !!saved);
    let xml = '';
    try { xml = window.TA.toTEI(JSON.parse(saved)); } catch (e) {}
    ok('TEI generato dal documento salvato', xml.indexOf('<TEI') !== -1 && xml.indexOf('<standOff') !== -1);

    document.querySelector('#mScript').value = 'greek-ancient'; fire(document.querySelector('#mScript'), 'change');
    ok('cambio scrittura senza errori', true);

    ok('anteprima TEI sempre visibile', document.querySelector('#xmlOut').textContent.indexOf('<TEI') !== -1);
    ok('reader a righe numerate (gutter)', document.querySelectorAll('#reader .ln .lno').length >= 1);
    ok('gutter textarea popolato', document.querySelectorAll('#gnums div').length >= 1);
    ok('barra statistiche presente', /Annotazioni:/.test(document.querySelector('#statbar').textContent));
    ok('note con selettore di categoria', document.querySelectorAll('#annList .cat-select').length === 3);

    // Cambio categoria di una nota -> diventa persona (colore viola)
    const sel = document.querySelector('#annList .cat-select');
    sel.value = 'persona'; fire(sel, 'change');
    ok('cambio categoria applicato', window.TA.toTEI(JSON.parse(window.localStorage.getItem('stele:current:v1'))).indexOf('type="persona"') !== -1);

    if (errors.length) { console.log('\nERRORI jsdom:'); errors.forEach(e => console.log('  - ' + e)); }
    console.log('\n' + pass + ' pass, ' + fail + ' fail');
    process.exit(fail || errors.length ? 1 : 0);
  }, 200);
}
