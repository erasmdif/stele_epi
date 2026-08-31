/* Scheda contesto — editing + datazioni multiple + termini in-place. */
(function(){
  'use strict';
  const $=s=>document.querySelector(s);
  const $$=s=>Array.from(document.querySelectorAll(s));
  const OWNER_KIND=window.STELE_OWNER_KIND || 'context';
  const OWNER_ID=window.STELE_OWNER_ID;
  const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

  function toast(m,k){let h=$('#toastHost');if(!h){h=document.createElement('div');h.id='toastHost';h.className='toast-host';document.body.appendChild(h);}
    const e=document.createElement('div');e.className='toast'+(k?' '+k:'');e.textContent=m;h.appendChild(e);
    setTimeout(()=>{e.style.opacity=0;e.style.transition='.3s'},1800);setTimeout(()=>e.remove(),2200);}
  async function api(m,u,b){const o={method:m,headers:{}};if(b!==undefined){o.headers['Content-Type']='application/json';o.body=JSON.stringify(b);}
    const r=await fetch(u,o);let d=null;try{d=await r.json();}catch(e){} if(!r.ok)throw new Error((d&&d.error)||('HTTP '+r.status));return d;}

  // salva identità + campi archeologici
  const bSave=$('#btnSave');
  if(bSave) bSave.addEventListener('click',async()=>{
    const body={
      code:$('#fCode').value.trim() || null,
      name:$('#fName').value.trim() || null,
      description:$('#fDescription').value,
      deposit_type:$('#fDepositType').value || null,
      excavation_technique:$('#fExcavationTechnique').value || null,
      excavation_method_note:$('#fExcavationMethodNote').value,
      preservation_note:$('#fPreservationNote').value,
    };
    try{await api('PATCH',`/api/context/${OWNER_ID}`,body); toast('Salvato.','ok');}
    catch(e){toast(e.message,'err');}
  });

  // mappa (se c'è geometria)
  if(window.STELE_POINT && typeof L!=='undefined'){
    const map=L.map('ctxMap').setView([STELE_POINT.lat,STELE_POINT.lon],13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap'}).addTo(map);
    L.marker([STELE_POINT.lat,STELE_POINT.lon]).addTo(map);
  }

  // rimozione assegnazione termine
  $$('#termsList .rm').forEach(b=>b.addEventListener('click',async()=>{
    const aid=b.closest('[data-aid]').dataset.aid;
    if(!confirm('Rimuovere questa assegnazione?'))return;
    try{await api('DELETE',`/api/${OWNER_KIND}-term-assignments/${aid}`); location.reload();}
    catch(e){toast(e.message,'err');}
  }));

  // aggiunta termine (picker cerca-o-crea sul vocabolario relativo)
  const vocabTable=OWNER_KIND==='context'?'context_term':'object_term';
  $('#btnAddTerm').addEventListener('click',()=>openTermPicker($('#addTermBox')));

  function openTermPicker(host){
    host.querySelectorAll('.term-menu').forEach(m=>m.remove());
    const m=document.createElement('div'); m.className='term-menu'; m.style.position='relative';
    m.innerHTML=`
      <input placeholder="cerca o crea termine…">
      <div class="res"></div>
      <div class="create-hint">Digita per cercare o creare un nuovo termine di ${vocabTable}.</div>`;
    host.appendChild(m);
    const inp=m.querySelector('input'), res=m.querySelector('.res'); let t=null;
    async function search(){
      const val=inp.value.trim();
      const list=await api('GET',`/api/vocab/${vocabTable}?q=`+encodeURIComponent(val));
      let html='';
      if(val){
        const exact=list.some(x=>x.preferred_label.toLowerCase()===val.toLowerCase());
        if(!exact){
          html+=`<div class="primary-create" id="createNew">
            <span class="plus">＋</span>
            <span>Crea <b>«${esc(val)}»</b> come nuovo termine</span>
          </div>`;
        }
      }
      html+=list.map(x=>`<button data-id="${x.id}" style="display:block;width:100%;text-align:left;border:none;background:transparent;padding:5px 8px;border-radius:5px;cursor:pointer;font:inherit;font-size:13px">${esc(x.preferred_label)}${x.term_type?` <span class="tag">${x.term_type}</span>`:''}</button>`).join('');
      if(!list.length && !val) html='<div class="muted" style="font-size:12px;padding:4px">Digita per cercare o creare.</div>';
      res.innerHTML=html;
      const createEl=res.querySelector('#createNew');
      if(createEl) createEl.addEventListener('click',async()=>{
        try{
          const created=await api('POST',`/api/vocab/${vocabTable}`,{preferred_label:val});
          await assign(created.id);
        }catch(e){toast(e.message,'err');}
      });
      res.querySelectorAll('button[data-id]').forEach(b=>b.addEventListener('click',()=>assign(+b.dataset.id)));
    }
    async function assign(termId){
      try{
        await api('POST',`/api/${OWNER_KIND}/${OWNER_ID}/terms`,{term_id:termId});
        location.reload();
      }catch(e){toast(e.message,'err');}
    }
    inp.addEventListener('input',()=>{clearTimeout(t); t=setTimeout(search,180);}); inp.focus(); search();
    setTimeout(()=>document.addEventListener('click',outside),0);
    function outside(e){if(!m.contains(e.target)&&!$('#btnAddTerm').contains(e.target)){m.remove();document.removeEventListener('click',outside);}}
  }

  // --- CRONOLOGIA -----------------------------------------------------------
  ChronologyBar.render('#chronoBar', window.STELE_CHRONO || []);
  renderChronoList(window.STELE_CHRONO || []);
  window.addEventListener('resize', ()=>ChronologyBar.render('#chronoBar', window.STELE_CHRONO || []));

  function fmtY(y){return ChronologyBar.fmtYear(y);}
  function renderChronoList(items){
    const box=$('#chronoList');
    if(!items.length){box.innerHTML=''; return;}
    box.innerHTML=items.map(d=>{
      const range=(d.absolute_from!=null||d.absolute_to!=null)
        ? `<span class="mono" style="font-size:12px">${fmtY(d.absolute_from)} → ${fmtY(d.absolute_to)}</span>`
        : '<span class="muted">—</span>';
      return `<div class="row-line" data-did="${d.id}">
        ${range}
        <span class="tag">${d.dating_method||'metodo non specificato'}</span>
        ${d.certainty?`<span class="muted" style="font-size:11px">${d.certainty}</span>`:''}
        ${d.term_label?`<span style="font-size:12px">· <a href="/vocab/chronology_term/${d.chronology_term_id}">${esc(d.term_label)}</a></span>`:''}
        ${d.note?`<span class="muted" style="font-size:12px">— ${esc(d.note)}</span>`:''}
        <button class="rm" title="Rimuovi datazione">×</button>
      </div>`;
    }).join('');
    box.querySelectorAll('.rm').forEach(b=>b.addEventListener('click',async()=>{
      const did=b.closest('[data-did]').dataset.did;
      if(!confirm('Rimuovere questa datazione?'))return;
      try{await api('DELETE',`/api/${OWNER_KIND}-datings/${did}`); location.reload();}
      catch(e){toast(e.message,'err');}
    }));
  }

  // aggiunta datazione: pannellino inline
  $('#btnAddDating').addEventListener('click',()=>openDatingForm($('#addDatingBox')));

  async function openDatingForm(host){
    host.querySelectorAll('.dating-form').forEach(m=>m.remove());
    let enums={dating_methods:[]};
    try{enums=await api('GET','/api/enums/archaeology');}catch(e){}
    const form=document.createElement('div');
    form.className='dating-form';
    form.style.cssText='border:1px solid var(--line-strong);border-radius:6px;padding:12px;margin-top:8px;background:#fbfaf6';
    form.innerHTML=`
      <p class="eyebrow" style="margin:0 0 6px">Nuova datazione</p>
      <p class="muted" style="font-size:12px;margin:0 0 8px">
        Scegli un termine cronologico (gli anni si prendono da lì) <b>oppure</b> inserisci gli anni liberi.
        Puoi combinare entrambi: se metti gli anni, sovrascrivono quelli del termine.
      </p>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">
        <label style="font-size:11px;color:var(--ink-soft)">Termine cronologico
          <div style="position:relative">
            <input id="dfTerm" placeholder="cerca…" style="width:100%;font:inherit;padding:5px 8px;border:1px solid var(--line-strong);border-radius:5px">
            <input type="hidden" id="dfTermId">
            <div id="dfTermRes" class="res" style="display:none;position:absolute;top:100%;left:0;right:0;background:var(--paper);border:1px solid var(--line-strong);border-radius:5px;max-height:150px;overflow:auto;z-index:20"></div>
          </div>
        </label>
        <label style="font-size:11px;color:var(--ink-soft)">Da (anno, 1 BC = 0)
          <input id="dfFrom" type="number" placeholder="-1300"
                 style="width:100%;font:inherit;padding:5px 8px;border:1px solid var(--line-strong);border-radius:5px"></label>
        <label style="font-size:11px;color:var(--ink-soft)">A (anno)
          <input id="dfTo" type="number" placeholder="-1200"
                 style="width:100%;font:inherit;padding:5px 8px;border:1px solid var(--line-strong);border-radius:5px"></label>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px">
        <label style="font-size:11px;color:var(--ink-soft)">Metodo
          <select id="dfMethod" style="width:100%;font:inherit;padding:5px 8px;border:1px solid var(--line-strong);border-radius:5px">
            <option value="">— non specificato —</option>
            ${enums.dating_methods.map(m=>`<option>${m}</option>`).join('')}
          </select>
        </label>
        <label style="font-size:11px;color:var(--ink-soft)">Certezza
          <select id="dfCert" style="width:100%;font:inherit;padding:5px 8px;border:1px solid var(--line-strong);border-radius:5px">
            <option value="">—</option><option>certain</option><option>probable</option>
            <option>possible</option><option>uncertain</option><option>unknown</option>
          </select>
        </label>
      </div>
      <label style="font-size:11px;color:var(--ink-soft);display:block;margin-top:8px">Nota
        <input id="dfNote" placeholder="es. datazione paleografica indipendente dal contesto"
               style="width:100%;font:inherit;padding:5px 8px;border:1px solid var(--line-strong);border-radius:5px">
      </label>
      <div style="display:flex;gap:6px;justify-content:flex-end;margin-top:10px">
        <button class="btn mini" id="dfCancel">Annulla</button>
        <button class="btn mini primary" id="dfSave">Aggiungi</button>
      </div>`;
    host.appendChild(form);

    // ricerca chronology_term
    const inp=$('#dfTerm'), res=$('#dfTermRes'), hid=$('#dfTermId');
    let t=null;
    inp.addEventListener('input',()=>{clearTimeout(t); t=setTimeout(async()=>{
      const val=inp.value.trim();
      if(!val){res.style.display='none'; return;}
      const list=await api('GET','/api/vocab/chronology_term?q='+encodeURIComponent(val));
      res.innerHTML=list.slice(0,10).map(x=>`<button type="button" data-id="${x.id}" style="display:block;width:100%;text-align:left;border:none;background:transparent;padding:5px 8px;cursor:pointer;font:inherit;font-size:13px">${esc(x.preferred_label)}</button>`).join('');
      res.style.display=list.length?'block':'none';
      res.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{
        inp.value=b.textContent.trim(); hid.value=b.dataset.id; res.style.display='none';
      }));
    },160);});
    inp.addEventListener('focus',()=>{if(inp.value.trim()) res.style.display='block';});
    inp.addEventListener('blur',()=>setTimeout(()=>res.style.display='none',200));

    $('#dfCancel').addEventListener('click',()=>form.remove());
    $('#dfSave').addEventListener('click',async()=>{
      const body={
        chronology_term_id: hid.value?+hid.value:null,
        absolute_from: $('#dfFrom').value===''?null:+$('#dfFrom').value,
        absolute_to: $('#dfTo').value===''?null:+$('#dfTo').value,
        dating_method: $('#dfMethod').value || null,
        certainty_code: $('#dfCert').value || null,
        note: $('#dfNote').value || null,
      };
      try{
        await api('POST',`/api/${OWNER_KIND}/${OWNER_ID}/datings`,body);
        location.reload();
      }catch(e){toast(e.message,'err');}
    });
  }
})();
