'use strict';
// Uses the application's existing same-origin cookie/session authentication.
const $ = (id) => document.getElementById(id);
const state = { roadmapId: 1 };
const statusLabels = {pending:'Pending', in_progress:'In Progress', completed:'Completed'};
function node(tag, className, text) { const el=document.createElement(tag); if(className)el.className=className; if(text!==undefined)el.textContent=text; return el; }
function message(text) { $('message').textContent=text; }
async function api(path, options={}) {
  const response=await fetch(`/api/v1/roadmap-tracking/${state.roadmapId}${path}`, {credentials:'same-origin', headers:{'Content-Type':'application/json'},...options});
  if(!response.ok)throw new Error(`${response.status}: ${(await response.text()).slice(0,250)}`);
  return response.json();
}
async function load() {
  try { state.roadmapId=Number($('roadmap-id').value); if(!Number.isSafeInteger(state.roadmapId)||state.roadmapId<1)throw new Error('Roadmap ID không hợp lệ');
    const data=await api(''); renderMilestones(data.milestones); renderSuggestions(data.suggestions); message('Đã tải roadmap.');
  }catch(error){message(error.message);}
}
function renderMilestones(items) {
  const root=$('milestones');root.replaceChildren();
  if(!items.length)root.append(node('p','', 'Chưa có milestone. Hãy đồng bộ từ PBI-023.'));
  for(const m of items){const card=node('article','card');card.append(node('h3','',m.title),node('p','',`Skills: ${m.required_skills.join(', ') || '—'}`));
    const row=node('div','actions');const select=node('select');select.setAttribute('aria-label',`Trạng thái ${m.title}`);
    for(const [value,label] of Object.entries(statusLabels)){const option=node('option','',label);option.value=value;option.selected=m.status===value;select.append(option);}
    const btn=node('button','primary','Lưu tiến độ');btn.addEventListener('click',async()=>{const note=window.prompt('Ghi chú thay đổi (không bắt buộc):')||null;try{await api(`/milestones/${m.id}`,{method:'PATCH',body:JSON.stringify({status:select.value,note,expected_version:m.version})});await load();}catch(error){message(error.message);}});
    const history=node('button','','Lịch sử');history.addEventListener('click',async()=>{try{const entries=await api(`/milestones/${m.id}/history`);message(entries.map(e=>`${new Date(e.created_at).toLocaleString('vi-VN')}: ${e.old_status||'—'} → ${e.new_status} (${e.source})`).join(' | ')||'Chưa có lịch sử');}catch(error){message(error.message);}});
    row.append(select,btn,history);card.append(row);root.append(card);}
}
function renderSuggestions(items) {
  const root=$('suggestions');root.replaceChildren();const pending=items.filter(s=>s.state==='pending');$('count').textContent=`(${pending.length})`;
  if(!pending.length)root.append(node('p','', 'Không có đề xuất đang chờ.'));
  for(const s of pending){const card=node('article','card');card.append(node('h3','',`Milestone #${s.milestone_id} · ${s.action}`),node('p','',s.explanation));
    const evidence=node('p','evidence',s.evidence.map(e=>`${e.skill}: ${e.ref}`).join(' · '));card.append(evidence);
    const row=node('div','actions');for(const [action,label] of [['apply','Chấp nhận'],['reject','Từ chối']]){const btn=node('button',action==='apply'?'primary':'',label);btn.addEventListener('click',async()=>{try{await api(`/suggestions/${s.id}/${action}`,{method:'POST'});await load();}catch(error){message(error.message);}});row.append(btn);}card.append(row);root.append(card);}
}
$('load').addEventListener('click',load);
$('reevaluate').addEventListener('click',async()=>{try{await api('/re-evaluate',{method:'POST',body:JSON.stringify({snapshot_id:'demo-valid',expected_scope:'public',expected_rubric:'v1',expected_period:'last-90-days'})});await load();}catch(error){message(error.message);}});
$('theme').addEventListener('click',()=>document.body.classList.toggle('dark'));
load();
