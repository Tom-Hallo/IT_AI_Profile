const $ = id => document.getElementById(id);
const repoId = new URLSearchParams(location.search).get('repo_id');
const base = `/api/v1/repositories/${encodeURIComponent(repoId || '')}/consents`;
const originHeaders = {'Content-Type':'application/json'};
const access = $('access'), external = $('external'), save = $('save');
$('repo').textContent = repoId && /^\d+$/.test(repoId) ? `Repository ID: ${repoId}` : 'Thiếu repo_id hợp lệ trong URL.';
function sync() { external.disabled = !access.checked; if (!access.checked) external.checked = false; save.disabled = !(access.checked && external.checked && /^\d+$/.test(repoId || '')); }
access.addEventListener('change', sync); external.addEventListener('change', sync);
function paths() { return $('paths').value.split('\n').map(x=>x.trim()).filter(Boolean); }
async function request(url, options={}) { const res = await fetch(url,{credentials:'include',...options}); if(!res.ok) throw new Error(`HTTP ${res.status}`); return res.json(); }
async function refresh() { if(!/^\d+$/.test(repoId||''))return; try {const data=await request(base); $('status').textContent = data.consents.map(c=>`${c.consent_type}${c.provider?` (${c.provider})`:''}: ${c.granted?'Đã cấp':'Đã thu hồi'}`).join(' · ') || 'Chưa cấp quyền'; } catch { $('status').textContent='Không thể tải trạng thái. Vui lòng đăng nhập.'; } }
$('form').addEventListener('submit',async e=>{e.preventDefault(); if(save.disabled)return; save.disabled=true; try {const scope=paths(); if(!scope.length)throw new Error('Hãy chọn ít nhất một file'); const policy=await request(base); const body=(consent_type,provider='')=>JSON.stringify({consent_type,provider,scope,policy_version:policy.policy_version,accepted:true}); await request(base,{method:'POST',headers:originHeaders,body:body('repository_access')}); await request(base,{method:'POST',headers:originHeaders,body:body('external_ai','openai')}); $('status').textContent='Đã lưu hai xác nhận.';} catch(err){$('status').textContent=`Không hoàn tất: ${err.message}. Kiểm tra trạng thái bên dưới.`;} finally {sync(); await refresh();}});
for(const [id,type,provider] of [['revoke-access','repository_access',''],['revoke-external','external_ai','openai']]) $(''+id).addEventListener('click',async()=>{try{await request(`${base}/${type}${provider?'?provider='+encodeURIComponent(provider):''}`,{method:'DELETE'}); await refresh();}catch(err){$('status').textContent=`Thu hồi thất bại: ${err.message}`;}});
refresh();
