/* Scheda-record del dizionario: editing identità, label, ID esterni, relazioni. */
(function(){
  'use strict';
  const $=s=>document.querySelector(s);
  const $$=s=>Array.from(document.querySelectorAll(s));
  const TID=window.STELE_TERM_ID, TTYPE=window.STELE_TERM_TYPE;
  const RELS_HINT=[['IS_A','is a type of'],['PART_OF','is part of'],
    ['ASSOCIATED_WITH','is associated with'],['EQUIVALENT_TO','is equivalent to'],
    ['DERIVED_FROM','is derived from'],['RELATED_TO','is related to']];
  const TYPES=['person','deity','place','institution','ethnonym','formula','abbreviation','concept','quantity','event','title','office','object_concept','other'];
  const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

  function toast(m,k){let h=$('#toastHost');if(!h){h=document.createElement('div');h.id='toastHost';h.className='toast-host';document.body.appendChild(h);}
    const e=document.createElement('div');e.className='toast'+(k?' '+k:'');e.textContent=m;h.appendChild(e);
    setTimeout(()=>{e.style.opacity=0;e.style.transition='.3s'},1800);setTimeout(()=>e.remove(),2200);}
  async function api(m,u,b){const o={method:m,headers:{}};if(b!==undefined){o.headers['Content-Type']='application/json';o.body=JSON.stringify(b);}
    const r=await fetch(u,o);let d=null;try{d=await r.json();}catch(e){} if(!r.ok)throw new Error((d&&d.error)||('HTTP '+r.status));return d;}
  const reload=()=>location.reload();

  // salva identità
  $('#btnSaveIdentity').addEventListener('click',async()=>{
    try{await api('PATCH',`/api/text-terms/${TID}`,{
      preferred_label:$('#fPreferred').value.trim(),
      term_type:$('#fType').value,
      description:$('#fDescription').value
    }); toast('Saved.','ok'); setTimeout(reload,400);}
    catch(e){toast(e.message,'err');}
  });
  $('#btnDelete').addEventListener('click',async()=>{
    if(!confirm('Delete this record? Records used by annotations cannot be deleted.'))return;
    try{await api('DELETE',`/api/text-terms/${TID}`);
      toast('Deleted.','ok'); setTimeout(()=>location.href='/vocabularies',600);}
    catch(e){toast(e.message,'err');}
  });

  // label alternative
  $('#btnAddLabel').addEventListener('click',async()=>{
    const l=$('#newLabel').value.trim(); if(!l)return;
    try{await api('POST',`/api/text-terms/${TID}/labels`,{
      label:l,label_type:$('#newLabelType').value,language:$('#newLabelLang').value||null});
      reload();}catch(e){toast(e.message,'err');}
  });
  $$('#labels .rm').forEach(b=>b.addEventListener('click',async()=>{
    const lid=b.closest('[data-lid]').dataset.lid;
    try{await api('DELETE',`/api/text-term-labels/${lid}`); reload();}catch(e){toast(e.message,'err');}
  }));

  // external IDs
  $('#btnAddExternal').addEventListener('click',async()=>{
    const id=$('#newIdentifier').value.trim(); if(!id){toast('Identifier is required.','warn');return;}
    try{await api('POST',`/api/text-terms/${TID}/external-ids`,{
      authority:$('#newAuthority').value, identifier:id, uri:$('#newUri').value||null}); reload();}
    catch(e){toast(e.message,'err');}
  });
  $$('#externals .rm').forEach(b=>b.addEventListener('click',async()=>{
    const xid=b.closest('[data-xid]').dataset.xid;
    try{await api('DELETE',`/api/text-term-external-ids/${xid}`); reload();}catch(e){toast(e.message,'err');}
  }));

  // relazioni: rimuovi
  $$('#neighbours .rm').forEach(b=>b.addEventListener('click',async()=>{
    const row=b.closest('[data-source]');
    if(!confirm('Remove this relation?'))return;
    try{await api('DELETE','/api/text-term-relations',{
      source_id:+row.dataset.source,target_id:+row.dataset.target,relation_code:row.dataset.rel});
      reload();}catch(e){toast(e.message,'err');}
  }));

  // relazioni: aggiungi (con creazione inline del target)
  $('#btnAddRel').addEventListener('click',()=>openRelPicker($('#addRelBox')));

  function openRelPicker(host){
    host.querySelectorAll('.term-menu').forEach(m=>m.remove());
    const m=document.createElement('div'); m.className='term-menu'; m.style.position='relative';
    m.innerHTML=`
      <div style="display:flex;gap:5px;margin-bottom:6px">
        <select id="relSel" style="width:52%;font:inherit;font-size:12px;padding:4px 6px;border:1px solid var(--line-strong);border-radius:5px">
          ${RELS_HINT.map(r=>`<option value="${r[0]}">${r[0]} · ${r[1]}</option>`).join('')}
        </select>
        <input id="relQ" placeholder="type a target label…" style="flex:1">
      </div>
      <div class="res" id="relRes"></div>`;
    host.appendChild(m);
    const q=m.querySelector('#relQ'), res=m.querySelector('#relRes'); let t=null;
    async function search(){
      const val=q.value.trim();
      const list=await api('GET','/api/text-terms?q='+encodeURIComponent(val));
      const filtered=list.filter(x=>x.id!==TID);
      let html='';
      if(val){
        const exact=filtered.some(x=>x.preferred_label.toLowerCase()===val.toLowerCase());
        if(!exact){
          html+=`<div class="primary-create" id="createNew">
            <span class="plus">＋</span>
            <span>Create <b>“${esc(val)}”</b> as</span>
            <select id="createType">${TYPES.map(t=>`<option ${t===TTYPE?'selected':''}>${t}</option>`).join('')}</select>
          </div>`;
        }
      }
      html+=filtered.map(x=>`<button data-id="${x.id}" style="display:block;width:100%;text-align:left;border:none;background:transparent;padding:5px 8px;border-radius:5px;cursor:pointer;font:inherit;font-size:13px">${esc(x.preferred_label)} <span class="tag">${x.term_type}</span></button>`).join('');
      if(!filtered.length && !val) html='<div class="muted" style="font-size:12px;padding:4px">Type to search or create.</div>';
      res.innerHTML=html;

      const createEl=res.querySelector('#createNew');
      if(createEl) createEl.addEventListener('click',async ev=>{
        if(ev.target.tagName==='SELECT') return;
        const type=res.querySelector('#createType').value;
        try{
          const created=await api('POST','/api/text-terms',{term_type:type,preferred_label:val});
          await linkTo(created.id);
        }catch(e){toast(e.message,'err');}
      });
      res.querySelectorAll('button[data-id]').forEach(b=>b.addEventListener('click',()=>linkTo(+b.dataset.id)));
    }
    async function linkTo(otherId){
      const relCode=m.querySelector('#relSel').value;
      try{
        await api('POST','/api/text-term-relations',{source_id:TID,target_id:otherId,relation_code:relCode});
        reload();
      }catch(e){toast(e.message,'err');}
    }
    q.addEventListener('input',()=>{clearTimeout(t); t=setTimeout(search,180);}); q.focus(); search();
    setTimeout(()=>document.addEventListener('click',outside),0);
    function outside(e){if(!m.contains(e.target)&&!$('#btnAddRel').contains(e.target)){m.remove();document.removeEventListener('click',outside);}}
  }
})();
