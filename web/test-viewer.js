const fs = require('fs');
const { JSDOM, VirtualConsole } = require('jsdom');
let pass = 0, fail = 0;
const ok = (n, c) => { (c ? pass++ : fail++); console.log((c ? 'PASS ' : 'FAIL ') + n); };

let html = fs.readFileSync('viewer.html', 'utf8');
html = html.replace(/<link[^>]*>/g, '');
html = html.replace(/<script src="https?:[^"]*"><\/script>/g, '');
const core = fs.readFileSync('assets/js/core.js', 'utf8');
const vw = fs.readFileSync('assets/js/viewer.js', 'utf8');
html = html.replace('<script src="assets/js/core.js"></script>', () => '<script>' + core + '</script>');
html = html.replace('<script src="assets/js/viewer.js"></script>', () => '<script>' + vw + '</script>');
// forza il caricamento della sessione
html = html.replace('viewer.html', 'viewer.html'); // no-op

const sample = fs.readFileSync('sample/example.json', 'utf8');
const vc = new VirtualConsole(); const errors = [];
vc.on('jsdomError', e => errors.push(e.message));

const dom = new JSDOM(html, {
  url: 'https://example.org/viewer.html?from=session',
  runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc,
  beforeParse(win) { win.L = undefined; try { win.localStorage.setItem('stele:current:v1', sample); } catch (e) {} }
});
const { window } = dom; const document = window.document;
window.HTMLElement.prototype.scrollIntoView = function () {};

window.addEventListener('load', () => setTimeout(() => {
  ok('viewer: griglia visibile (documento caricato)', !document.querySelector('#grid').hidden);
  ok('viewer: titolo mostrato', document.querySelector('#vTitle').textContent.length > 0);
  ok('viewer: reader popolato con segmenti', document.querySelectorAll('#reader .seg').length > 0);
  ok('viewer: 8 annotazioni in lista', document.querySelectorAll('#annList .ann-item').length === 8);
  ok('viewer: sovrapposizione visibile (seg con 2 note)',
    Array.from(document.querySelectorAll('#reader .seg.ann')).some(s => (s.getAttribute('data-anns') || '').split(' ').length === 2));
  const placeBadges = document.querySelectorAll('#annList .place-meta').length;
  ok('viewer: 3 luoghi', placeBadges === 3);
  if (errors.length) { console.log('ERRORI:', errors); }
  console.log('\n' + pass + ' pass, ' + fail + ' fail');
  process.exit(fail || errors.length ? 1 : 0);
}, 80));
