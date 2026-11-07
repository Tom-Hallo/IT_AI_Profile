export function initDialogs(notify){
  const confirm=document.querySelector('#confirm-dialog');const form=document.querySelector('#form-dialog');
  let danger=false;
  document.querySelector('#open-modal').addEventListener('click',()=>{danger=false;document.querySelector('#dialog-text').textContent='This is a reusable native dialog with keyboard support.';confirm.showModal()});
  document.querySelector('#danger-demo').addEventListener('click',()=>{danger=true;document.querySelector('#dialog-text').textContent='Demo only: no data will be deleted. Production destructive actions require server authorization.';confirm.showModal()});
  document.querySelector('#cancel-dialog').addEventListener('click',()=>confirm.close());
  document.querySelector('#confirm-dialog-btn').addEventListener('click',()=>{confirm.close();notify(danger?'Danger action simulated; no data deleted.':'Action confirmed (demo).')});
  document.querySelector('#open-form').addEventListener('click',()=>form.showModal());
  document.querySelector('#close-form').addEventListener('click',()=>form.close());
  document.querySelector('#demo-form').addEventListener('submit',event=>{event.preventDefault();const email=document.querySelector('#demo-email');const role=document.querySelector('#demo-role');const error=document.querySelector('#email-error');const valid=email.validity.valid&&email.value.trim().length>0;email.setAttribute('aria-invalid',String(!valid));error.textContent=valid?'':'Enter a valid email address.';role.setAttribute('aria-invalid',String(!role.value));if(!valid){email.focus();return}if(!role.value){role.focus();return}form.close();notify('Form validated successfully (demo).')});
}
export function initDrawer(notify){
  const drawer=document.querySelector('#agent-drawer');const open=document.querySelector('#open-agent');const close=document.querySelector('#close-agent');let previous=null;
  const focusable=()=>Array.from(drawer.querySelectorAll('button,input,[href]')).filter(el=>!el.disabled);
  function show(){previous=document.activeElement;drawer.classList.add('is-open');drawer.setAttribute('aria-hidden','false');open.hidden=true;close.focus()}
  function hide(){drawer.classList.remove('is-open');drawer.setAttribute('aria-hidden','true');open.hidden=false;previous?.focus()}
  open.addEventListener('click',show);close.addEventListener('click',hide);document.querySelector('#nav-agent').addEventListener('click',event=>{event.preventDefault();show()});
  drawer.addEventListener('keydown',event=>{if(event.key==='Escape'){hide();return}if(event.key==='Tab'){const nodes=focusable(),first=nodes[0],last=nodes[nodes.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}}});
  document.querySelector('#chat-form').addEventListener('submit',event=>{event.preventDefault();const input=document.querySelector('#chat-input');const msg=input.value.trim();if(!msg)return;const p=document.createElement('p');p.className='evidence-item';p.textContent=`You: ${msg}`;document.querySelector('#chat-output').append(p);input.value='';notify('Demo only — AI backend is not connected.')});
}
