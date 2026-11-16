// Browser-only interaction; no OAuth or server-side permission changes.
const byId=id=>document.getElementById(id);
const handle=byId('ghHandle'), role=byId('ghRole');
if(handle&&role){
 const refresh=()=>{byId('ghPreviewName').textContent='@'+(handle.value.trim().replace(/[^a-zA-Z0-9-]/g,'').slice(0,39)||'your-github-handle');byId('ghPreviewRole').textContent=role.value;};
 handle.addEventListener('input',refresh);role.addEventListener('change',refresh);
 document.querySelectorAll('[name="ghScope"]').forEach(el=>el.addEventListener('change',()=>{const isPrivate=document.querySelector('[name="ghScope"]:checked').value==='combined';byId('privateConsent').hidden=!isPrivate;byId('scopeStatus').textContent=isPrivate?'Private consent required':'Public repositories';byId('scopeMessage').textContent='Chưa có quyền nào được cấp.';}));
 byId('saveScope').addEventListener('click',()=>{const priv=document.querySelector('[name="ghScope"]:checked').value==='combined';byId('scopeMessage').textContent=priv&&!(byId('ghConsent1').checked&&byId('ghConsent2').checked)?'Vui lòng đánh dấu cả hai xác nhận để xem trước phạm vi private.':`Đã xem trước phạm vi ${priv?'public + private':'public'} — chưa cấp quyền thật và chưa kết nối GitHub.`;});
}
