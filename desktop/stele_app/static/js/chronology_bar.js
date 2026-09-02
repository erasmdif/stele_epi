/* Barra temporale visuale per datazioni multiple.
 * Rende `chrono` = array di {absolute_from, absolute_to, dating_method, certainty,
 * term_label, note, id} come bande sovrapposte sull'asse.
 * Numerazione astronomica (1 BC = 0). */
(function(){
  'use strict';
  const NS='http://www.w3.org/2000/svg';
  const METHOD_COLOR={
    stratigraphic_context:'#2a6f9a', palaeography:'#7a4fb0', stylistic:'#c07b1f',
    radiocarbon:'#2f7d5b', dendrochronology:'#8a5a2a', typological:'#b5561f',
    epigraphic:'#2a6f9a', historical:'#6b6559', other:'#8a8271'
  };
  const CERT_ALPHA={Certain:1, Probable:0.75, Possible:0.55, Uncertain:0.4, Unknown:0.3};

  function fmtYear(y){
    if(y==null) return '?';
    if(y<0) return (-y)+' BC';
    if(y===0) return '1 BC';
    return y+' CE';
  }

  function render(target, chrono){
    const el=(typeof target==='string')?document.querySelector(target):target;
    if(!el) return;
    // filtri: solo datazioni con almeno un anno
    const items=(chrono||[]).filter(x=>x.absolute_from!=null || x.absolute_to!=null);
    if(!items.length){
      el.innerHTML='<div class="muted" style="font-size:13px;padding:6px 0">No dating with absolute years. Add one below.</div>';
      return;
    }
    // estendo un po' i bordi per respiro
    let mn=Math.min(...items.map(x=>x.absolute_from!=null?x.absolute_from:x.absolute_to));
    let mx=Math.max(...items.map(x=>x.absolute_to!=null?x.absolute_to:x.absolute_from));
    const span=mx-mn||100; mn-=Math.round(span*0.06); mx+=Math.round(span*0.06);
    const width=el.clientWidth||600, H=Math.max(72, items.length*22+40), pad=44;
    const x=y=>pad+((y-mn)/(mx-mn))*(width-pad*2);

    let svg=`<svg xmlns="${NS}" viewBox="0 0 ${width} ${H}" style="width:100%;height:${H}px;background:#faf9f4;border:1px solid var(--line);border-radius:6px">`;
    // asse
    svg+=`<line x1="${pad}" y1="${H-22}" x2="${width-pad}" y2="${H-22}" stroke="#c7bfa9" stroke-width="1"/>`;
    // tacche automatiche
    const tickStep=Math.pow(10, Math.floor(Math.log10(span))) || 100;
    const tickStart=Math.ceil(mn/tickStep)*tickStep;
    for(let t=tickStart; t<=mx; t+=tickStep){
      const xt=x(t);
      svg+=`<line x1="${xt}" y1="${H-25}" x2="${xt}" y2="${H-19}" stroke="#8a8271"/>`;
      svg+=`<text x="${xt}" y="${H-6}" font-size="10" fill="#8a8271" text-anchor="middle" font-family="monospace">${fmtYear(t)}</text>`;
    }
    // bande
    items.forEach((it,i)=>{
      const a=it.absolute_from!=null?it.absolute_from:it.absolute_to;
      const b=it.absolute_to!=null?it.absolute_to:it.absolute_from;
      const x1=x(Math.min(a,b)), x2=x(Math.max(a,b));
      const y=8+i*22, h=18;
      const col=METHOD_COLOR[it.dating_method]||'#6b6559';
      const alpha=CERT_ALPHA[it.certainty]||0.65;
      svg+=`<g style="cursor:default"><title>${(it.dating_method||'—')} · ${(it.certainty||'—')}${it.term_label?' · '+it.term_label:''}</title>`;
      svg+=`<rect x="${x1}" y="${y}" width="${Math.max(3,x2-x1)}" height="${h}" fill="${col}" opacity="${alpha}" rx="3"/>`;
      const label=(it.term_label||it.dating_method||'—');
      const midx=(x1+x2)/2;
      // etichetta interna se lo spazio basta, esterna altrimenti
      if((x2-x1)>label.length*6.5+8){
        svg+=`<text x="${midx}" y="${y+h/2+3}" font-size="11" fill="#fff" text-anchor="middle" style="pointer-events:none">${label}</text>`;
      } else {
        svg+=`<text x="${x2+4}" y="${y+h/2+3}" font-size="11" fill="#22201b" text-anchor="start" style="pointer-events:none">${label}</text>`;
      }
      svg+=`</g>`;
    });
    svg+=`</svg>`;
    el.innerHTML=svg;
  }

  window.ChronologyBar={render, fmtYear, METHOD_COLOR, CERT_ALPHA};
})();
