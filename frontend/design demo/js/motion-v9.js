// Craft Talent V9: lightweight, accessible motion layer. No extra dependencies.
const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
const motion=()=>!reduced.matches;
const main=document.querySelector('main')||document.querySelector('.hero')||document.body;
main.id ||= 'main-content';
const skip=document.createElement('a');skip.className='v9-skip';skip.href='#main-content';skip.textContent='Bỏ qua điều hướng';document.body.prepend(skip);
// Animate only authored content blocks; never hide content if IntersectionObserver is unavailable.
const revealNodes=[...document.querySelectorAll('.page-header,.section-title,.panel,.hero h1,.hero p,.hero .btn,.feature-card,.v6-universe')].slice(0,70);
if(motion()&&'IntersectionObserver' in window){
 const observer=new IntersectionObserver((entries)=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('v9-visible');observer.unobserve(entry.target)}}),{threshold:.07,rootMargin:'0px 0px 60px 0px'});
 revealNodes.forEach((el,i)=>{el.classList.add('v9-reveal');el.style.setProperty('--v9-delay',`${Math.min(i%4,3)*55}ms`);observer.observe(el)});
}else revealNodes.forEach(el=>el.classList.add('v9-visible'));
// Only hover devices get visual depth; keyboard interaction remains unaffected.
if(window.matchMedia('(hover:hover) and (pointer:fine)').matches&&motion()){
 document.querySelectorAll('.panel,.feature-card').forEach(el=>{
  el.classList.add('v9-interactive','v9-spotlight');
  el.addEventListener('pointermove',e=>{const r=el.getBoundingClientRect();el.style.setProperty('--v9-x',`${e.clientX-r.left}px`);el.style.setProperty('--v9-y',`${e.clientY-r.top}px`)},{passive:true});
 });
}
// Page transitions only for same-origin, local HTML pages.
document.addEventListener('click',e=>{
 const a=e.target.closest('a[href]');if(!a||e.defaultPrevented||e.button!==0||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey||!motion())return;
 if(a.target||a.hasAttribute('download'))return;
 const url=new URL(a.href,location.href);if(url.origin!==location.origin||url.pathname===location.pathname||!url.pathname.endsWith('.html'))return;
 e.preventDefault();document.body.classList.add('v9-switching');setTimeout(()=>location.assign(url.href),180);
});
// Scroll-to-top utility.
const topBtn=document.createElement('button');topBtn.type='button';topBtn.className='v9-scrolltop';topBtn.setAttribute('aria-label','Lên đầu trang');topBtn.textContent='↑';document.body.append(topBtn);
const syncScroll=()=>topBtn.classList.toggle('show',scrollY>550);window.addEventListener('scroll',syncScroll,{passive:true});syncScroll();topBtn.addEventListener('click',()=>scrollTo({top:0,behavior:motion()?'smooth':'instant'}));
// Smooth theme visual feedback without overriding existing theme logic.
document.addEventListener('click',e=>{if(!e.target.closest('[data-theme-toggle],[data-v8-theme]'))return;document.body.classList.remove('v9-theme-flash');void document.body.offsetWidth;document.body.classList.add('v9-theme-flash');setTimeout(()=>document.body.classList.remove('v9-theme-flash'),500)});
// Animated demo metrics (numbers are NOT live scores).
if(motion()&&'IntersectionObserver' in window){const metrics=[...document.querySelectorAll('.metric strong')];const obs=new IntersectionObserver(entries=>entries.forEach(({target,isIntersecting})=>{if(!isIntersecting)return;obs.unobserve(target);const text=target.firstChild;if(!text||text.nodeType!==Node.TEXT_NODE)return;const match=text.textContent.trim().match(/^\d+$/);if(!match)return;const end=Number(match[0]);const start=performance.now();const original=match[0];function frame(t){const k=Math.min(1,(t-start)/700);text.textContent=String(Math.round(end*(1-(1-k)**3))).padStart(original.length,'0');if(k<1)requestAnimationFrame(frame)}requestAnimationFrame(frame)}),{threshold:.5});metrics.forEach(el=>obs.observe(el))}
// Surface demo workspace status on the dashboard, not fabricated live telemetry.
if(location.pathname.endsWith('/dashboard.html')){const host=document.querySelector('.page-header');if(host){const b=document.createElement('div');b.className='v9-workspace-banner';b.innerHTML='<div><strong><span class="v9-live-dot"></span>Developer Studio · V9 Motion</strong><small>Khám phá Skill Universe 3D, lộ trình và GitHub evidence. Dữ liệu hiện là demo.</small></div><a href="github-repo.html">Khám phá GitHub ↗</a>';host.after(b)}}
