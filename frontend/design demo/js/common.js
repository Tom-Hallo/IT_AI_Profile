const root=document.documentElement;
const saved=localStorage.getItem('craft-theme');root.dataset.theme=saved|| (matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
function updateTheme(){document.querySelectorAll('[data-theme-label]').forEach(x=>x.textContent=root.dataset.theme==='dark'?'Light mode':'Dark mode');document.querySelectorAll('[data-theme-icon]').forEach(x=>x.textContent=root.dataset.theme==='dark'?'☀':'☾')}
function toast(msg){document.querySelector('.toast')?.remove();const el=document.createElement('div');el.className='toast';el.textContent=msg;document.body.append(el);setTimeout(()=>el.remove(),2600)}
document.addEventListener('click',e=>{if(e.target.closest('[data-theme-toggle]')){root.dataset.theme=root.dataset.theme==='dark'?'light':'dark';localStorage.setItem('craft-theme',root.dataset.theme);updateTheme()}if(e.target.closest('[data-menu]'))document.querySelector('.sidebar')?.classList.toggle('open');if(e.target.closest('[data-demo-action]'))toast(e.target.closest('[data-demo-action]').dataset.demoAction||'Đây là tính năng demo');});
window.addEventListener('DOMContentLoaded',updateTheme);
export {toast};
