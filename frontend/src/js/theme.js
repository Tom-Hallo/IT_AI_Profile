const KEY='it-talent-theme';
export function initTheme(button){
  const saved=localStorage.getItem(KEY);
  const systemDark=window.matchMedia('(prefers-color-scheme: dark)').matches;
  const initial=saved==='light'||saved==='dark'?saved:(systemDark?'dark':'light');
  setTheme(initial,button);
  button.addEventListener('click',()=>{const next=document.documentElement.dataset.theme==='light'?'dark':'light';localStorage.setItem(KEY,next);setTheme(next,button)});
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change',event=>{if(!localStorage.getItem(KEY))setTheme(event.matches?'dark':'light',button)});
}
function setTheme(theme,button){document.documentElement.dataset.theme=theme;button.textContent=theme==='dark'?'☀':'☾';button.setAttribute('aria-label',`Switch to ${theme==='dark'?'light':'dark'} mode`)}
