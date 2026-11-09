// Motion system: respects reduced motion and touch devices.
const reduce=window.matchMedia('(prefers-reduced-motion: reduce)');
const coarse=window.matchMedia('(pointer: coarse)');
const enabled=()=>!reduce.matches;
const progress=document.querySelector('.scroll-progress');
let scheduled=false;
function updateScroll(){if(progress){const total=document.documentElement.scrollHeight-innerHeight;progress.style.width=`${total>0?Math.min(100,scrollY/total*100):0}%`;}scheduled=false;}
addEventListener('scroll',()=>{if(!scheduled){scheduled=true;requestAnimationFrame(updateScroll)}},{passive:true});updateScroll();
const observer=enabled()&&'IntersectionObserver' in window?new IntersectionObserver(entries=>{entries.forEach(e=>{if(e.isIntersecting){e.target.classList.add('is-visible');observer.unobserve(e.target)}})},{threshold:.09,rootMargin:'0px 0px -30px 0px'}):null;
document.querySelectorAll('.reveal').forEach(el=>observer?observer.observe(el):el.classList.add('is-visible'));
if(enabled()&&!coarse.matches){document.querySelectorAll('[data-tilt]').forEach(el=>{const max=Number(el.dataset.tiltMax||5);let frame=0;el.addEventListener('pointermove',e=>{if(frame)return;frame=requestAnimationFrame(()=>{frame=0;const r=el.getBoundingClientRect();const x=(e.clientX-r.left)/r.width-.5;const y=(e.clientY-r.top)/r.height-.5;el.style.transform=`rotateX(${-y*max*2}deg) rotateY(${x*max*2}deg)`})});el.addEventListener('pointerleave',()=>{cancelAnimationFrame(frame);frame=0;el.style.transform='rotateX(0deg) rotateY(0deg)'})})}
